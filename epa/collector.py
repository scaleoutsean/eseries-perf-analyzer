#!/usr/bin/env python3
"""
Retrieves and collects data from the the NetApp E-Series API server
and sends exports via Prometheus

-----------------------------------------------------------------------------
Copyright (c) 2026 E-Series Perf Analyzer (scaleoutSean@Github (post-v3.0.0
commits) and NetApp, Inc (pre-v3.1.0 commits))
Licensed under the MIT License. See LICENSE in the project root for details.
-----------------------------------------------------------------------------
Repository: https://github.com/scaleoutsean/eseries-perf-analyzer
"""

import argparse
import concurrent.futures
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from threading import Thread, Lock
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import requests

from mappings import (
    CONFIG_DRIVES_MAPPING,
    CONFIG_STORAGE_POOLS_MAPPING,
    CONFIG_VOLUMES_MAPPING,
    CONFIG_WORKLOADS_MAPPING,
    DRIVE_MAPPING,
    GLOBAL_ID_CACHE,
    HOSTS_MAPPING,
    HOST_GROUPS_MAPPING,
    PROMETHEUS_METRICS_CONFIG,
    SNAPSHOT_METRIC_DEFS,
    STORAGE_SYSTEM_GAUGE_KEYS,
    STORAGE_SYSTEM_INFO_KEYS,
    apply_mapping,
    extract_field_keys,
    extract_tag_keys,
    flatten_dict_one_level
)

# Monkey-patch requests.models.Response.json to handle 424 and other errors gracefully
_old_json = requests.models.Response.json

def _safe_json(self, **kwargs):
    res = _old_json(self, **kwargs)
    if not self.ok:
        logging.getLogger('collector').warning(f"API Error {self.status_code} for {self.url}")
        return []
    
    if isinstance(res, list):
        items = res
    elif isinstance(res, dict) and 'statistics' not in res:
        items = [res]
    else:
        items = []

    for item in items:
        if isinstance(item, dict):
            obj_id = item.get('id') or item.get('volumeRef') or item.get('pitRef') or item.get('consistencyGroupRef') or item.get('concatVolRef')
            name = item.get('name') or item.get('label') or item.get('volumeName') or item.get('groupName') or item.get('consistencyGroupName') or item.get('hostName')
            
            if not name and 'concatVolRef' in item and 'memberRefs' in item and isinstance(item['memberRefs'], list) and len(item['memberRefs']) > 0:
                member_names = [GLOBAL_ID_CACHE.get(m) for m in item['memberRefs'] if GLOBAL_ID_CACHE.get(m)]
                if member_names:
                    name = ",".join(member_names)

            if obj_id and name and isinstance(obj_id, str) and isinstance(name, str):
                GLOBAL_ID_CACHE[obj_id] = name

    return res

requests.models.Response.json = _safe_json


# Prometheus client imports (optional - will gracefully handle if not available)
try:
    from prometheus_client import CollectorRegistry, Gauge, Summary, Counter, generate_latest, CONTENT_TYPE_LATEST
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

if not PROMETHEUS_AVAILABLE:
    class DummyMetric:
        def labels(self, *args, **kwargs): return self
        def time(self): return self
        def inc(self, *args, **kwargs): pass
        def set(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb): False

    EPA_SCRAPE_TIME = DummyMetric()
    EPA_ERROR_COUNT = DummyMetric()
    EPA_METRIC_COUNT = DummyMetric()

def metrics_timer(endpoint_name):
    def decorator(func):
        def wrapper(*args, **kwargs):
            sys_info = args[0] if args else {}
            sys_name = sys_info.get('name', 'unknown') if isinstance(sys_info, dict) else 'unknown'
            try:
                with EPA_SCRAPE_TIME.labels(endpoint=endpoint_name, system=sys_name).time():
                    return func(*args, **kwargs)
            except Exception:
                EPA_ERROR_COUNT.labels(error_type='execution', endpoint=endpoint_name, system=sys_name).inc()
                raise
        return wrapper
    return decorator

DEFAULT_USERNAME = 'monitor'
DEFAULT_PASSWORD = ''

DEFAULT_SYSTEM_NAME = ''
DEFAULT_SYSTEM_ID = ''
DEFAULT_SYSTEM_API_IP = ''

DEFAULT_SYSTEM_PORT = '8443'

# Live stats cumulative time counters are treated as microseconds and normalized to ms.
LIVE_TIME_COUNTER_TO_MS = 1.0 / 1000.0

__version__ = '4.0.0beta3'

#######################
# LIST OF METRICS #####
#######################

# Naming convention: *_ANALYZED_* and *_LIVE_* refer to payload shape intent.
# Keep API paths exactly as implemented (some SANtricity endpoints use analysed, others analyzed).


FLASHCACHE_REALTIME_COUNTERS = [
    'reads',
    'readBlocks',
    'writes',
    'writeBlocks',
    'fullCacheHits',
    'fullCacheHitBlocks',
    'partialCacheHits',
    'partialCacheHitBlocks',
    'completeCacheMiss',
    'completeCacheMissBlocks',
    'populateOnReads',
    'populateOnReadBlocks',
    'populateOnWrites',
    'populateOnWriteBlocks',
    'invalidates',
    'recycles'
]

FLASHCACHE_REALTIME_GAUGES = [
    'availableBytes',
    'allocatedBytes',
    'populatedCleanBytes',
    'populatedDirtyBytes',
    'cached_volumes_count',
    'cache_drive_count'
]



# Configuration for interface alerting
# Only includes interfaces with known JSON structure patterns
# Each config specifies the JSON path to the alert status field and the values that trigger an alert
INTERFACE_ALERT_CONFIG = {
    'iscsi': {
        'enabled': True,
        # Path to status in iSCSI interface object
        'alert_paths': ['interfaceData', 'ethernetData', 'linkStatus'],
        # Values that trigger alert (1=alert)
        'alert_values': ['down'],
    },
    'ib': {
        'enabled': True,
        # Path to status in IB interface object
        'alert_paths': ['physPortState'],
        # Values that trigger alert (1=alert)
        'alert_values': ['linkdown'],
    },
    'ethernet': {
        'enabled': True,
        # Path to status in management Ethernet interface
        'alert_paths': ['ethernet', 'linkStatus'],
        # Values that trigger alert (1=alert)
        'alert_values': ['down'],
    }
    # FC, SAS omitted until JSON structure is confirmed in testing
    # Add additional interface types here after validating their JSON structure
}




#######################
# GLOBAL CACHE VARIABLES FOR CROSS-REFERENCING
#######################

# Cache for cross-referencing between configuration measurements
# Populated by collect_config_* functions, used by collect_config_volumes
_STORAGE_POOLS_CACHE = {}  # volumeGroupRef -> pool info
_HOSTS_CACHE = {}          # clusterRef -> host info
# Mega-cache from mappable-objects API - contains all volume and mapping data
_MAPPABLE_OBJECTS_CACHE = {}  # volumeRef -> complete volume object with mappings
# Cache for cross-referencing drive config (driveRef -> drive info)
_DRIVES_CACHE = {}  # driveRef -> drive info
# Cache for real-time volume statistics (volumeRef -> {timestamp, readOps, writeOps, etc.})
_VOLUME_STATS_CACHE = {}
# Cache for real-time controller statistics (controllerId -> cumulative counters)
_CONTROLLER_STATS_CACHE = {}
# Cache for live interface statistics (interfaceId -> {timestamp, readOps, writeOps, etc.})
_INTERFACE_STATS_CACHE = {}
# Cache for Flash Cache configuration (sys_id -> {flash_cache_id, flash_cache_name, ...})
_FLASHCACHE_METADATA_CACHE = {} 
# Cache for Flash Cache real-time statistics (sys_id -> counter dict)
_FLASHCACHE_STATS_CACHE = {}

# Global iteration counter for config collection timing
_CONFIG_COLLECTION_ITERATION_COUNTER = 0

# Global controller index for consistent selection within a collection session
_CURRENT_CONTROLLER_INDEX = None

# Guard to avoid repeated warning spam for controllerId type normalization
_CONTROLLER_ID_TYPE_WARNING_EMITTED = False

# Optional capture settings for recording SANtricity API responses
CAPTURE_ENABLED = False
_CAPTURE_DIR = None
_CAPTURE_SEQUENCE = count()
_CAPTURE_LOCK = Lock()


def initialize_capture(target_dir):
    """Enable capture of SANtricity API request/response payloads."""
    global CAPTURE_ENABLED, _CAPTURE_DIR

    if target_dir:
        capture_path = Path(target_dir).expanduser()
    else:
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        capture_path = Path.cwd() / 'captures' / timestamp

    capture_path.mkdir(parents=True, exist_ok=True)
    capture_path = capture_path.resolve()
    _CAPTURE_DIR = capture_path
    CAPTURE_ENABLED = True
    LOG.info("SANtricity API capture enabled; writing responses to %s", _CAPTURE_DIR)


def _serialize_capture_field(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.decode('utf-8', errors='replace')
    if isinstance(value, dict):
        return {str(key): _serialize_capture_field(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_capture_field(item) for item in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)


def _capture_slug_from_url(url):
    path = urlparse(url).path or ''
    slug = path.strip('/').replace('/', '_') or 'root'
    slug = re.sub(r'[^A-Za-z0-9_.-]+', '_', slug)
    return slug[:80]


def _record_capture(method, url, kwargs, *, session, response=None, error=None, duration=None):
    if not CAPTURE_ENABLED or _CAPTURE_DIR is None:
        return

    capture_entry = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'method': method.upper(),
        'url': url,
        'duration_seconds': duration,
        'request': {
            'params': _serialize_capture_field(kwargs.get('params')),
            'json': _serialize_capture_field(kwargs.get('json')),
            'data': _serialize_capture_field(kwargs.get('data')),
            'headers': _serialize_capture_field(dict(session.headers)),
        }
    }

    if kwargs.get('headers'):
        capture_entry['request']['headers_override'] = _serialize_capture_field(kwargs['headers'])

    if response is not None:
        capture_entry['response'] = {
            'status_code': response.status_code,
            'headers': _serialize_capture_field(dict(response.headers)),
            'body': _serialize_capture_field(response.text),
        }

    if error is not None:
        capture_entry['error'] = _serialize_capture_field(str(error))

    sequence = next(_CAPTURE_SEQUENCE)
    filename = _CAPTURE_DIR / f"{sequence:05d}_{_capture_slug_from_url(url)}.json"

    try:
        with _CAPTURE_LOCK:
            filename.write_text(json.dumps(capture_entry, indent=2, sort_keys=True), encoding='utf-8')
        LOG.debug("Captured %s %s -> %s", method.upper(), url, filename.name)
    except OSError as exc:
        LOG.warning("Failed to write capture file %s: %s", filename, exc)


class CaptureSession(requests.Session):
    """requests.Session that records outbound requests when capture mode is enabled."""

    def request(self, method, url, **kwargs):  # pylint: disable=arguments-renamed
        kwargs.setdefault('verify', self.verify)
        start_time = time.time()
        try:
            response = super().request(method, url, **kwargs)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _record_capture(method, url, kwargs, session=self, error=exc, duration=time.time() - start_time)
            raise

        _record_capture(method, url, kwargs, session=self, response=response, duration=time.time() - start_time)
        return response


def populate_mappable_objects_cache(system_info):
    """
    Populate mega-cache from mappable-objects API containing all volume and mapping data.

    This function ALWAYS runs (regardless of --include filters) because
    volume/mapping correlation is required for performance data host mapping.

    Builds _MAPPABLE_OBJECTS_CACHE containing:
    - Volume information (name, volumeRef, volumeGroupRef, etc.)
    - Volume mappings (listOfMappings with mapRef)
    - Storage pool references (volumeGroupRef)

    Replaces the need for separate _VOLUME_NAME_CACHE and _VOLUME_MAPPINGS_CACHE.

    :param system_info: The JSON object of a storage_system
    """

    # Only run during config collection intervals
    if not should_collect_config_data():
        LOG.debug(
            "Skipping mappable objects cache population - not a config collection interval"
        )
        return

    try:
        # Set controller for consistent selection within this collection session
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))

        session = get_session()

        # Clear and populate mega-cache from mappable-objects API
        _MAPPABLE_OBJECTS_CACHE.clear()

        # Get comprehensive mapping data from mappable-objects API
        url = f"{get_controller('sys')}/{sys_id}/mappable-objects"
        mappable_objects_response = session.get(url).json()
        LOG.debug(
            "Retrieved %d mappable objects for mega-cache",
            len(mappable_objects_response),
        )

        # Build comprehensive cache indexed by volumeRef
        for obj in mappable_objects_response:
            volume_ref = obj.get('volumeRef')
            
            # Skip snapshot repository volumes
            if obj.get('label', '').startswith('repos_'):
                continue

            if volume_ref:
                _MAPPABLE_OBJECTS_CACHE[volume_ref] = obj
                LOG.debug(
                    "Cached mappable object: '%s' -> %s",
                    obj.get('label'),
                    volume_ref,
                )

        LOG.info(
            "Built mappable objects mega-cache with %d volume objects",
            len(_MAPPABLE_OBJECTS_CACHE),
        )

    except Exception as exc:  # pylint: disable=broad-exception-caught
        LOG.warning(
            "Could not retrieve mappable-objects for mega-cache: %s",
            exc,
        )
        LOG.warning("Performance collector host mapping may be incomplete")

    finally:
        # Reset controller selection for next collection session
        set_current_controller_index(None)



def populate_hosts_cache(system_info):
    """
    Populate _HOSTS_CACHE with host mappings to resolve performance data host mapping.
    This also runs on config collection intervals.
    """
    if not should_collect_config_data():
        return

    try:
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))
            
        sys_id = system_info.get('wwn', system_info.get('id'))
        session = get_session()
        
        # Get host and host-group configurations
        hosts_response = session.get(f"{get_controller('sys')}/{sys_id}/hosts").json()
        try:
            host_groups_response = session.get(f"{get_controller('sys')}/{sys_id}/host-groups").json()
        except Exception as e:
            LOG.warning(f"Could not retrieve host-groups for cache: {e}")
            host_groups_response = []

        _HOSTS_CACHE.clear()
        
        # 1. Register Host Groups (even if empty, to map their IDs)
        for hg in host_groups_response:
            cluster_ref = hg.get('clusterRef', hg.get('id'))
            if cluster_ref and cluster_ref not in _HOSTS_CACHE:
                _HOSTS_CACHE[cluster_ref] = []
                
        # 2. Register Hosts
        for host in hosts_response:
            cluster_ref = host.get('clusterRef')
            host_ref = host.get('hostRef')
            host_info = {
                'name': host.get('name', host.get('label', 'unknown')),
                'hostRef': host_ref,
                'id': host.get('id', 'unknown')
            }

            if cluster_ref:
                if cluster_ref not in _HOSTS_CACHE:
                    _HOSTS_CACHE[cluster_ref] = []
                _HOSTS_CACHE[cluster_ref].append(host_info)

                if cluster_ref == "0000000000000000000000000000000000000000" and host_ref:
                    _HOSTS_CACHE[host_ref] = [host_info]
                    
        LOG.info(f"Built hosts cache with {len(_HOSTS_CACHE)} entries")
        
    except Exception as exc:
        LOG.warning(f"Could not retrieve hosts for cache: {exc}")
        
    finally:
        set_current_controller_index(None)


@metrics_timer("config_drives")
def collect_config_drives(system_info):
    """
    Collects drive configuration information for Prometheus
    :param system_info: The JSON object of a storage_system
    """
    # Early exit if not a config collection interval
    if not should_collect_config_data():
        LOG.info(
            "Skipping config_drives collection - not a scheduled interval "
            "(collected every 15 minutes)"
        )
        return

    try:
        # Set controller for consistent selection within this collection session
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))

        session = get_session()

        # Get drive configuration data from the API
        drive_url = f"{get_controller('sys')}/{sys_id}/drives"
        drives_response = session.get(drive_url).json()

        LOG.debug(
            "Retrieved %d drive configurations",
            len(drives_response),
        )

        for drive in drives_response:
            prom_metrics = apply_mapping(drive, CONFIG_DRIVES_MAPPING)

            # extract all string/label fields from prom_metrics
            extracted_labels = {
                "sys_id": sys_id,
                "sys_name": sys_name,
                "drive_ref": prom_metrics.pop("drive_ref", "unknown"),
                "serial_number": prom_metrics.pop("serial_number", "unknown"),
                "product_id": prom_metrics.pop("product_id", "unknown"),
                "drive_media_type": prom_metrics.pop("drive_media_type", "unknown"),
                "tray_id": str(prom_metrics.pop("tray_id", "unknown")),
                "slot_number": str(prom_metrics.pop("slot_number", "unknown")),
                "is_hot_spare": str(prom_metrics.pop("is_hot_spare", "")).lower(),
                "status": prom_metrics.pop("status", "unknown"),
                "volume_group_ref": prom_metrics.pop("volume_group_ref", "unknown"),
                "available": str(prom_metrics.pop("available", "")).lower(),
                "offline": str(prom_metrics.pop("offline", "")).lower(),
                "removed": str(prom_metrics.pop("removed", "")).lower()
            }

            
            # Generate the info metric
            info_labels = {k: extracted_labels[k] for k in PROMETHEUS_METRICS_CONFIG["config_drives"]["info"]["labels"] if k in extracted_labels}
            prometheus_metrics["config_drives"]["info"].labels(**info_labels).set(1.0)
            
            # The rest of the keys left in prom_metrics are the float-like config values
            for metric_key, val in prom_metrics.items():
                if metric_key in prometheus_metrics["config_drives"] and val is not None:
                    metric_labels = {k: extracted_labels[k] for k in PROMETHEUS_METRICS_CONFIG["config_drives"][metric_key]["labels"] if k in extracted_labels}
                    prometheus_metrics["config_drives"][metric_key].labels(**metric_labels).set(float(val))

    except RuntimeError:
        LOG.error(f"Error when attempting to post drive configuration for {system_info['name']}/{system_info['wwn']}")


#######################
# PARAMETERS ##########
#######################

NUMBER_OF_THREADS = 8

# Configuration data collection interval (in minutes)
# Config data changes infrequently, so collect every N minutes instead of every iteration
CONFIG_COLLECTION_INTERVAL_MINUTES = 15  # Collect config data every 15th minute

# LOGGING
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
LOG = logging.getLogger("collector")

# Disables reset connection warning message if the connection time is too long
try:
    logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(
        logging.WARNING)
except (AttributeError, KeyError):
    # Fallback for different urllib3 configurations
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


#######################
# ARGUMENT PARSER #####
#######################

PARSER = argparse.ArgumentParser()

PARSER.add_argument('-u', '--username', default=DEFAULT_USERNAME, type=str, required=False,
                    help='Username to connect to the SANtricity API. '
                         'Required. Default: \'' + DEFAULT_USERNAME + '\'. <String>')
PARSER.add_argument('-p', '--password', default='', type=str, required=False,
                    help='Password for this user to connect to the SANtricity API. '
                         'Required. Default: \'' + DEFAULT_PASSWORD + '\'. <String>')
PARSER.add_argument('--api', default='',  nargs='+', required=False,
                    help='The IPv4 address for the SANtricity API endpoint. '
                         'Required. Example: --api 5.5.5.5 6.6.6.6. Port number is auto-set to: \'' +
                    DEFAULT_SYSTEM_PORT + '\'. '
                         'May be provided twice (for two controllers). <IPv4 Address>')
PARSER.add_argument("--api-port", default=DEFAULT_SYSTEM_PORT, type=str, required=False, help="The port for the SANtricity API endpoint. Default: '" + DEFAULT_SYSTEM_PORT + "'.")
PARSER.add_argument('-t', '--intervalTime', type=int, default=60, choices=[60, 120, 300, 600],
                    help='Interval (seconds) to poll and export data from the SANtricity API. Default: 60. <Integer>')
PARSER.add_argument('-s', '--showStorageNames', action='store_true',
                    help='Outputs the storage array names found from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-v', '--showVolumeNames', action='store_true', default=0,
                    help='Outputs the volume names found from the SANtricity API to console.  Optional. <switch>')
PARSER.add_argument('--showFlashCache', action='store_true', default=False,
                    help='Outputs the Flash Cache IDs, names, and real-time stats to console. Optional. <switch>')
PARSER.add_argument('-f', '--showInterfaceNames', action='store_true', default=0,
                    help='Outputs the interface names found from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-a', '--showVolumeMetrics', action='store_true', default=0,
                    help='Outputs the volume payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-d', '--showDriveNames', action='store_true', default=0,
                    help='Outputs the drive names found from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-b', '--showDriveMetrics', action='store_true', default=0,
                    help='Outputs the drive payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-ct', '--showControllerMetrics', action='store_true', default=0,
                    help='Outputs the controller payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-c', '--showSystemMetrics', action='store_true', default=0,
                    help='Outputs the system payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-m', '--showMELMetrics', action='store_true', default=0,
                    help='Outputs the MEL payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-e', '--showStateMetrics', action='store_true', default=0,
                    help='Outputs the state payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-g', '--showInterfaceMetrics', action='store_true', default=0,
                    help='Outputs the interface payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-pw', '--showPower', action='store_true', default=0,
                    help='Outputs the PSU reading to console. Optional. <switch>')
PARSER.add_argument('-en', '--showSensor', action='store_true', default=0,
                    help='Outputs the readings from environmental sensors (temperature) to console. Optional. <switch>')
PARSER.add_argument('-i', '--showIteration', action='store_true', default=0,
                    help='Outputs the current loop iteration. Optional. <switch>')
PARSER.add_argument('--debug', action='store_true', default=False,
                    help='Enable debug logging to show detailed collection and filtering information. Optional. <switch>')
PARSER.add_argument('--debug-force-config', action='store_true', default=False,
                    help='Force config data collection every iteration (for testing). Optional. <switch>')
PARSER.add_argument('--include', nargs='+', required=False,
                    help='Only collect specified measurements. Options: '
                    'disks, interface, volumes, controllers, power, temp, '
                         'failures, config_storage_pools, config_workloads, config_volumes, config_hosts, config_drives, flashcache. '
                         'Example: --include disks interface. If not specified, '
                         'all measurements are collected.')
PARSER.add_argument('--prometheus-port', type=int, default=9080,
                    help='Port for Prometheus metrics HTTP server. Default: 9080. Only used when --output includes prometheus.')
PARSER.add_argument('--max-iterations', type=int, default=0,
                    help='Maximum number of collection iterations to run (0 = unlimited). Useful for testing. Default: 0.')
PARSER.add_argument('--capture', nargs='?', const='', default=None, metavar='DIR',
                    help='Capture SANtricity API request/response payloads to disk for replay or debugging. '
                         'Optionally specify a directory; if omitted, files are stored under ./captures/<timestamp>.')
PARSER.add_argument('--no-verify-ssl', action='store_true', default=False,
                    help='Disable TLS/SSL certificate verification for SANtricity API connections. '
                         'Use only in lab/dev environments with self-signed certificates. '
                         'Default: False (verification enabled).')

CMD = PARSER.parse_args()

if CMD.no_verify_ssl:
    try:
        requests.packages.urllib3.disable_warnings()
    except AttributeError:
        pass
    import warnings
    warnings.filterwarnings('ignore', message='Unverified HTTPS request')

if CMD.capture is not None:
    initialize_capture(CMD.capture)

# Set logging level based on debug flag
if CMD.debug:
    logging.getLogger().setLevel(logging.DEBUG)
    LOG.setLevel(logging.DEBUG)
    LOG.debug("Debug logging enabled")

# Conditional validation for database creation mode
# For normal operation, SANtricity API parameters are required
if not CMD.username:
    # Fall back to environment variable and finally DEFAULT_USERNAME if not provided
    CMD.username = os.getenv('USERNAME', DEFAULT_USERNAME)
    # If still not set, raise error
    if not CMD.username:
        PARSER.error("--username is required for normal operation")
if not CMD.password:
    PARSER.error("--password is required for normal operation")
if not CMD.api:
    PARSER.error("--api is required for normal operation")


# Define which measurements each collection function provides
FUNCTION_MEASUREMENTS = {
    "collect_config_interfaces": ["config_interfaces"],
    "collect_config_controllers": ["config_controllers"],
    'collect_storage_metrics': ['disks', 'interface', 'volumes'],
    'collect_controller_metrics': ['controllers'],
    'collect_symbol_stats': ['power', 'temp'],
    'collect_system_state': ['failures', 'interface_alerts'],
    'collect_config_storage_pools': ['config_storage_pools'],
    'collect_config_workloads': ['config_workloads'],
    'collect_config_volumes': ['config_volumes', 'config_volumes_summary'],
    'collect_config_volume_mappings': ['config_volume_mappings'],
    'collect_config_hosts': ['config_hosts', 'config_host_groups'],
    'collect_config_drives': ['config_drives'],
    'collect_flashcache_stats': ['flashcache'],
    'collect_config_system': ['config_system'],
    'collect_config_snapshots_all': [
        'config_consistency_groups', 'config_snapshot_groups', 'config_repositories',
        'config_snapshot_images', 'config_snapshot_volumes',
        'config_snapshot_group_util', 'config_snapshot_volume_util',
        'config_consistency_group_members', 'config_snapshot_schedules'
    ]
}

# Validate --include options if provided
if hasattr(CMD, 'include') and CMD.include:
    valid_measurements = set()
    for measurements in FUNCTION_MEASUREMENTS.values():
        valid_measurements.update(measurements)

    invalid_measurements = [
        m for m in CMD.include if m not in valid_measurements]
    if invalid_measurements:
        PARSER.error(f"Invalid measurement(s) in --include: "
                     f"{', '.join(invalid_measurements)}. "
                     f"Valid options: {', '.join(sorted(valid_measurements))}")

    LOG.info(
        f"Selective collection enabled. Including measurements: {', '.join(CMD.include)}")
    LOG.debug(f"CMD.include value: {CMD.include}")
    LOG.debug(f"CMD.include type: {type(CMD.include)}")
else:
    LOG.info("Collecting all measurements (default behavior)")
    LOG.debug(f"CMD.include value: {CMD.include}")
    LOG.debug(f"CMD.include type: {type(CMD.include)}")

# Validate config collection interval against collector interval
collector_interval_minutes = CMD.intervalTime / 60.0
if CONFIG_COLLECTION_INTERVAL_MINUTES < collector_interval_minutes:
    PARSER.error(f"Config collection interval ({CONFIG_COLLECTION_INTERVAL_MINUTES} minutes) "
                    f"cannot be less than collector interval ({collector_interval_minutes} minutes). "
                    f"Config data cannot be collected more frequently than the collector runs.")


#######################
# PROMETHEUS SETUP ####
#######################

# Global Prometheus registry and metrics
prometheus_registry = None
prometheus_metrics = {}
prometheus_server = None

def setup_prometheus():
    """
    Initialize Prometheus metrics and HTTP server if Prometheus output is enabled.
    """

    if not PROMETHEUS_AVAILABLE:
        LOG.error("Prometheus client library not available. Install with: pip install prometheus-client")
        sys.exit(1)

    LOG.info(f"Setting up Prometheus metrics server on port {CMD.prometheus_port}")

    global prometheus_registry
    # Create custom registry to avoid conflicts with default registry
    prometheus_registry = CollectorRegistry()

    global EPA_SCRAPE_TIME, EPA_ERROR_COUNT, EPA_METRIC_COUNT
    EPA_SCRAPE_TIME = Summary('epa_scrape_duration_seconds', 'Time spent scraping SANtricity', ['endpoint', 'system'], registry=prometheus_registry)
    EPA_ERROR_COUNT = Counter('epa_scrape_errors_total', 'Number of failures during collection', ['error_type', 'endpoint', 'system'], registry=prometheus_registry)
    EPA_METRIC_COUNT = Gauge('epa_metrics_generated_total', 'Number of metrics successfully generated', ['endpoint', 'system'], registry=prometheus_registry)

    # Import metrics configurations from mappings

    # Initialize default static metrics
    for measurement, metrics in PROMETHEUS_METRICS_CONFIG.items():
        prometheus_metrics[measurement] = {}
        for metric_key, config in metrics.items():
            prometheus_metrics[measurement][metric_key] = Gauge(
                config['name'], config['desc'], config['labels'], registry=prometheus_registry
            )

    # Dynamically register snapshot config metrics
    for measurement, metric_def in SNAPSHOT_METRIC_DEFS.items():
        base_name, desc, mapping, _ = metric_def
        tags = ["sys_id", "sys_name"] + extract_tag_keys(mapping)
        fields = extract_field_keys(mapping)
        
        prom_dict = {
            'info': Gauge(f"{base_name}_info", f"{desc} info", tags, registry=prometheus_registry)
        }
        for field in fields:
            prom_dict[f"{measurement}_{field}"] = Gauge(f"{base_name}_{field}", f"{desc} - {field}", tags, registry=prometheus_registry)
        prometheus_metrics[measurement] = prom_dict

    # Start HTTP server in background thread
    start_prometheus_server()


class PrometheusHandler(BaseHTTPRequestHandler):
    """HTTP handler for Prometheus metrics endpoint."""

    def do_GET(self):
        # Handle path parsing to ignore query params and trailing slashes
        parsed_path = urlparse(self.path)
        clean_path = parsed_path.path.rstrip('/')

        if clean_path == '/metrics':
            try:
                self.send_response(200)
                self.send_header('Content-Type', CONTENT_TYPE_LATEST)
                self.end_headers()
                self.wfile.write(generate_latest(prometheus_registry))
            except Exception as e:
                LOG.error(f"Error generating Prometheus metrics: {e}")
                self.send_response(500)
                self.end_headers()
        elif clean_path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
            self.end_headers()


    def log_message(self, format, *args):  # pylint: disable=redefined-builtin
        # Log to the standard collector logger if debug is enabled
        if CMD.debug:
            LOG.debug("Prometheus HTTP: %s - - [%s] %s\n" %
                      (self.client_address[0],
                       self.log_date_time_string(),
                       format % args))


def start_prometheus_server():
    """Start Prometheus metrics HTTP server in background thread."""

    def run_server():
        try:
            # Use ThreadingHTTPServer to handle multiple concurrent requests (e.g. browser keep-alive + actual scrape)
            prometheus_server = ThreadingHTTPServer(('', CMD.prometheus_port), PrometheusHandler)
            LOG.info(f"Prometheus metrics server started on port {CMD.prometheus_port}")
            LOG.info(f"Metrics available at: http://0.0.0.0:{CMD.prometheus_port}/metrics")
            prometheus_server.serve_forever()
        except Exception as e:
            LOG.error(f"Failed to start Prometheus server: {e}")

    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()


def send_to_prometheus(measurement, tags, fields):
    """
    Send metrics to Prometheus.

    Args:
        measurement (str): Measurement name (e.g., 'disks', 'controllers')
        tags (dict): Tag dictionary with label values
        fields (dict): Field dictionary with metric values
    """
    if not PROMETHEUS_AVAILABLE:
        return

    if measurement not in prometheus_metrics:
        LOG.debug(f"No Prometheus metrics defined for measurement: {measurement}")
        return

    measurement_metrics = prometheus_metrics[measurement]

    try:
        if PROMETHEUS_AVAILABLE:
            EPA_METRIC_COUNT.labels(endpoint=measurement, system=tags.get("sys_name", "unknown")).inc(len(fields))
        if measurement == 'disks':
            # Remove any tags that aren't in Prometheus label definition and ensure required labels exist
            dtags = {
                'sys_id': tags.get('sys_id', 'unknown'),
                'sys_name': tags.get('sys_name', 'unknown'),
                'sys_tray': tags.get('sys_tray', 'unknown'),
                'sys_tray_slot': tags.get('sys_tray_slot', 'unknown'),
                'vol_group_name': tags.get('vol_group_name', 'unknown')
            }
            
            # Map disk fields to Prometheus metrics
            if 'combinedIOps' in fields and fields['combinedIOps'] is not None:
                measurement_metrics['iops'].labels(**dtags).set(fields['combinedIOps'])

            # Throughput metrics
            for direction, field in [('read', 'readThroughput'), ('write', 'writeThroughput'), ('combined', 'combinedThroughput')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['throughput'].labels(**dtags, direction=direction).set(fields[field])

            # Response time metrics
            for operation, field in [('read', 'readResponseTime'), ('write', 'writeResponseTime'), ('combined', 'combinedResponseTime')]:
                if field in fields and fields[field] is not None:
                    # Convert milliseconds to seconds for Prometheus
                    measurement_metrics['response_time'].labels(**dtags, operation=operation).set(fields[field] / 1000.0)

            # SSD wear metrics
            if 'spareBlocksRemainingPercent' in fields and fields['spareBlocksRemainingPercent'] is not None:
                measurement_metrics['ssd_wear'].labels(**dtags, metric='spare_blocks_remaining').set(fields['spareBlocksRemainingPercent'])
            if 'percentEnduranceUsed' in fields and fields['percentEnduranceUsed'] is not None:
                measurement_metrics['ssd_wear'].labels(**dtags, metric='endurance_used').set(fields['percentEnduranceUsed'])

        elif measurement == 'controllers':
            # Controller IOPS
            for operation, field in [('read', 'readIOps'), ('write', 'writeIOps'), ('other', 'otherIOps'), ('combined', 'combinedIOps')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['iops'].labels(**tags, operation=operation).set(fields[field])

            # Controller throughput
            for direction, field in [('read', 'readThroughput'), ('write', 'writeThroughput'), ('combined', 'combinedThroughput')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['throughput'].labels(**tags, direction=direction).set(fields[field])

            # CPU utilization
            for metric, field in [('max', 'maxCpuUtilization'), ('average', 'cpuAvgUtilization')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['cpu_utilization'].labels(**tags, metric=metric).set(fields[field])

            # Cache hit rate
            if 'cacheHitBytesPercent' in fields and fields['cacheHitBytesPercent'] is not None:
                measurement_metrics['cache_hit'].labels(**tags).set(fields['cacheHitBytesPercent'])

        elif measurement == 'volumes':
            # Volume IOPS
            for operation, field in [('read', 'readIOps'), ('write', 'writeIOps'), ('other', 'otherIOps'), ('combined', 'combinedIOps')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['iops'].labels(**tags, operation=operation).set(fields[field])

            # Volume throughput
            for direction, field in [('read', 'readThroughput'), ('write', 'writeThroughput'), ('combined', 'combinedThroughput')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['throughput'].labels(**tags, direction=direction).set(fields[field])

            # Volume response time
            for operation, field in [('read', 'readResponseTime'), ('write', 'writeResponseTime'), ('combined', 'combinedResponseTime')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['response_time'].labels(**tags, operation=operation).set(fields[field] / 1000.0)

        elif measurement == 'interface':
            # Interface IOPS
            for operation, field in [('read', 'readIOps'), ('write', 'writeIOps'), ('other', 'otherIOps'), ('combined', 'combinedIOps')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['iops'].labels(**tags, operation=operation).set(fields[field])

            # Interface throughput
            for direction, field in [('read', 'readThroughput'), ('write', 'writeThroughput'), ('combined', 'combinedThroughput')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['throughput'].labels(**tags, direction=direction).set(fields[field])

            # Queue depth
            for metric, field in [('total', 'queueDepthTotal'), ('max', 'queueDepthMax')]:
                if field in fields and fields[field] is not None:
                    measurement_metrics['queue_depth'].labels(**tags, metric=metric).set(fields[field])

        elif measurement == 'power':
            if 'totalPower' in fields and fields['totalPower'] is not None:
                measurement_metrics['total_power'].labels(**tags).set(fields['totalPower'])

        elif measurement == 'temp':
            if 'temp' in fields and fields['temp'] is not None:
                measurement_metrics['temperature'].labels(**tags).set(fields['temp'])

        elif measurement == 'flashcache':
            # Bytes metrics
            for gauge_m in ['availableBytes', 'allocatedBytes', 'populatedCleanBytes', 'populatedDirtyBytes']:
                if gauge_m in fields and fields[gauge_m] is not None:
                    measurement_metrics['bytes'].labels(**tags, metric=gauge_m).set(fields[gauge_m])
            
            # Component counts
            for comp_m in ['cached_volumes_count', 'cache_drive_count']:
                if comp_m in fields and fields[comp_m] is not None:
                    measurement_metrics['components'].labels(**tags, metric=comp_m).set(fields[comp_m])
                    
            # Ops and Blocks
            for c in FLASHCACHE_REALTIME_COUNTERS:
                if c in fields and fields[c] is not None:
                    if 'Blocks' in c:
                        measurement_metrics['blocks'].labels(**tags, metric=c).set(fields[c])
                    else:
                        measurement_metrics['ops'].labels(**tags, metric=c).set(fields[c])

        # Log successful Prometheus update with timestamp
        # LOG.info(f"Prometheus metrics updated for '{measurement}' at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        import traceback
        LOG.error(f"Error sending {measurement} metrics to Prometheus: {e}\n{traceback.format_exc()}")


#######################
# HELPER FUNCTIONS ####
#######################


def should_collect_config_data():
    """
    Determine if config data should be collected this iteration.

    Uses a smart interval-aware approach that handles different collector intervals:
    - If config interval == collector interval: Always collect (every iteration)
    - If config interval > collector interval: Use iteration-based timing
    - Special case: Always collect on iteration 1 to populate caches immediately
    - Debug mode: Force collection every iteration with --debug-force-config

    Config data changes infrequently, so collect only every N minutes based on
    the relationship between CONFIG_COLLECTION_INTERVAL_MINUTES and CMD.intervalTime.

    Returns True when config data should be collected this iteration.
    """

    # Note: Iteration counter is incremented once per cycle in the main loop

    # Force collection every iteration in debug mode
    if CMD.debug_force_config:
        LOG.debug(f"Config collection: Iteration {_CONFIG_COLLECTION_ITERATION_COUNTER}, forced collection (--debug-force-config)")
        return True

    # Always collect on first iteration to populate caches immediately
    # This ensures volume name correlation cache is available for performance data
    if _CONFIG_COLLECTION_ITERATION_COUNTER == 1:
        LOG.debug("Config collection: Iteration 1, collecting config data (first iteration cache population)")
        return True

    collector_interval_minutes = CMD.intervalTime / 60.0

    if CONFIG_COLLECTION_INTERVAL_MINUTES == collector_interval_minutes:
        # Equal case: collect every iteration since interval matches exactly
        LOG.debug(f"Config collection: Every iteration (intervals match: {CONFIG_COLLECTION_INTERVAL_MINUTES} min)")
        return True
    else:
        # Greater case: config interval > collector interval, use iteration-based timing
        config_interval_iterations = int(CONFIG_COLLECTION_INTERVAL_MINUTES * 60 // CMD.intervalTime)
        should_collect = (_CONFIG_COLLECTION_ITERATION_COUNTER % config_interval_iterations) == 1

        if should_collect:
            LOG.debug(f"Config collection: Iteration {_CONFIG_COLLECTION_ITERATION_COUNTER}, "
                     f"collecting every {config_interval_iterations} iterations "
                     f"({CONFIG_COLLECTION_INTERVAL_MINUTES} min config / {collector_interval_minutes} min collector)")
        else:
            LOG.debug(f"Config collection: Iteration {_CONFIG_COLLECTION_ITERATION_COUNTER}, "
                     f"skipping (next collection in {config_interval_iterations - (_CONFIG_COLLECTION_ITERATION_COUNTER % config_interval_iterations)} iterations)")

        return should_collect



def write_to_outputs(json_body, measurement_type="metrics"):
    """
    Write metrics to configured outputs (Prometheus)

    Args:
        json_body (list): List of measurement dictionaries with tags and fields
        measurement_type (str): Type of measurement for logging purposes
    """
    # Stamp points client-side if caller didn't provide time so retries/batching
    # do not shift the effective measurement timestamp.
    point_time = int(datetime.now(timezone.utc).timestamp())
    for metric in json_body:
        if isinstance(metric, dict) and "time" not in metric:
            metric["time"] = point_time
    

def get_session():
    """
    Returns a session with the appropriate content type and login information.
    :return: Returns a request session for the SANtricity API endpoint
    """
    request_session = CaptureSession()

    username = CMD.username
    password = CMD.password

    request_session.auth = (username, password)
    request_session.headers = {"Accept": "application/json",
                               "Content-Type": "application/json",
                               "netapp-client-type": "collector-" + __version__}

    request_session.verify = not CMD.no_verify_ssl
    return request_session


def _get_live_statistics_snapshot(session, system_id):
    """Fetch live statistics payload once for reuse across collectors."""
    try:
        response = session.get(
            f"{get_controller('sys')}/{system_id}/live-statistics",
            timeout=(6.10, 15),
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # pylint: disable=broad-exception-caught
        LOG.warning("Could not retrieve live statistics snapshot: %s", exc)
        return None


def _extract_live_stats_section(live_stats_payload, section_key):
    """Return list payload for a live statistics section across known payload shapes."""
    if isinstance(live_stats_payload, dict):
        section = live_stats_payload.get(section_key, [])
        return section if isinstance(section, list) else []

    if isinstance(live_stats_payload, list):
        type_map = {
            'volumeStats': 'volume',
            'controllerStats': 'controller',
            'interfaceStats': 'interface'
        }
        mapped_type = type_map.get(section_key)
        if mapped_type:
            return [
                item for item in live_stats_payload
                if isinstance(item, dict) and item.get('type') == mapped_type
            ]

    return []


def _parse_stats_timestamp(stats, default_ts):
    """Parse observedTimeInMS/observedTime from stats payload to epoch seconds."""
    api_ts_val = stats.get('observedTimeInMS')
    if not api_ts_val:
        api_ts_val = stats.get('observedTime')

    if not api_ts_val:
        return float(default_ts)

    try:
        val = float(api_ts_val)
        if val > 100_000_000_000:
            return val / 1000.0
        return val
    except ValueError:
        try:
            if isinstance(api_ts_val, str) and 'T' in api_ts_val:
                iso_str = api_ts_val.replace('Z', '+00:00')
                return datetime.fromisoformat(iso_str).timestamp()
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    return float(default_ts)


def get_controller(query):
    """
    Returns a SANtricity API URL with param-based path.
    :return: Returns a SANtricity API URL path string to storage-systems or firmware
    """
    if query == "sys":
        api_path = '/devmgr/v2/storage-systems'
    elif query == "fw":
        api_path = '/devmgr/v2/firmware/embedded-firmware'
    else:
        LOG.error("Unsupported API path requested")
        raise ValueError(f"Unsupported query type: {query}")
    if (len(CMD.api) == 0) or (CMD.api is None) or (CMD.api == ''):
        storage_controller_ep = 'https://' + \
            DEFAULT_SYSTEM_API_IP + ':' + CMD.api_port + api_path
    elif len(CMD.api) == 1:
        storage_controller_ep = 'https://' + \
            CMD.api[0] + ':' + CMD.api_port + api_path
    else:
        if _CURRENT_CONTROLLER_INDEX is not None:
            controller = _CURRENT_CONTROLLER_INDEX
        else:
            controller = random.randrange(0, 2)
        storage_controller_ep = 'https://' + \
            CMD.api[controller] + ':' + CMD.api_port + \
            api_path
        LOG.info(f"Controller selection: {storage_controller_ep}")
    return storage_controller_ep


def set_current_controller_index(index):
    """
    Set the current controller index for consistent selection within a collection session.
    :param index: Controller index (0 or 1) or None to reset
    """
    global _CURRENT_CONTROLLER_INDEX
    _CURRENT_CONTROLLER_INDEX = index


def get_drive_location(sys_id, session):
    """
    :param sys_id: Storage system ID (WWN) on the controller
    :param session: the session of the thread that calls this definition
    ::return: returns a dictionary containing the disk id matched up against
    the tray id it is located in:
    """
    hardware_list = session.get(
        f"{get_controller('sys')}/{sys_id}/hardware-inventory").json()
    tray_list = hardware_list["trays"]
    drive_list = hardware_list["drives"]
    tray_ids = {}
    drive_location = {}

    for tray in tray_list:
        tray_ids[tray["trayRef"]] = tray["trayId"]

    for drive in drive_list:
        drive_tray = drive["physicalLocation"]["trayRef"]
        tray_id = tray_ids.get(drive_tray)
        if tray_id != "none":
            drive_location[drive["driveRef"]] = [
                tray_id, drive["physicalLocation"]["slot"], str(drive.get("driveMediaType", "unknown"))]
        else:
            LOG.error("Error matching drive to a tray in the storage system")
    return drive_location


@metrics_timer("symbol_stats")
def collect_symbol_stats(system_info):
    """
    Collects temp sensor and PSU consumption (W) and posts them to Prometheus
    :param system_info: The JSON object
    """
    # Set controller for consistent selection within this collection session
    if len(CMD.api) > 1:
        set_current_controller_index(random.randrange(0, 2))

    try:
        session = get_session()
        json_body = list()
        # PSU
        psu_response = session.get(f"{get_controller('sys')}/{sys_id}/symbol/getEnergyStarData",
                                   params={"controller": "auto", "verboseErrorResponse": "false"}, timeout=(6.10, CMD.intervalTime*2)).json()
        
        if psu_response and psu_response.get('energyStarData'):
            psu_total = psu_response['energyStarData'].get('totalPower')
            if psu_total is not None:
                if CMD.showPower:
                    LOG.info("PSU response (total): %s", psu_total)
                item = {
                    "measurement": "power",
                    "tags": {
                        "sys_id": sys_id,
                        "sys_name": sys_name
                    },
                    "fields": {"totalPower": int(psu_total)}
                }
                if not CMD.include or item["measurement"] in CMD.include:
                    json_body.append(item)
                    # Send to Prometheus
                    send_to_prometheus(item["measurement"], item["tags"], item["fields"])
                    LOG.debug(f"Added {item['measurement']} measurement to collection")
                else:
                    LOG.debug(f"Skipped {item['measurement']} measurement (not in --include filter)")
                LOG.info("LOG: PSU data prepared")
        else:
            LOG.debug("LOG: PSU data unavailable or unsupported, skipping power measurement")

        # ENVIRONMENTAL SENSORS
        response = session.get(
            f"{get_controller('sys')}/{sys_id}/symbol/getEnclosureTemperatures",
            params={"controller": "auto", "verboseErrorResponse": "false"},
            timeout=(6.10, CMD.intervalTime*2)).json()
            
        if response and response.get('thermalSensorData'):
            if CMD.showSensor:
                LOG.info("Sensor response: %s", response['thermalSensorData'])
            env_response = order_sensor_response_list(response)
            for i, sensor in enumerate(env_response):
                sensor_id = sensor['thermalSensorRef']
                sensor_order = f"sensor_{i}"
                item = {
                    "measurement": "temp",
                    "tags": {
                        "sensor": sensor_id,
                        "sensor_seq": sensor_order,
                        "sys_id": sys_id,
                        "sys_name": sys_name
                    },
                    "fields": {"temp": int(sensor['currentTemp'])}
                }
                if not CMD.include or item["measurement"] in CMD.include:
                    json_body.append(item)
                    # Send to Prometheus
                    send_to_prometheus(item["measurement"], item["tags"], item["fields"])
            LOG.info("LOG: sensor data prepared")
        else:
            LOG.debug("LOG: sensor data unavailable, skipping temp measurements")

        LOG.debug(f"collect_symbol_stats: Prepared {len(json_body)} measurements")
        write_to_outputs(json_body, "SYMbol V2 PSU and sensor readings")

    except RuntimeError:
        LOG.error(
            f"Error when attempting to post tmp sensors data for {system_info['name']}/{system_info['wwn']}")

    finally:
        # Reset controller selection for next collection session
        set_current_controller_index(None)



def collect_storage_metrics(system_info, live_stats_snapshot=None):
    """
    Collects all defined storage metrics and posts them to Prometheus: drives, system stats,
    interfaces, and volumes
    :param sys: The JSON object of a storage system
    """

    # Set controller for consistent selection within this collection session
    if len(CMD.api) > 1:
        set_current_controller_index(random.randrange(0, 2))

    try:
        session = get_session()
        json_body = list()
        drive_stats_list = session.get(
            f"{get_controller('sys')}/{sys_id}/analysed-drive-statistics").json()
        drive_locations = get_drive_location(sys_id, session)
        if CMD.showDriveNames:
            for stats in drive_stats_list:
                location_send = drive_locations.get(stats["diskId"])
                if location_send is not None:
                    LOG.info(
                        f"Tray{location_send[0]:02.0f}, Slot{location_send[1]:03.0f}")
                else:
                    LOG.warning(
                        f"Could not find location for drive {stats['diskId']}")

        # Get firmware version to determine API capabilities
        fw_resp = session.get(
            f"{get_controller('fw')}/{sys_id}/versions").json()
        fw_cv = fw_resp['codeVersions']
        major_vers = 0
        minor_vers = 0
        for mod in (range(len(fw_cv))):
            if fw_cv[mod]['codeModule'] == 'management':
                parts = (fw_cv[mod]['versionString']).split(".")
                if len(parts) >= 2:
                    major_vers = int(parts[0])
                    minor_vers = int(parts[1])
                break

        # Get SSD wear statistics from the drives endpoint
        ssd_wear_dict = {}
        if major_vers >= 12 or (major_vers == 11 and minor_vers >= 80):
            try:
                drive_response = session.get(f"{get_controller('sys')}/{sys_id}/drives").json()

                for drive in drive_response:
                    if str(drive.get('driveMediaType')).lower() != 'ssd':
                        continue

                    drive_id = drive.get('id') or drive.get('driveRef')
                    ssd_wear = drive.get('ssdWearLife')

                    if drive_id and isinstance(ssd_wear, dict):
                        wear_data = {}
                        if 'spareBlocksRemainingPercent' in ssd_wear:
                            wear_data['spareBlocksRemainingPercent'] = ssd_wear['spareBlocksRemainingPercent']
                        if 'percentEnduranceUsed' in ssd_wear:
                            wear_data['percentEnduranceUsed'] = ssd_wear['percentEnduranceUsed']
                            
                        if wear_data:  # Only store if we have at least one metric
                            ssd_wear_dict[drive_id] = wear_data

                LOG.info(
                    f"Found SSD wear data for {len(ssd_wear_dict)} drives")
            except (requests.exceptions.RequestException, KeyError, ValueError) as e:
                LOG.warning(f"Could not retrieve SSD wear statistics: {e}")
        else:
            version_string = next((fw_cv[mod]['versionString'] for mod in range(len(fw_cv))
                                   if fw_cv[mod]['codeModule'] == 'management'), 'unknown')
            LOG.warning(
                f"SSD wear level ignored for this SANtricity version {version_string}")

        for stats in drive_stats_list:
            pdict = {}
            disk_location_info = drive_locations.get(stats["diskId"])

            # Try to get SSD wear data using diskId
            disk_id = stats.get("diskId")
            vol_group_name = stats.get("volGroupName")

            if disk_id and ssd_wear_dict and disk_id in ssd_wear_dict:
                wear_data = ssd_wear_dict[disk_id]
                pdict = wear_data.copy()  # Copy the wear metrics dictionary
                wear_metrics = []
                if 'spareBlocksRemainingPercent' in wear_data:
                    wear_metrics.append(
                        f"spareBlocks={wear_data['spareBlocksRemainingPercent']}%")
                if 'percentEnduranceUsed' in wear_data:
                    wear_metrics.append(
                        f"enduranceUsed={wear_data['percentEnduranceUsed']}%")
                LOG.debug(
                    f"Found SSD wear data for drive {disk_id}: {', '.join(wear_metrics)}")

            if pdict:
                fields_dict = apply_mapping(stats, DRIVE_MAPPING) | pdict
            else:
                fields_dict = apply_mapping(stats, DRIVE_MAPPING)

            # Apply field type coercion to match Prometheus exporter schema
            # Safely handle disk location info with fallbacks
            drive_media_type = "unknown"
            if disk_location_info is not None and len(disk_location_info) >= 2:
                tray_id = disk_location_info[0]
                slot_id = disk_location_info[1]
                if len(disk_location_info) > 2:
                    drive_media_type = disk_location_info[2]
            else:
                # Fallback to trayRef and driveSlot from stats if location info is unavailable
                tray_id = stats.get('trayRef', 99)
                slot_id = stats.get('driveSlot', 999)

            disk_item = {
                "measurement": "disks",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    "sys_tray": f"{tray_id:02.0f}",
                    "sys_tray_slot": f"{slot_id:03.0f}",
                    "driveMediaType": drive_media_type
                },
                "fields": fields_dict
            }

            # Add volume group tag if available
            if vol_group_name is not None:
                disk_item["tags"]["vol_group_name"] = vol_group_name
            if CMD.showDriveMetrics:
                LOG.info("Drive payload: %s", disk_item)
            if not CMD.include or disk_item["measurement"] in CMD.include:
                json_body.append(disk_item)
                # Send to Prometheus
                send_to_prometheus(disk_item["measurement"], disk_item["tags"], disk_item["fields"])


        # Interface collection: live-only 
        interface_stats_list = _extract_live_stats_section(live_stats_snapshot, 'interfaceStats')
        if not interface_stats_list:
            LOG.info("Live interface stats unavailable this iteration.")
        else:
            if CMD.showInterfaceNames:
                for stats in interface_stats_list:
                    LOG.info(stats.get("interfaceId", stats.get("id", "unknown")))

            current_ts = time.time()
            produced_if_points = 0
            for stats in interface_stats_list:
                interface_id = stats.get('interfaceId', stats.get('id', 'unknown'))
                prev_stats = _INTERFACE_STATS_CACHE.get(interface_id)

                current_values = {
                    'timestamp': _parse_stats_timestamp(stats, current_ts),
                    'readOps': float(stats.get('readOps', 0)),
                    'writeOps': float(stats.get('writeOps', 0)),
                    'otherOps': float(stats.get('otherOps', 0)),
                    'readBytes': float(stats.get('readBytes', 0)),
                    'writeBytes': float(stats.get('writeBytes', 0)),
                    'readTimeTotal': float(stats.get('readTimeTotal', 0)),
                    'writeTimeTotal': float(stats.get('writeTimeTotal', 0)),
                    'otherTimeTotal': float(stats.get('otherTimeTotal', 0)),
                }
                _INTERFACE_STATS_CACHE[interface_id] = current_values

                if not prev_stats:
                    continue

                if (current_values['readOps'] < prev_stats['readOps'] or
                    current_values['writeOps'] < prev_stats['writeOps'] or
                    current_values['readBytes'] < prev_stats['readBytes'] or
                    current_values['writeBytes'] < prev_stats['writeBytes']):
                    LOG.debug(f"Counter reset/rollback detected for interface {interface_id}, skipping")
                    continue

                dt = current_values['timestamp'] - prev_stats['timestamp']
                if dt <= 0:
                    dt = 1

                delta_read_ops = current_values['readOps'] - prev_stats['readOps']
                delta_write_ops = current_values['writeOps'] - prev_stats['writeOps']
                delta_other_ops = current_values['otherOps'] - prev_stats['otherOps']
                delta_read_bytes = current_values['readBytes'] - prev_stats['readBytes']
                delta_write_bytes = current_values['writeBytes'] - prev_stats['writeBytes']
                delta_read_time = current_values['readTimeTotal'] - prev_stats['readTimeTotal']
                delta_write_time = current_values['writeTimeTotal'] - prev_stats['writeTimeTotal']
                delta_other_time = current_values['otherTimeTotal'] - prev_stats['otherTimeTotal']

                if delta_read_time < 0 or delta_write_time < 0 or delta_other_time < 0:
                    LOG.debug("Time counter reset/rollback detected for interface %s, skipping", interface_id)
                    continue

                read_iops = delta_read_ops / dt
                write_iops = delta_write_ops / dt
                other_iops = delta_other_ops / dt
                combined_iops = (delta_read_ops + delta_write_ops + delta_other_ops) / dt
                read_throughput = delta_read_bytes / dt
                write_throughput = delta_write_bytes / dt
                combined_throughput = (delta_read_bytes + delta_write_bytes) / dt

                read_response_time = (delta_read_time / delta_read_ops) * LIVE_TIME_COUNTER_TO_MS if delta_read_ops > 0 else 0
                write_response_time = (delta_write_time / delta_write_ops) * LIVE_TIME_COUNTER_TO_MS if delta_write_ops > 0 else 0
                total_ops = delta_read_ops + delta_write_ops + delta_other_ops
                total_time = delta_read_time + delta_write_time + delta_other_time
                combined_response_time = (total_time / total_ops) * LIVE_TIME_COUNTER_TO_MS if total_ops > 0 else 0

                read_response_time = max(0.0, read_response_time)
                write_response_time = max(0.0, write_response_time)
                combined_response_time = max(0.0, combined_response_time)

                interface_fields = {
                    'averageReadOpSize': delta_read_bytes / delta_read_ops if delta_read_ops > 0 else 0,
                    'averageWriteOpSize': delta_write_bytes / delta_write_ops if delta_write_ops > 0 else 0,
                    'combinedIOps': combined_iops,
                    'combinedResponseTime': combined_response_time,
                    'combinedThroughput': combined_throughput,
                    'otherIOps': other_iops,
                    'queueDepthMax': float(stats.get('queueDepthMax', 0)),
                    'queueDepthTotal': float(stats.get('queueDepthTotal', 0)),
                    'readIOps': read_iops,
                    'readOps': delta_read_ops,
                    'readResponseTime': read_response_time,
                    'readThroughput': read_throughput,
                    'writeIOps': write_iops,
                    'writeOps': delta_write_ops,
                    'writeResponseTime': write_response_time,
                    'writeThroughput': write_throughput,
                }
                if_item = {
                    "measurement": "interface",
                    "tags": {
                        "sys_id": sys_id,
                        "sys_name": sys_name,
                        "interface_id": interface_id,
                        "channel_type": stats.get("channelType", "unknown")
                    },
                    "fields": interface_fields
                }

                if CMD.showInterfaceMetrics:
                    LOG.info("Interface payload: %s", if_item)

                if not CMD.include or if_item["measurement"] in CMD.include:
                    json_body.append(if_item)
                    send_to_prometheus(if_item["measurement"], if_item["tags"], if_item["fields"])
                    produced_if_points += 1

            if produced_if_points == 0:
                LOG.info("No live interface deltas produced this iteration (first run or counter reset)")


        if live_stats_snapshot is None:
            live_stats_snapshot = _get_live_statistics_snapshot(session, sys_id)

        volume_stats_list = _extract_live_stats_section(live_stats_snapshot, 'volumeStats')
        if not volume_stats_list:
            LOG.info("Live volume stats unavailable this iteration.")
        else:
            if CMD.showVolumeNames:
                for stats in volume_stats_list:
                    LOG.info(stats.get("volumeName", stats.get("volumeId", "unknown")))

            current_ts = time.time()
            produced_points = 0
            for stats in volume_stats_list:
                volume_name = stats.get('volumeName', stats.get('volumeId', 'unknown'))
                if volume_name.startswith('repos_'):
                    LOG.debug(f"Skipping repository volume {volume_name}")
                    continue

                vol_ref = stats.get('volumeId') or stats.get('volumeRef') or volume_name
                prev_stats = _VOLUME_STATS_CACHE.get(vol_ref)

                current_values = {
                    'timestamp': _parse_stats_timestamp(stats, current_ts),
                    'readOps': float(stats.get('readOps', 0)),
                    'writeOps': float(stats.get('writeOps', 0)),
                    'otherOps': float(stats.get('otherOps', 0)),
                    'readBytes': float(stats.get('readBytes', 0)),
                    'writeBytes': float(stats.get('writeBytes', 0)),
                    'readTimeTotal': float(stats.get('readTimeTotal', 0)),
                    'writeTimeTotal': float(stats.get('writeTimeTotal', 0)),
                    'otherTimeTotal': float(stats.get('otherTimeTotal', 0)),
                    'flashCacheReadHitBytes': float(stats.get('flashCacheReadHitBytes', 0)),
                    'flashCacheReadHitOps': float(stats.get('flashCacheReadHitOps', 0)),
                    'flashCacheReadHitTimeTotal': float(stats.get('flashCacheReadHitTimeTotal', 0)),
                    'readHitBytes': float(stats.get('readHitBytes', 0)),
                    'readHitOps': float(stats.get('readHitOps', 0)),
                    'writeHitBytes': float(stats.get('writeHitBytes', 0)),
                    'writeHitOps': float(stats.get('writeHitOps', 0)),
                    'queueDepthMax': float(stats.get('queueDepthMax', 0)),
                    'queueDepthTotal': float(stats.get('queueDepthTotal', 0)),
                }
                _VOLUME_STATS_CACHE[vol_ref] = current_values

                if not prev_stats:
                    continue

                if (current_values['readOps'] < prev_stats['readOps'] or
                    current_values['writeOps'] < prev_stats['writeOps'] or
                    current_values['readBytes'] < prev_stats['readBytes'] or
                    current_values['writeBytes'] < prev_stats['writeBytes']):
                    LOG.debug(f"Counter reset/rollback detected for volume {volume_name}, skipping")
                    continue

                dt = current_values['timestamp'] - prev_stats['timestamp']
                if dt <= 0:
                    dt = 1

                delta_read_ops = current_values['readOps'] - prev_stats['readOps']
                delta_write_ops = current_values['writeOps'] - prev_stats['writeOps']
                delta_other_ops = current_values['otherOps'] - prev_stats['otherOps']
                delta_read_bytes = current_values['readBytes'] - prev_stats['readBytes']
                delta_write_bytes = current_values['writeBytes'] - prev_stats['writeBytes']
                delta_read_time = current_values['readTimeTotal'] - prev_stats['readTimeTotal']
                delta_write_time = current_values['writeTimeTotal'] - prev_stats['writeTimeTotal']
                delta_other_time = current_values['otherTimeTotal'] - prev_stats['otherTimeTotal']
                delta_fc_hit_bytes = current_values['flashCacheReadHitBytes'] - prev_stats['flashCacheReadHitBytes']
                delta_fc_hit_ops = current_values['flashCacheReadHitOps'] - prev_stats['flashCacheReadHitOps']
                delta_fc_hit_time = current_values['flashCacheReadHitTimeTotal'] - prev_stats['flashCacheReadHitTimeTotal']
                delta_read_hit_bytes = current_values['readHitBytes'] - prev_stats['readHitBytes']
                delta_read_hit_ops = current_values['readHitOps'] - prev_stats['readHitOps']
                delta_write_hit_bytes = current_values['writeHitBytes'] - prev_stats['writeHitBytes']
                delta_write_hit_ops = current_values['writeHitOps'] - prev_stats['writeHitOps']

                if (delta_read_time < 0 or delta_write_time < 0 or delta_other_time < 0 or
                    delta_fc_hit_time < 0):
                    LOG.debug("Time counter reset/rollback detected for volume %s, skipping", volume_name)
                    continue

                read_iops = delta_read_ops / dt
                write_iops = delta_write_ops / dt
                other_iops = delta_other_ops / dt
                combined_iops = (delta_read_ops + delta_write_ops + delta_other_ops) / dt
                read_throughput = delta_read_bytes / dt
                write_throughput = delta_write_bytes / dt
                combined_throughput = (delta_read_bytes + delta_write_bytes) / dt

                read_response_time = (delta_read_time / delta_read_ops) * LIVE_TIME_COUNTER_TO_MS if delta_read_ops > 0 else 0
                write_response_time = (delta_write_time / delta_write_ops) * LIVE_TIME_COUNTER_TO_MS if delta_write_ops > 0 else 0
                total_ops = delta_read_ops + delta_write_ops + delta_other_ops
                total_time = delta_read_time + delta_write_time + delta_other_time
                combined_response_time = (total_time / total_ops) * LIVE_TIME_COUNTER_TO_MS if total_ops > 0 else 0

                avg_read_op_size = delta_read_bytes / delta_read_ops if delta_read_ops > 0 else 0
                avg_write_op_size = delta_write_bytes / delta_write_ops if delta_write_ops > 0 else 0
                read_cache_util = (delta_read_hit_bytes / delta_read_bytes * 100.0) if delta_read_bytes > 0 else 0
                write_cache_util = (delta_write_hit_bytes / delta_write_bytes * 100.0) if delta_write_bytes > 0 else 0
                flash_cache_hit_pct = (delta_fc_hit_ops / delta_read_ops * 100.0) if delta_read_ops > 0 else 0
                flash_cache_resp = (delta_fc_hit_time / delta_fc_hit_ops) * LIVE_TIME_COUNTER_TO_MS if delta_fc_hit_ops > 0 else 0

                read_response_time = max(0.0, read_response_time)
                write_response_time = max(0.0, write_response_time)
                combined_response_time = max(0.0, combined_response_time)
                flash_cache_resp = max(0.0, flash_cache_resp)

                host_names = []
                volume_obj = _MAPPABLE_OBJECTS_CACHE.get(vol_ref)
                if not volume_obj:
                    for _, obj in _MAPPABLE_OBJECTS_CACHE.items():
                        if obj.get('label') == volume_name:
                            volume_obj = obj
                            break

                if volume_obj:
                    list_of_mappings = volume_obj.get('listOfMappings', [])
                    for mapping in list_of_mappings:
                        map_ref = mapping.get('mapRef')
                        if map_ref and map_ref in _HOSTS_CACHE:
                            for host_info in _HOSTS_CACHE[map_ref]:
                                host_name = host_info.get('name', 'unknown')
                                if host_name not in host_names:
                                    host_names.append(host_name)

                volume_fields = {
                    'averageReadOpSize': avg_read_op_size,
                    'averageWriteOpSize': avg_write_op_size,
                    'combinedIOps': combined_iops,
                    'combinedResponseTime': combined_response_time,
                    'combinedThroughput': combined_throughput,
                    'flashCacheHitPct': flash_cache_hit_pct,
                    'flashCacheReadHitBytes': delta_fc_hit_bytes / dt if dt > 0 else 0,
                    'flashCacheReadHitOps': delta_fc_hit_ops / dt if dt > 0 else 0,
                    'flashCacheReadResponseTime': flash_cache_resp,
                    'flashCacheReadThroughput': delta_fc_hit_bytes / dt if dt > 0 else 0,
                    'otherIOps': other_iops,
                    'queueDepthMax': current_values['queueDepthMax'],
                    'queueDepthTotal': current_values['queueDepthTotal'],
                    'readCacheUtilization': read_cache_util,
                    'readHitBytes': delta_read_hit_bytes / dt if dt > 0 else 0,
                    'readHitOps': delta_read_hit_ops / dt if dt > 0 else 0,
                    'readIOps': read_iops,
                    'readOps': delta_read_ops,
                    'readPhysicalIOps': read_iops,
                    'readResponseTime': read_response_time,
                    'readThroughput': read_throughput,
                    'writeCacheUtilization': write_cache_util,
                    'writeHitBytes': delta_write_hit_bytes / dt if dt > 0 else 0,
                    'writeHitOps': delta_write_hit_ops / dt if dt > 0 else 0,
                    'writeIOps': write_iops,
                    'writeOps': delta_write_ops,
                    'writePhysicalIOps': write_iops,
                    'writeResponseTime': write_response_time,
                    'writeThroughput': write_throughput,
                    'mapped_host_names': ','.join(host_names) if host_names else '',
                    'mapped_host_count': len(host_names)
                }
                vol_item = {
                    "measurement": "volumes",
                    "tags": {
                        "sys_id": sys_id,
                        "sys_name": sys_name,
                        "vol_name": volume_name
                    },
                    "fields": volume_fields
                }

                if CMD.showVolumeMetrics:
                    LOG.info("Volume payload: %s", vol_item)

                if not CMD.include or vol_item["measurement"] in CMD.include:
                    json_body.append(vol_item)
                    send_to_prometheus(vol_item["measurement"], vol_item["tags"], vol_item["fields"])
                    produced_points += 1

            if produced_points == 0:
                LOG.info("No live volume deltas produced this iteration (first run or counter reset)")

        LOG.debug(f"collect_storage_metrics: Prepared {len(json_body)} measurements")
        write_to_outputs(json_body, "storage metrics")

    except RuntimeError:
        LOG.error(
            f"Error when attempting to post statistics for {system_info['name']}/{system_info['wwn']}")

    finally:
        # Reset controller selection for next collection session
        set_current_controller_index(None)


def create_failure_dict_item(sys_id, sys_name, fail_type, obj_ref, obj_type, is_active, the_time):
    item = {
        "measurement": "failures",
        "tags": {
            "sys_id": sys_id,
            "sys_name": sys_name,
            "failure_type": fail_type,
            "object_ref": obj_ref,
            "object_type": obj_type,
            "active": is_active
        },
        "fields": {
            "name_of": sys_name,
            "type_of": fail_type
        },
        "time": the_time
    }
    return item


@metrics_timer("system_failures")
def collect_system_failures(system_info, checksums):
    """
    Top-level function that collects failure data once and sends to Prometheus.
    Eliminates duplicate API calls when both outputs are enabled.
    """
    try:
        session = get_session()
        sys_id = system_info["wwn"]
        sys_name = system_info["name"]

        # Single API call to get current failures
        failure_response = session.get(
            f"{get_controller('sys')}/{sys_id}/failures").json()

        if PROMETHEUS_AVAILABLE:
            create_prometheus_failure_alerts(sys_id, sys_name, failure_response)


    except RuntimeError:
        LOG.error(f"Error when attempting to collect failure data for {system_info['name']}/{system_info['wwn']}")



def create_prometheus_failure_alerts(sys_id, sys_name, failure_response):
    """
    Create Prometheus metrics for current failures (for alerting).
    Always runs regardless of checksums for real-time alerting.
    """
    if not PROMETHEUS_AVAILABLE or 'failures' not in prometheus_metrics:
        return

    failure_gauge = prometheus_metrics['failures']['active_failures']

    # Clear existing metrics for this system first
    # Note: Prometheus client doesn't have a direct way to clear specific labels,
    # so we set all current failure combinations to their actual values

    # Group failures by type, object_type, and object_ref for detailed metrics
    failure_counts = {}
    for failure in failure_response:
        failure_type = failure.get("failureType", "unknown")
        object_type = failure.get("objectType", "unknown")
        object_ref = failure.get("objectRef", "unknown")
        # Use object_ref directly, but handle None/null values
        if object_ref is None:
            object_ref = ""
        key = (failure_type, object_type, object_ref)
        failure_counts[key] = failure_counts.get(key, 0) + 1

    if not failure_counts:
        # Emit a baseline zero metric so absent() alerts don't trigger incorrectly
        failure_gauge.labels(
            sys_id=sys_id,
            sys_name=sys_name,
            failure_type="none",
            object_type="none",
            object_ref=""
        ).set(0.0)
    else:
        # Set Prometheus metrics for active failures
        for (failure_type, object_type, object_ref), count in failure_counts.items():
            failure_gauge.labels(
                sys_id=sys_id,
                sys_name=sys_name,
                failure_type=failure_type,
                object_type=object_type,
                object_ref=object_ref
            ).set(count)

    # If no failures, ensure we still have a metric with 0
    if not failure_counts:
        failure_gauge.labels(
            sys_id=sys_id,
            sys_name=sys_name,
            failure_type="none",
            object_type="none",
            object_ref=""
        ).set(0)

    LOG.debug(f"Updated Prometheus failure metrics: {len(failure_counts)} failure types for system {sys_name}")


@metrics_timer("interface_alerts")
def collect_interface_alerts(system_info):
    """Collect interface alert information and update Prometheus metrics."""
    if not PROMETHEUS_AVAILABLE:
        return

    if 'interface_alerts' not in prometheus_metrics:
        logging.warning("Prometheus metric 'interface_alerts' not available, skipping interface alert collection")
        return

    sys_id = system_info.get("wwn", "unknown")
    sys_name = system_info.get("name", "unknown")

    try:
        session = get_session()
        interface_alert_gauge = prometheus_metrics['interface_alerts']['interface_alert']

        response = session.get(
            f"{get_controller('sys')}/{sys_id}/graph/xpath-filter?query=/controller"
        )
        response.raise_for_status()
        controllers_response = response.json()

        alert_count = 0

        for controller in controllers_response:
            controller_id = _map_controller_id(controller.get('controllerRef', 'unknown'))

            # Process management interfaces (wan0, wan1, etc.)
            net_interfaces = controller.get('netInterfaces', [])
            for interface in net_interfaces:
                iface_type = interface.get('interfaceType', '').lower()

                if iface_type not in INTERFACE_ALERT_CONFIG:
                    LOG.debug("Skipping unconfigured management interface type: %s", iface_type)
                    continue

                config = INTERFACE_ALERT_CONFIG[iface_type]
                if not config.get('enabled', False):
                    continue

                eth_data = interface.get('ethernet', {})
                interface_name = eth_data.get('interfaceName', 'unknown')
                channel = str(eth_data.get('channel', 0))
                interface_ref = eth_data.get('interfaceRef', 'unknown')
                label_values = {
                    'sys_id': sys_id,
                    'sys_name': sys_name,
                    'interface_ref': interface_ref,
                    'channel': channel,
                    'interface_type': f"mgmt_{iface_type}_{interface_name}",
                }

                current_obj = interface
                for path_segment in config['alert_paths']:
                    if isinstance(current_obj, dict) and path_segment in current_obj:
                        current_obj = current_obj[path_segment]
                    else:
                        current_obj = None
                        break

                status_value = str(current_obj).lower() if current_obj is not None else ''
                is_alert = status_value in config['alert_values']
                interface_alert_gauge.labels(**label_values).set(1.0 if is_alert else 0.0)

                if is_alert:
                    alert_count += 1
                    LOG.info(
                        "Management interface alert: %s controller %s %s (%s) ch=%s status=%s",
                        sys_name,
                        controller_id,
                        interface_name,
                        iface_type,
                        channel,
                        status_value,
                    )

            # Process storage service interfaces (iSCSI, FC, IB, SAS)
            host_interfaces = controller.get('hostInterfaces', [])
            for interface in host_interfaces:
                iface_type = interface.get('interfaceType', '').lower()

                if iface_type not in INTERFACE_ALERT_CONFIG:
                    LOG.debug("Skipping unconfigured storage interface type: %s", iface_type)
                    continue

                config = INTERFACE_ALERT_CONFIG[iface_type]
                if not config.get('enabled', False):
                    continue

                type_obj = interface.get(iface_type, {})
                if not isinstance(type_obj, dict) or not type_obj:
                    continue

                current_obj = type_obj
                for path_segment in config['alert_paths']:
                    if isinstance(current_obj, dict) and path_segment in current_obj:
                        current_obj = current_obj[path_segment]
                    else:
                        current_obj = None
                        break

                status_value = str(current_obj).lower() if current_obj is not None else ''
                interface_ref = type_obj.get('interfaceRef', 'unknown')
                channel = str(type_obj.get('channel', 0))

                if iface_type == 'iscsi':
                    ethernet_data = type_obj.get('interfaceData', {}).get('ethernetData', {})
                    mac_address = ethernet_data.get('macAddress', '')
                    interface_id = f"{iface_type}_ch{channel}_{mac_address}"
                elif iface_type == 'ib':
                    global_id = type_obj.get('globalIdentifier', 'unknown')
                    interface_id = f"{iface_type}_ch{channel}_{global_id}"
                else:
                    interface_id = f"{iface_type}_ch{channel}_{interface_ref}"

                label_values = {
                    'sys_id': sys_id,
                    'sys_name': sys_name,
                    'interface_ref': interface_ref,
                    'channel': channel,
                    'interface_type': interface_id,
                }

                is_alert = status_value in config['alert_values']
                interface_alert_gauge.labels(**label_values).set(1.0 if is_alert else 0.0)

                if is_alert:
                    alert_count += 1
                    LOG.info(
                        "Storage interface alert: %s controller %s %s status=%s",
                        sys_name,
                        controller_id,
                        interface_id,
                        status_value,
                    )

        if alert_count == 0:
            interface_alert_gauge.labels(
                sys_id=sys_id,
                sys_name=sys_name,
                interface_ref="none",
                channel="0",
                interface_type="healthy",
            ).set(0.0)

        LOG.debug(
            "Updated Prometheus interface alert metrics: %d alerts for system %s",
            alert_count,
            sys_name,
        )

    except (requests.RequestException, ValueError, KeyError) as exc:
        LOG.warning(
            "Failed to collect interface alerts for system %s: %s",
            sys_name,
            exc,
        )


@metrics_timer("config_workloads")
def collect_config_workloads(system_info):
    """
    Collects workload configuration information 
    :param system_info: The JSON object of a storage_system
    """

    # Early exit if not a config collection interval
    if not should_collect_config_data():
        LOG.info("Skipping config_workloads collection - not a scheduled interval (collected every 15 minutes)")
        return

    try:
        # Set controller for consistent selection within this collection session
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))

        session = get_session()
        json_body = list()

        # Get workload configuration data from the API
        workloads_response = session.get(f"{get_controller('sys')}/{sys_id}/workloads").json()
        LOG.debug(f"Retrieved {len(workloads_response)} workload configurations")

        for workload in workloads_response:
            # Flatten workloadAttributes manually before applying mapping
            attributes = workload.pop("workloadAttributes", [])
            for attr in attributes:
                val = attr.get("value")
                if isinstance(val, str) and val.lower() in ("true", "false"):
                    val = val.lower() == "true"
                workload[f"workloadAttributes_{attr.get('key')}"] = val
            
            config_fields = apply_mapping(workload, CONFIG_WORKLOADS_MAPPING)
            workload_config_item = {
                "measurement": "config_workloads",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    "id": workload.get("id", "unknown"),
                    "name": workload.get("name", "unknown")
                },
                "fields": config_fields
            }

            if not CMD.include or workload_config_item["measurement"] in CMD.include:
                if PROMETHEUS_AVAILABLE and "config_workloads" in prometheus_metrics:
                    try:
                        prometheus_metrics["config_workloads"]["info"].labels(**workload_config_item["tags"]).set(1.0)
                    except Exception as e:
                        LOG.error(f"Prometheus label error: {e}")
                json_body.append(workload_config_item)
                LOG.debug(f"Added config_workloads measurement for workload {workload.get('name', 'unknown')}")
            else:
                LOG.debug("Skipped config_workloads measurement (not in --include filter)")

    finally:
        # Reset controller selection for next collection session
        set_current_controller_index(None)

@metrics_timer("config_volumes")

def collect_config_volume_mappings(system_info):
    '''Collect volume to host mappings and expose as metrics'''
    try:
        sys_id = system_info.get('wwn', system_info.get('id', 'unknown')) if isinstance(system_info, dict) else str(system_info)
        system_id_val = sys_id
        
        url = f"{get_controller('sys')}/{system_id_val}/volume-mappings"
        session = get_session()
        r = session.get(url)
        if r.status_code == 200:
            mappings = r.json()
            for mapping in mappings:
                if 'lunMappingRef' in mapping and 'lun' in mapping and 'volumeRef' in mapping and 'mapRef' in mapping:
                    item_tags = {
                        'storage_system': system_id_val,
                        'storage_system_name': system_info.get('name', 'unknown') if isinstance(system_info, dict) else 'unknown',
                        'lun_mapping_ref': str(mapping['lunMappingRef']),
                        'lun': str(mapping['lun']),
                        'volume_ref': str(mapping['volumeRef']),
                        'type': str(mapping.get('type', 'unknown')),
                        'map_ref': str(mapping['mapRef'])
                    }
                    if 'collect_config_volume_mappings' in prometheus_metrics and 'info' in prometheus_metrics['collect_config_volume_mappings']:
                        prometheus_metrics['collect_config_volume_mappings']['info'].labels(**item_tags).set(1.0)
    except Exception as e:
        LOG.error('Failed to collect volume mappings for system %s: %s' % (system_id_val if 'system_id_val' in locals() else 'unknown', e))


def _map_controller_id(cid: str) -> str:
    """Map the long 24-character hexadecimal controller ID to 'A' or 'B'."""
    if not cid:
        return 'unknown'
    cid_str = str(cid)
    if cid_str == "070000000000000000000001":
        return "A"
    elif cid_str == "070000000000000000000002":
        return "B"
    return cid_str

@metrics_timer("config_controllers")
def collect_config_controllers(system_info):
    """
    Collects controller configuration information using the upstream santricity_client reports.
    """
    if not should_collect_config_data():
        LOG.info("Skipping config_controllers collection - not a scheduled interval")
        return

    try:
        import random
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))

        session = get_session()
        sys_id = system_info.get("wwn", system_info.get("id"))
        sys_name = system_info.get("name", "unknown")

        class EPCClient:
            def request(self, method, url, **kwargs):
                if url.startswith("/"):
                    url = url[1:]
                req_kwargs = {}
                if "params" in kwargs:
                    req_kwargs["params"] = kwargs["params"]
                if "json_payload" in kwargs:
                    req_kwargs["json"] = kwargs["json_payload"]
                if "data_payload" in kwargs:
                    req_kwargs["data"] = kwargs["data_payload"]
                
                full_url = f"{get_controller('sys')}/{sys_id}/{url}"
                if method.upper() == "GET":
                    return session.get(full_url, **req_kwargs).json()
                elif method.upper() == "POST":
                    return session.post(full_url, **req_kwargs).json()
                else:
                    return session.request(method, full_url, **req_kwargs).json()

        try:
            from santricity_client.reports.controllers import controllers_report
            from santricity_client.resources.interfaces import InterfacesResource
        except ImportError:
            # Fallback if santricity_client is not copied exactly
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from santricity_client.reports.controllers import controllers_report
            from santricity_client.resources.interfaces import InterfacesResource

        client = EPCClient()
        client.interfaces = InterfacesResource(client)

        results = controllers_report(client)
        for row in results:
            tags = {
                "sys_id": sys_id,
                "sys_name": sys_name,
                "controller_id": _map_controller_id(row.get("id", "unknown")),
                "controller_ref": str(row.get("controller_ref", "unknown")),
                "physical_location_label": str(row.get("physical_location_label", "unknown"))
            }
            if 'config_controllers' in prometheus_metrics and 'info' in prometheus_metrics['config_controllers']:
                prometheus_metrics['config_controllers']['info'].labels(**tags).set(1.0)
                
    except Exception as e:
        LOG.error(f"Failed to collect config_controllers: {e}")

@metrics_timer("config_interfaces")
def collect_config_interfaces(system_info):
    """
    Collects hostside interface configuration information.
    """
    if not should_collect_config_data():
        LOG.info("Skipping config_interfaces collection - not a scheduled interval")
        return

    try:
        import random
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))

        session = get_session()
        sys_id = system_info.get("wwn", system_info.get("id"))
        sys_name = system_info.get("name", "unknown")

        class EPCClient:
            def request(self, method, url, **kwargs):
                if url.startswith("/"):
                    url = url[1:]
                req_kwargs = {}
                if "params" in kwargs:
                    req_kwargs["params"] = kwargs["params"]
                if "json_payload" in kwargs:
                    req_kwargs["json"] = kwargs["json_payload"]
                if "data_payload" in kwargs:
                    req_kwargs["data"] = kwargs["data_payload"]
                
                full_url = f"{get_controller('sys')}/{sys_id}/{url}"
                if method.upper() == "GET":
                    return session.get(full_url, **req_kwargs).json()
                elif method.upper() == "POST":
                    return session.post(full_url, **req_kwargs).json()
                else:
                    return session.request(method, full_url, **req_kwargs).json()

        try:
            from santricity_client.reports.interfaces_report import hostside_interfaces_report
            from santricity_client.resources.interfaces import InterfacesResource
        except ImportError:
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
            from santricity_client.reports.interfaces_report import hostside_interfaces_report
            from santricity_client.resources.interfaces import InterfacesResource

        client = EPCClient()
        client.interfaces = InterfacesResource(client)

        results = hostside_interfaces_report(client)
        for row in results:
            tags = {
                "sys_id": sys_id,
                "sys_name": sys_name,
                "interface_id": str(row.get("interface_id", "unknown")),
                "controller_id": _map_controller_id(row.get("controller_id", "unknown")),
                "interface_ref": str(row.get("interface_ref", "unknown")),
                "protocol": str(row.get("protocol", "unknown"))
            }
            if 'config_interfaces' in prometheus_metrics and 'info' in prometheus_metrics['config_interfaces']:
                prometheus_metrics['config_interfaces']['info'].labels(**tags).set(1.0)
                
    except Exception as e:
        LOG.error(f"Failed to collect config_interfaces: {e}")

@metrics_timer("config_system")
def collect_config_system(system_info):
    """
    Collects system overview information
    """
    if not should_collect_config_data():
        LOG.info("Skipping config_system collection - not a scheduled interval")
        return
        
    try:
        sys_id = system_info.get("wwn", system_info.get("id"))
        sys_name = system_info.get("name", "unknown")
        
        tags = {
            "storage_system": sys_id,
            "storage_system_name": sys_name
        }
        
        if 'config_system' in prometheus_metrics:
            # 1) Populate info gauge (metadata and strings)
            if 'info' in prometheus_metrics['config_system']:
                metric_tags = dict(tags)
                for key, nice_name, conv_func in STORAGE_SYSTEM_INFO_KEYS:
                    val = system_info.get(key, "")
                    if conv_func and val:
                        try:
                            val = conv_func(val)
                        except Exception:
                            pass
                    metric_tags[nice_name] = str(val)
                prometheus_metrics['config_system']['info'].labels(**metric_tags).set(1.0)
            
            # 2) Populate independent numeric gauges for changing stats
            for key, nice_name, conv_func in STORAGE_SYSTEM_GAUGE_KEYS:
                val = system_info.get(key)
                if val is not None:
                    if conv_func:
                        try:
                            val = conv_func(val)
                        except Exception:
                            pass
                    
                    try:
                        fval = float(val)
                        if nice_name in prometheus_metrics['config_system']:
                            prometheus_metrics['config_system'][nice_name].labels(**tags).set(fval)
                    except (ValueError, TypeError):
                        continue
            
    except Exception as e:
        LOG.error('Failed to collect system info for %s: %s' % (sys_name, e))


def collect_config_volumes(system_info):
    """
    Collects volume configuration information and posts it to Prometheus
    :param system_info: The JSON object of a storage_system
    """

    # Early exit if not a config collection interval
    if not should_collect_config_data():
        LOG.info("Skipping config_volumes collection - not a scheduled interval (collected every 15 minutes)")
        return

    try:
        # Set controller for consistent selection within this collection session
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))

        session = get_session()
        json_body = list()

        # Get volume configuration data from the API
        volumes_response = session.get(f"{get_controller('sys')}/{sys_id}/volumes").json()

        # Use mega-cache for host mapping resolution (consistent with config collection timing)
        # Build volumeRef -> [host_names] mapping from mega-cache
        volume_to_hosts = {}

        # Use _MAPPABLE_OBJECTS_CACHE and _HOSTS_CACHE populated by config collection
        for volume_ref, volume_obj in _MAPPABLE_OBJECTS_CACHE.items():
            list_of_mappings = volume_obj.get('listOfMappings', [])
            for mapping in list_of_mappings:
                map_ref = mapping.get('mapRef')
                if map_ref and map_ref in _HOSTS_CACHE:
                    # _HOSTS_CACHE now contains lists of hosts per cluster
                    host_list = _HOSTS_CACHE[map_ref]
                    if volume_ref not in volume_to_hosts:
                        volume_to_hosts[volume_ref] = []
                    # Add all hosts in the cluster to this volume
                    for host_info in host_list:
                        host_name = host_info.get('name', 'unknown')
                        if host_name not in volume_to_hosts[volume_ref]:  # Avoid duplicates
                            volume_to_hosts[volume_ref].append(host_name)

        try:
            snapshot_groups_response = session.get(f"{get_controller('sys')}/{sys_id}/snapshot-groups").json()
            repository_capacity = sum(float(g.get('repositoryCapacity', 0)) for g in snapshot_groups_response if isinstance(g, dict))
        except Exception as e:
            LOG.error(f"Failed to fetch snapshot-groups: {e}")
            repository_capacity = 0.0

        try:
            snapshot_images_response = session.get(f"{get_controller('sys')}/{sys_id}/snapshot-images").json()
            snapshot_count = len([x for x in snapshot_images_response if isinstance(x, dict)]) if isinstance(snapshot_images_response, list) else 0
        except Exception as e:
            LOG.error(f"Failed to fetch snapshot-images: {e}")
            snapshot_count = 0

        LOG.debug(f"Retrieved {len(volumes_response)} volume configurations, {snapshot_count} snapshot images, capacity {repository_capacity}")
        LOG.debug(f"Using cached data: {len(_HOSTS_CACHE)} hosts, {len(_MAPPABLE_OBJECTS_CACHE)} mappable objects")

        volume_count = 0

        for volume in volumes_response:
            # Skip snapshot repository volumes
            if volume.get('name', '').startswith('repos_'):
                LOG.debug(f"Skipping repository volume config {volume.get('name')}")
                continue

            volume_count += 1

            # Add computed host mapping fields to the volume object
            volume_ref = volume.get('volumeRef')
            if volume_ref and volume_ref in volume_to_hosts:
                host_names = volume_to_hosts[volume_ref]
                volume['mapped_host_names'] = ','.join(host_names)
                volume['mapped_host_count'] = len(host_names)
            else:
                volume['mapped_host_names'] = ''  # Empty string for unmapped volumes
                volume['mapped_host_count'] = 0

            # Flatten listOfMappings (take first mapping if multiple exist)
            mappings = volume.get('listOfMappings', [])
            if mappings and len(mappings) > 0:
                first_mapping = mappings[0]
                volume['listOfMappings_lunMappingRef'] = first_mapping.get('lunMappingRef', 'unknown')
                volume['listOfMappings_lun'] = first_mapping.get('lun', 0)
                volume['listOfMappings_ssid'] = first_mapping.get('ssid', 0)
            else:
                volume['listOfMappings_lunMappingRef'] = 'unmapped'
                volume['listOfMappings_lun'] = 0
                volume['listOfMappings_ssid'] = 0
            
            # Apply mapping and coerce
            volume_mapped = apply_mapping(volume, CONFIG_VOLUMES_MAPPING)
            config_fields = volume_mapped

            vol_config_item = {
                "measurement": "config_volumes",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    "wwn": str(volume_mapped.get("wwn", "unknown")),
                    "label": str(volume_mapped.get("label", "unknown")),
                    "volume_ref": str(volume_mapped.get("volume_ref", "unknown")),
                    "volume_name": str(volume_mapped.get("volume_name", "unknown")),
                    "id": str(volume_mapped.get("id", "unknown")),
                    "volume_group_ref": str(volume_mapped.get("volume_group_ref", "unknown")),
                    "raid_level": str(volume_mapped.get("raid_level", "unknown")),
                    "status": str(volume_mapped.get("status", "unknown")),
                    "is_disk_pool": str(volume_mapped.get("is_disk_pool", "unknown")),
                    "metadata": str(volume_mapped.get("metadata", ""))
                },
                "fields": config_fields
            }

            if not CMD.include or vol_config_item.get("measurement") in CMD.include:
                if PROMETHEUS_AVAILABLE and 'config_volumes' in prometheus_metrics:
                    try:
                        prometheus_metrics['config_volumes']['info'].labels(**vol_config_item['tags']).set(1.0)
                        
                        prom_tags = {k: v for k, v in vol_config_item['tags'].items() if k in ['sys_id', 'sys_name', 'volume_ref', 'label', 'volume_name', 'volume_group_ref']}
                        if 'capacity' in vol_config_item['fields'] and vol_config_item['fields']['capacity'] is not None:
                            prometheus_metrics['config_volumes']['capacity_bytes'].labels(**prom_tags).set(float(vol_config_item['fields']['capacity']))
                        if 'total_size_in_bytes' in vol_config_item['fields'] and vol_config_item['fields']['total_size_in_bytes'] is not None:
                            prometheus_metrics['config_volumes']['total_size_bytes'].labels(**prom_tags).set(float(vol_config_item['fields']['total_size_in_bytes']))
                    except Exception as e:
                        LOG.error(f"Prometheus label error: {e}")
                json_body.append(vol_config_item)
                LOG.debug(f"Added config_volumes measurement for volume {volume.get('name', 'unknown')}")
            else:
                LOG.debug("Skipped config_volumes measurement (not in --include filter)")

        # Add aggregate summary metric
        if not CMD.include or "config_volumes_summary" in CMD.include:
            summary_item = {
                "measurement": "config_volumes_summary",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name
                },
                "fields": {
                    "volume_count": volume_count,
                    "snapshot_count": snapshot_count,
                    "repository_capacity": float(repository_capacity)
                }
            }
            json_body.append(summary_item)
            LOG.debug("Added config_volumes_summary measurement")

        LOG.debug(f"collect_config_volumes: Prepared {len(json_body)} measurements for Prometheus")
        
        # Add per-snapshot repository stats
        if not CMD.include or "config_repositories" in CMD.include:
            vol_ref_to_name = {str(v.get('volumeRef', '')): v.get('name', 'unknown') for v in volumes_response if isinstance(v, dict)}
            if 'snapshot_images_response' in locals() and snapshot_images_response and isinstance(snapshot_images_response, list):
                for pit in snapshot_images_response:
                    if not isinstance(pit, dict):
                        continue
                        
                    pit_capacity = float(pit.get('pitCapacity', 0))
                    repo_pct = float(pit.get('repositoryCapacityUtilization', 0))
                    # Stranded capacity logic based on capacity vs utilization
                    stranded_capacity = (repo_pct / 100.0) * pit_capacity
                    base_vol = str(pit.get('baseVol', 'unknown'))
                    vol_name = vol_ref_to_name.get(base_vol, 'unknown')
                    
                    repo_item = {
                        "measurement": "config_repositories",
                        "tags": {
                            "sys_id": sys_id,
                            "sys_name": sys_name,
                            "pit_id": str(pit.get('id', 'unknown')),
                            "pitGroupRef": str(pit.get('pitGroupRef', 'unknown')),
                            "baseVol": base_vol,
                            "baseVol_name": vol_name
                        },
                        "fields": {
                            "pit_capacity": float(pit_capacity),
                            "repository_utilization_pct": float(repo_pct),
                            "stranded_capacity": float(stranded_capacity),
                            "active_cow": bool(pit.get('activeCOW', False))
                        }
                    }
                    if not CMD.include or "config_repositories" in CMD.include:
                         json_body.append(repo_item)
                repo_count = len([x for x in snapshot_images_response if isinstance(x, dict)])
                LOG.debug(f"Added {repo_count} config_repositories measurements")

    finally:
        # Reset controller selection for next collection session
        set_current_controller_index(None)


@metrics_timer("config_pools")
def collect_config_storage_pools(system_info):
    """
    Collects storage pool configuration information and posts it to Prometheus
    :param system_info: The JSON object of a storage_system
    """

    # Early exit if not a config collection interval
    if not should_collect_config_data():
        LOG.info("Skipping config_storage_pools collection - not a scheduled interval (collected every 15 minutes)")
        return
    try:
        # Set controller for consistent selection within this collection session
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))

        session = get_session()

        sys_id = system_info.get("wwn", system_info.get("id", "unknown"))
        sys_name = system_info.get("name", "unknown")

        # Get storage pool configuration data from the API
        storage_pools_response = session.get(f"{get_controller('sys')}/{sys_id}/storage-pools").json()

        LOG.debug(f"Retrieved {len(storage_pools_response)} storage pool configurations")


        for pool in storage_pools_response:
            # Apply mappings
            prom_metrics = apply_mapping(pool, CONFIG_STORAGE_POOLS_MAPPING)

            # extract all string/label fields for labels mapping 
            extracted_labels = {
                "sys_id": sys_id,
                "sys_name": sys_name,
                "volume_group_ref": prom_metrics.pop("volume_group_ref", "unknown"),
                "id": str(prom_metrics.pop("id", "unknown")),
                "label": str(prom_metrics.pop("label", "unknown")),
                "pool_name": str(prom_metrics.pop("pool_name", "unknown")),
                "raid_level": str(prom_metrics.pop("raid_level", "unknown")),
                "state": str(prom_metrics.pop("state", "unknown")),
                "drive_media_type": str(prom_metrics.pop("drive_media_type", "unknown"))
            }

            # other info labels from the mapping mapped directly to string variables
            for extra_label in ["wwn", "has_tray_loss_protection", "is_spindle_speed_match", "spindle_speed", "is_inaccessible", "security_type", "has_drawer_loss_protection", "is_protection_information_capable", "drive_physical_type", "drive_block_format", "reserved_space_allocated_bytes", "security_level", "is_dulbe_enabled", "sector_size_bytes_supported", "sector_size_recommended_bytes"]:
                val = prom_metrics.pop(extra_label, None)
                if val is not None:
                    extracted_labels[extra_label] = str(val).lower() if isinstance(val, bool) else str(val)

            # Generate the info metric
            info_labels = {k: extracted_labels[k] for k in PROMETHEUS_METRICS_CONFIG["config_storage_pools"]["info"]["labels"] if k in extracted_labels}
            
            # The remaining label values could technically be logged if we updated mapping file to contain them
            # For now, append them to prometheus config if needed, otherwise just set info:
            prometheus_metrics["config_storage_pools"]["info"].labels(**info_labels).set(1.0)
            
            # The keys left in prom_metrics are the float-like config values (used_space_bytes, total_raided_space_bytes, free_space_bytes)
            for metric_key, val in prom_metrics.items():
                if metric_key in prometheus_metrics["config_storage_pools"] and val is not None:
                    metric_labels = {k: extracted_labels[k] for k in PROMETHEUS_METRICS_CONFIG["config_storage_pools"][metric_key]["labels"] if k in extracted_labels}
                    prometheus_metrics["config_storage_pools"][metric_key].labels(**metric_labels).set(float(val))

    except Exception as e:
        LOG.error(f"Error when attempting to post storage pool configuration for {system_info.get('name')}/{system_info.get('wwn')}: {e}")

    finally:
        # Reset controller selection for next collection session
        set_current_controller_index(None)


@metrics_timer("config_hosts")
def collect_config_hosts(system_info):
    """
    Collects host and host-group configuration information and posts it to Prometheus
    :param system_info: The JSON object of a storage_system
    """

    # Early exit if not a config collection interval
    if not should_collect_config_data():
        LOG.info("Skipping config_hosts collection - not a scheduled interval (collected every 15 minutes)")
        return

    try:
        # Set controller for consistent selection within this collection session
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))

        session = get_session()
        json_body = list()
        
        sys_id = system_info.get("wwn", system_info.get("chassisSerialNumber", system_info.get("id", "1")))
        sys_name = system_info.get("name", "unknown")

        # 1. Collect Host Groups
        try:
            host_groups_response = session.get(f"{get_controller('sys')}/{sys_id}/host-groups").json()
            LOG.debug(f"Retrieved {len(host_groups_response)} host-group configurations")
            
            for hg in host_groups_response:
                hg_mapped = apply_mapping(hg, HOST_GROUPS_MAPPING)

                # Split tags vs fields based on the coerion_func logic
                config_fields = hg_mapped

                hg_item = {
                    "measurement": "config_host_groups",
                    "tags": {
                        "sys_id": sys_id,
                        "sys_name": sys_name,
                        "id": str(hg_mapped.get("id", "unknown")),
                        "cluster_ref": str(hg_mapped.get("cluster_ref", "none")),
                        "label": str(hg_mapped.get("label", "unknown")),
                        "name": str(hg_mapped.get("name", "unknown"))
                    },
                    "fields": config_fields
                }
                
                if not CMD.include or hg_item["measurement"] in CMD.include:
                    if PROMETHEUS_AVAILABLE and "config_host_groups" in prometheus_metrics:
                        try:
                            prometheus_metrics["config_host_groups"]["info"].labels(**hg_item["tags"]).set(1.0)
                        except Exception as e:
                            LOG.error(f"Prometheus label error: {e}")
                    json_body.append(hg_item)
                    
        except Exception as e:
            LOG.warning(f"Could not retrieve host-groups configurations: {e}")

        # 2. Collect Hosts
        try:
            hosts_response = session.get(f"{get_controller('sys')}/{sys_id}/hosts").json()
            LOG.debug(f"Retrieved {len(hosts_response)} host configurations")

            for host in hosts_response:
                ports = host.get('ports', [])
                host_side_ports = host.get('hostSidePorts', [])
                initiators = host.get('initiators', [])
                
                # Semicolon-delimited combinations for nested arrays
                ports_host_port_ref = ";".join([str(p.get("hostPortRef", "")) for p in ports if "hostPortRef" in p])
                port_1_name = ";".join([str(p.get("hostPortName", "")) for p in ports if "hostPortName" in p])
                is_port_1_inactive = ";".join([str(p.get("portInactive", "")) for p in ports if "portInactive" in p])
                port_1_id = ";".join([str(p.get("id", "")) for p in ports if "id" in p])
                
                host_side_ports_1_id = ";".join([str(p.get("id", "")) for p in host_side_ports if "id" in p])
                host_side_ports_1_name = ";".join([str(p.get("name", "")) for p in host_side_ports if "name" in p])
                
                host_mapped = apply_mapping(host, HOSTS_MAPPING)

                host_mapped["ports_host_port_ref"] = ports_host_port_ref
                host_mapped["port_names"] = port_1_name
                host_mapped["is_ports_inactive"] = is_port_1_inactive
                host_mapped["port_ids"] = port_1_id
                host_mapped["host_side_ports_ids"] = host_side_ports_1_id
                host_mapped["host_side_ports_names"] = host_side_ports_1_name
                host_mapped["initiator_count"] = len(initiators) + len(ports)
                host_mapped["host_side_port_count"] = len(host_side_ports)

                # Apply field coercion to ensure proper types
                config_fields = host_mapped

                host_item = {
                    "measurement": "config_hosts",
                    "tags": {
                        "sys_id": sys_id,
                        "sys_name": sys_name,
                        "id": str(host_mapped.get("id", "unknown")),
                        "host_ref": str(host_mapped.get("host_ref", "unknown")),
                        "host_name": str(host_mapped.get("host_name", "unknown")),
                        "label": str(host_mapped.get("label", "unknown")),
                        "host_type_index": str(host_mapped.get("host_type_index", "unknown")),
                        "cluster_ref": str(host_mapped.get("cluster_ref", "none"))
                    },
                    "fields": config_fields
                }

                if not CMD.include or host_item["measurement"] in CMD.include:
                    if PROMETHEUS_AVAILABLE and "config_hosts" in prometheus_metrics:
                        try:
                            prometheus_metrics["config_hosts"]["info"].labels(**host_item["tags"]).set(1.0)
                        except Exception as e:
                            LOG.error(f"Prometheus label error: {e}")
                    json_body.append(host_item)
                    LOG.debug(f"Added config_hosts measurement for host {host.get('name', 'unknown')}")

            LOG.debug(f"Populated _HOSTS_CACHE with {len(_HOSTS_CACHE)} hosts")

        except Exception as e:
            LOG.warning(f"Could not retrieve hosts configurations: {e}")

    except RuntimeError:
        LOG.error(f"Error when attempting to post host configuration for {system_info['name']}/{system_info['wwn']}")

    finally:
        # Reset controller selection for next collection session
        set_current_controller_index(None)


@metrics_timer("flashcache_stats")
def collect_flashcache_stats(system_info):
    """
    Collects Flash Cache stats and posts them to and Prometheus.
    """
    if CMD.include and 'flashcache' not in CMD.include:
        return

    # Set controller for consistent selection within this collection session
    if len(CMD.api) > 1:
        set_current_controller_index(random.randrange(0, 2))

    sys_id = system_info.get('wwn', system_info.get('id'))
    sys_name = system_info['name']

    try:
        session = get_session()
        
        # 1. Obtain Flash Cache Metadata
        fc_url = f"{get_controller('sys')}/{sys_id}/flash-cache"
        try:
            fc_raw_resp = session.get(fc_url)
            if fc_raw_resp.status_code == 404:
                # System doesn't have Flash Cache endpoints (e.g., all-SSD)
                if PROMETHEUS_AVAILABLE and 'flashcache' in prometheus_metrics:
                    prometheus_metrics['flashcache']['components'].labels(
                        sys_id=sys_id, sys_name=sys_name, 
                        flash_cache_id='none', flash_cache_name='none', metric='status'
                    ).set(0.0)
                return
            fc_resp = fc_raw_resp.json()
        except Exception as e:
            LOG.warning(f"Failed to retrieve Flash Cache metadata: {e}")
            return
            
        if not fc_resp or not isinstance(fc_resp, dict) or 'flashCacheRef' not in fc_resp:
            # Flash Cache does not exist
            return
            
        fc_id = fc_resp.get('flashCacheRef')
        fc_name = fc_resp.get('flashCacheBase', {}).get('label', 'Unknown')
        cached_volumes = len(fc_resp.get('cachedVolumes', []))
        cache_drives = len(fc_resp.get('driveRefs', []))
        
        # 2. Collect Performance Stats (SYMbol API)
        stats_url = f"{get_controller('sys')}/{sys_id}/symbol/getFlashCacheStatistics?verboseErrorResponse=true&controller=auto"
        try:
            stats_resp = session.post(
                stats_url, 
                json=fc_id, 
                headers={"Content-Type": "application/json;charset=utf-8"}
            ).json()
        except Exception as e:
            LOG.warning(f"Failed to POST to getFlashCacheStatistics: {e}")
            return
            
        if stats_resp.get('returnCode') != 'ok' or 'flashCacheStatistics' not in stats_resp:
            LOG.warning(f"Failed to get Flash Cache statistics (returnCode={stats_resp.get('returnCode')})")
            return
            
        api_stats = stats_resp['flashCacheStatistics']
        current_ts = float(api_stats.get('timestamp', time.time()))
        
        # Extract current raw values (counters + gauges)
        current_values = {'timestamp': current_ts}
        
        for p in FLASHCACHE_REALTIME_COUNTERS + FLASHCACHE_REALTIME_GAUGES:
            # Only exact params
            if p not in ["cached_volumes_count", "cache_drive_count"]:
                val = api_stats.get(p, 0)
                current_values[p] = float(val) if val is not None else 0.0
                
        # Get previous stats
        prev_stats = _FLASHCACHE_STATS_CACHE.get(sys_id)
        
        # Store for next run
        _FLASHCACHE_STATS_CACHE[sys_id] = current_values

        # On first run, we skip deltas for counter-based metrics.
        if not prev_stats:
            LOG.debug(f"First run for Flash Cache on {sys_name}, initializing cache")
            return
            
        dt = current_values['timestamp'] - prev_stats['timestamp']
        if dt <= 0:
            dt = 1
            
        fields: dict = {
            "cached_volumes_count": float(cached_volumes),
            "cache_drive_count": float(cache_drives)
        }
        
        # Process Gauges
        for p in FLASHCACHE_REALTIME_GAUGES:
            if p not in ["cached_volumes_count", "cache_drive_count"]:
                fields[p] = current_values[p]
                
        # Process Counters and calc delta
        valid_deltas = True
        for p in FLASHCACHE_REALTIME_COUNTERS:
            if current_values[p] < prev_stats[p]:
                # Counter reset
                valid_deltas = False
                break
            fields[p] = current_values[p] - prev_stats[p]
            
        if not valid_deltas:
            LOG.debug(f"Counter reset detected for Flash Cache on {sys_name}, skipping delta calculations")
            return
            
        # Coerce values to int per requirements        
        tags = {
            "sys_id": sys_id,
            "sys_name": sys_name,
            "flash_cache_id": fc_id,
            "flash_cache_name": fc_name
        }
        
        if getattr(CMD, 'showFlashCache', False):
            LOG.info(f"Flash Cache [{fc_id}] name: {fc_name}")
            LOG.info(f"Flash Cache Stats: {fields}")
        
        send_to_prometheus("flashcache", tags, fields)
            
    except Exception as e:
        LOG.error(f"Error collecting Flash Cache stats for {system_info['name']}/{sys_id}: {e}")
        
    finally:
        # Reset controller selection for next collection session
        set_current_controller_index(None)


@metrics_timer("controller_metrics")
def collect_controller_metrics(system_info, live_stats_snapshot=None):
    """
    Collects controller performance metrics from both controllers
    :param system_info: The JSON object of a storage_system
    """
    # Set controller for consistent selection within this collection session
    if len(CMD.api) > 1:
        set_current_controller_index(random.randrange(0, 2))

    try:
        json_body = list()

        try:
            session = get_session()
            if live_stats_snapshot is None:
                live_stats_snapshot = _get_live_statistics_snapshot(session, sys_id)

            controller_stats_list = _extract_live_stats_section(live_stats_snapshot, 'controllerStats')

            if not controller_stats_list:
                LOG.info("Live controller stats unavailable this iteration.")
            else:
                produced_points = 0
                current_ts = time.time()
                for controller_stats in controller_stats_list:
                    global _CONTROLLER_ID_TYPE_WARNING_EMITTED

                    raw_controller_id = controller_stats.get('controllerId', 'unknown')
                    if not isinstance(raw_controller_id, str) and not _CONTROLLER_ID_TYPE_WARNING_EMITTED:
                        LOG.warning(
                            "controllerId arrived as %s; coercing to string to match schema",
                            type(raw_controller_id).__name__,
                        )
                        _CONTROLLER_ID_TYPE_WARNING_EMITTED = True

                    controller_id = _map_controller_id(raw_controller_id)
                    prev_stats = _CONTROLLER_STATS_CACHE.get(controller_id)

                    cpu_stats = controller_stats.get('cpuUtilizationStats', [])
                    cpu_max = 0.0
                    cpu_sum_total = 0.0
                    cpu_core_count = 0
                    if isinstance(cpu_stats, list) and cpu_stats:
                        cpu_max = max(float(item.get('maxCpuUtilization', 0)) for item in cpu_stats if isinstance(item, dict))
                        cpu_sum_total = sum(float(item.get('sumCpuUtilization', 0)) for item in cpu_stats if isinstance(item, dict))
                        cpu_core_count = len([item for item in cpu_stats if isinstance(item, dict)])

                    current_values = {
                        'timestamp': _parse_stats_timestamp(controller_stats, current_ts),
                        'readIopsTotal': float(controller_stats.get('readIopsTotal', 0)),
                        'writeIopsTotal': float(controller_stats.get('writeIopsTotal', 0)),
                        'totalIopsServiced': float(controller_stats.get('totalIopsServiced', 0)),
                        'readBytesTotal': float(controller_stats.get('readBytesTotal', 0)),
                        'writeBytesTotal': float(controller_stats.get('writeBytesTotal', 0)),
                        'totalBytesServiced': float(controller_stats.get('totalBytesServiced', 0)),
                        'cacheHitsBytesTotal': float(controller_stats.get('cacheHitsBytesTotal', 0)),
                        'randomIosTotal': float(controller_stats.get('randomIosTotal', 0)),
                        'mirrorBytesTotal': float(controller_stats.get('mirrorBytesTotal', 0)),
                        'fullStripeWritesBytes': float(controller_stats.get('fullStripeWritesBytes', 0)),
                        'raid0BytesTransferred': float(controller_stats.get('raid0BytesTransferred', 0)),
                        'raid1BytesTransferred': float(controller_stats.get('raid1BytesTransferred', 0)),
                        'raid5BytesTransferred': float(controller_stats.get('raid5BytesTransferred', 0)),
                        'raid6BytesTransferred': float(controller_stats.get('raid6BytesTransferred', 0)),
                        'ddpBytesTransferred': float(controller_stats.get('ddpBytesTransferred', 0)),
                        'cpuMax': cpu_max,
                        'cpuSumTotal': cpu_sum_total,
                        'cpuCoreCount': float(cpu_core_count),
                    }

                    _CONTROLLER_STATS_CACHE[controller_id] = current_values

                    if not prev_stats:
                        continue

                    if (current_values['readIopsTotal'] < prev_stats['readIopsTotal'] or
                        current_values['writeIopsTotal'] < prev_stats['writeIopsTotal'] or
                        current_values['totalIopsServiced'] < prev_stats['totalIopsServiced'] or
                        current_values['readBytesTotal'] < prev_stats['readBytesTotal'] or
                        current_values['writeBytesTotal'] < prev_stats['writeBytesTotal'] or
                        current_values['totalBytesServiced'] < prev_stats['totalBytesServiced']):
                        LOG.debug("Controller counter reset detected for controller %s", controller_id)
                        continue

                    dt = current_values['timestamp'] - prev_stats['timestamp']
                    if dt <= 0:
                        dt = 1

                    delta_read_iops_total = current_values['readIopsTotal'] - prev_stats['readIopsTotal']
                    delta_write_iops_total = current_values['writeIopsTotal'] - prev_stats['writeIopsTotal']
                    delta_total_iops = current_values['totalIopsServiced'] - prev_stats['totalIopsServiced']
                    delta_read_bytes = current_values['readBytesTotal'] - prev_stats['readBytesTotal']
                    delta_write_bytes = current_values['writeBytesTotal'] - prev_stats['writeBytesTotal']
                    delta_total_bytes = current_values['totalBytesServiced'] - prev_stats['totalBytesServiced']
                    delta_cache_hit_bytes = current_values['cacheHitsBytesTotal'] - prev_stats['cacheHitsBytesTotal']
                    delta_random_ios = current_values['randomIosTotal'] - prev_stats['randomIosTotal']
                    delta_mirror_bytes = current_values['mirrorBytesTotal'] - prev_stats['mirrorBytesTotal']
                    delta_fullstripe_bytes = current_values['fullStripeWritesBytes'] - prev_stats['fullStripeWritesBytes']
                    delta_raid0_bytes = current_values['raid0BytesTransferred'] - prev_stats['raid0BytesTransferred']
                    delta_raid1_bytes = current_values['raid1BytesTransferred'] - prev_stats['raid1BytesTransferred']
                    delta_raid5_bytes = current_values['raid5BytesTransferred'] - prev_stats['raid5BytesTransferred']
                    delta_raid6_bytes = current_values['raid6BytesTransferred'] - prev_stats['raid6BytesTransferred']
                    delta_ddp_bytes = current_values['ddpBytesTransferred'] - prev_stats['ddpBytesTransferred']

                    read_iops = delta_read_iops_total / dt
                    write_iops = delta_write_iops_total / dt
                    combined_iops = delta_total_iops / dt
                    other_iops = max(0.0, combined_iops - read_iops - write_iops)

                    read_throughput = delta_read_bytes / dt
                    write_throughput = delta_write_bytes / dt
                    combined_throughput = delta_total_bytes / dt

                    cache_hit_bytes_pct = (delta_cache_hit_bytes / delta_total_bytes * 100.0) if delta_total_bytes > 0 else 0
                    random_ios_pct = (delta_random_ios / delta_total_iops * 100.0) if delta_total_iops > 0 else 0
                    mirror_bytes_pct = (delta_mirror_bytes / delta_total_bytes * 100.0) if delta_total_bytes > 0 else 0
                    fullstripe_bytes_pct = (delta_fullstripe_bytes / delta_total_bytes * 100.0) if delta_total_bytes > 0 else 0
                    raid0_bytes_pct = (delta_raid0_bytes / delta_total_bytes * 100.0) if delta_total_bytes > 0 else 0
                    raid1_bytes_pct = (delta_raid1_bytes / delta_total_bytes * 100.0) if delta_total_bytes > 0 else 0
                    raid5_bytes_pct = (delta_raid5_bytes / delta_total_bytes * 100.0) if delta_total_bytes > 0 else 0
                    raid6_bytes_pct = (delta_raid6_bytes / delta_total_bytes * 100.0) if delta_total_bytes > 0 else 0
                    ddp_bytes_pct = (delta_ddp_bytes / delta_total_bytes * 100.0) if delta_total_bytes > 0 else 0

                    cpu_avg = 0.0
                    delta_cpu_sum = current_values['cpuSumTotal'] - prev_stats.get('cpuSumTotal', 0.0)
                    cpu_cores = int(current_values.get('cpuCoreCount', 0))
                    if delta_cpu_sum >= 0 and cpu_cores > 0 and dt > 0:
                        cpu_avg = delta_cpu_sum / (cpu_cores * dt)

                    controller_fields = {
                        'readIOps': read_iops,
                        'writeIOps': write_iops,
                        'otherIOps': other_iops,
                        'combinedIOps': combined_iops,
                        'readThroughput': read_throughput,
                        'writeThroughput': write_throughput,
                        'combinedThroughput': combined_throughput,
                        'readOps': delta_read_iops_total,
                        'writeOps': delta_write_iops_total,
                        'readPhysicalIOps': read_iops,
                        'writePhysicalIOps': write_iops,
                        'cacheHitBytesPercent': cache_hit_bytes_pct,
                        'randomIosPercent': random_ios_pct,
                        'mirrorBytesPercent': mirror_bytes_pct,
                        'fullStripeWritesBytesPercent': fullstripe_bytes_pct,
                        'maxCpuUtilization': current_values['cpuMax'],
                        'cpuAvgUtilization': cpu_avg,
                        'raid0BytesPercent': raid0_bytes_pct,
                        'raid1BytesPercent': raid1_bytes_pct,
                        'raid5BytesPercent': raid5_bytes_pct,
                        'raid6BytesPercent': raid6_bytes_pct,
                        'ddpBytesPercent': ddp_bytes_pct,
                        'controllerId': controller_id,
                    }
                    tags = {
                        "sys_id": sys_id,
                        "sys_name": sys_name,
                        "controller_id": controller_id,
                    }
                    controller_item = {
                        "measurement": "controllers",
                        "tags": tags,
                        "fields": controller_fields,
                    }

                    if CMD.showControllerMetrics:
                        LOG.info("Controller payload: %s", controller_item)

                    if not CMD.include or controller_item["measurement"] in CMD.include:
                        json_body.append(controller_item)
                        send_to_prometheus(controller_item["measurement"], controller_item["tags"], controller_item["fields"])
                        produced_points += 1

                if produced_points == 0:
                    LOG.info("No live controller deltas produced this iteration (first run or counter reset)")

        except Exception as e:
            LOG.warning(f"Could not retrieve controller statistics: {e}")
            return

        LOG.debug(f"collect_controller_metrics: Prepared {len(json_body)} measurements")
        write_to_outputs(json_body, "controller metrics")

    except Exception as e:
        LOG.error(f"Error when attempting to collect controller metrics for {system_info['name']}/{system_info['wwn']}: {e}")

    finally:
        # Reset controller selection for next collection session
        set_current_controller_index(None)


def order_sensor_response_list(response):
    """
    Reorders the sensor readings list by ascending thermalSensorRef string for "stable" sensor ordering and tagging
    :param response: the response from the SANtricity SYMbol v2 API with environmental sensor readings
    ::return: returns a response dictionary with the sensor readings (thermalSensorRef) list items in ascending order
    """
    osensor = []
    i = 0
    for item in response['thermalSensorData']:
        pair = (item['thermalSensorRef'], i)
        osensor.append(pair)
        i = i+1
    osensor.sort()
    ordered_response = []
    for item in osensor:
        ordered_response.append(response['thermalSensorData'][item[1]])
    return ordered_response


#######################
# MAIN FUNCTIONS ######
#######################


def _collect_and_map_endpoint(session, sys_id, sys_name, measurement, metric_def, include_filter, prom_metrics):
    base_name, desc, mapping, endpoint = metric_def
    if include_filter and measurement not in include_filter:
        return

    json_body = []
    try:
        url = f"{get_controller('sys')}/{sys_id}{endpoint}"
        result = session.get(url).json()
        
        if isinstance(result, dict):
            result = [result]
        elif not isinstance(result, list):
            result = []

        for item in result:
            try:
                flat_item = flatten_dict_one_level(item)
            except Exception as e:
                EPA_ERROR_COUNT.labels(error_type='flattening', endpoint=measurement, system=sys_name).inc()
                LOG.warning(f"Flattening failed in {measurement}: {e}")
                continue

            try:
                mapped_item = apply_mapping(flat_item, mapping)
            except Exception as e:
                EPA_ERROR_COUNT.labels(error_type='mapping', endpoint=measurement, system=sys_name).inc()
                LOG.warning(f"Mapping failed in {measurement}: {e}")
                continue

            tags = {"sys_id": sys_id, "sys_name": sys_name}
            
            # Ensure all registered tags are present; map missing ones to "None"
            for tag_k in extract_tag_keys(mapping):
                tags[tag_k] = "None"
            
            fields = {}
            for k, v in mapped_item.items():
                if k in extract_tag_keys(mapping):
                    tags[k] = str(v)
                else:
                    fields[k] = v
            
            if not fields:
                fields["status"] = 1.0
                
            config_item = {
                "measurement": measurement,
                "tags": tags,
                "fields": fields
            }
            json_body.append(config_item)
            
            if prom_metrics and measurement in prom_metrics:
                try:
                    prom_metrics[measurement]['info'].labels(**tags).set(1.0)
                    for field_k, field_v in fields.items():
                        if field_k != "status":
                            prom_key = f"{measurement}_{field_k}"
                            if prom_key in prom_metrics[measurement]:
                                prom_metrics[measurement][prom_key].labels(**tags).set(float(field_v) if field_v is not None else 0.0)
                except Exception as e:
                    LOG.error(f"Prometheus label error for {measurement}: {e}")

            if prom_metrics:
                EPA_METRIC_COUNT.labels(endpoint=measurement, system=sys_name).inc(len(fields))
            
    except Exception as e:
        EPA_ERROR_COUNT.labels(error_type='snapshot_endpoint', endpoint=measurement, system=sys_name).inc()
        LOG.error(f"Error processing {measurement}: {e}")

@metrics_timer("config_snapshots")
def collect_config_snapshots_all(system_info):
    """
    Collects all snapshot-related configuration info 
    """
    if not should_collect_config_data():
        LOG.info("Skipping snapshot config collection - not a scheduled interval")
        return
        
    LOG.info("Collecting snapshot configuration...")

    try:
        import random
        if len(CMD.api) > 1:
            set_current_controller_index(random.randrange(0, 2))
        
        session = get_session()
        sys_id = system_info.get("wwn", system_info.get("chassisSerialNumber", system_info.get("id", "1")))
        sys_name = system_info.get("name")
        
        prom_metrics = prometheus_metrics if PROMETHEUS_AVAILABLE else None
        include_filter = CMD.include if hasattr(CMD, 'include') and CMD.include else []
        
        for measurement, metric_def in SNAPSHOT_METRIC_DEFS.items():
            _collect_and_map_endpoint(
                session, sys_id, sys_name, measurement, metric_def, 
                include_filter, prom_metrics
            )
            
    finally:
        set_current_controller_index(None)


if __name__ == "__main__":
    executor = concurrent.futures.ThreadPoolExecutor(NUMBER_OF_THREADS)

    SESSION = get_session()
    loopIteration = 1


# Set up Prometheus metrics server if requested
    setup_prometheus()

    LOG.info("=== Metrics Source Strategy ===")
    LOG.info("volumes: live-statistics counter deltas (first iteration skipped)")
    LOG.info("controllers: live-statistics counter deltas (first iteration skipped)")
    LOG.info("interfaces: live-statistics counter deltas (first iteration skipped)")
    LOG.info("disks: non-cached statistics counter deltas (first iteration skipped)")    
    LOG.info("===============================")

    sys_id = "unknown"
    sys_name = "unknown"

    checksums = {}
    iteration_count = 0
    while True:
        iteration_count += 1

        # Check iteration limit for lab testing
        if CMD.max_iterations > 0 and iteration_count > CMD.max_iterations:
            LOG.info(f"Reached maximum iterations limit ({CMD.max_iterations}), exiting...")
            break

        time_start = time.time()
        try:
            response = SESSION.get(get_controller("sys") + "/1")
            
            if response.status_code != 200:
                LOG.warning(
                    f"Unable to connect to storage-system API endpoint! Status-code={response.status_code}")
                # Optional fallback if 1 fails, try array root
                fallback = SESSION.get(get_controller("sys"))
                if fallback.status_code == 200:
                   arr = fallback.json()
                   if isinstance(arr, list) and len(arr) > 0:
                       resp_json = arr[0]
                   else:
                       resp_json = {}
                else:
                   resp_json = {}
            else:
                resp_json = response.json()
                
            sys_id = resp_json.get("wwn", resp_json.get("id", "unknown"))
            sys_name = resp_json.get("name", "unknown")
            
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            LOG.warning("Unable to connect to the API! %s", e)
            if PROMETHEUS_AVAILABLE and 'system_status' in prometheus_metrics:
                # Might not have actual sys_name/id if initial connect fails, fallback to placeholders
                if sys_id != "unknown" and sys_name != "unknown":
                    prometheus_metrics['system_status']['epa_status'].labels(sys_id=sys_id, sys_name=sys_name, endpoint="collector").set(0.0)
        except Exception as e:
            LOG.warning("Unexpected exception! %s", e)
            if PROMETHEUS_AVAILABLE and 'system_status' in prometheus_metrics:
                if sys_id != "unknown" and sys_name != "unknown":
                    prometheus_metrics['system_status']['epa_status'].labels(sys_id=sys_id, sys_name=sys_name, endpoint="collector").set(0.0)
        else:
            sys = resp_json
            sys['wwn'] = sys_id
            if PROMETHEUS_AVAILABLE and 'system_status' in prometheus_metrics:
                if sys_id != "unknown" and sys_name != "unknown":
                    prometheus_metrics['system_status']['epa_status'].labels(sys_id=sys_id, sys_name=sys_name, endpoint="collector").set(1.0)
            if CMD.showStorageNames:
                LOG.info(sys_name)

            # Increment config collection iteration counter once per collection cycle
            _CONFIG_COLLECTION_ITERATION_COUNTER += 1

            # Always populate mappable objects mega-cache (required for performance host mapping)
            # This runs regardless of --include filters since volume/mapping correlation is needed
            # for performance data even when config measurements aren't being collected
            populate_hosts_cache(sys)
            populate_mappable_objects_cache(sys)

            # Fetch one live snapshot for both volumes and controllers per cycle.
            live_stats_snapshot = None
            if hasattr(CMD, 'include') and CMD.include:
                needs_live_storage = ('volumes' in CMD.include)
                needs_live_controller = ('controllers' in CMD.include)
                if needs_live_storage or needs_live_controller:
                    live_stats_snapshot = _get_live_statistics_snapshot(SESSION, sys_id)
            else:
                live_stats_snapshot = _get_live_statistics_snapshot(SESSION, sys_id)

            # Conditionally collect measurements based on --include filter
            if hasattr(CMD, 'include') and CMD.include:
                LOG.info(f"Starting selective collection for measurements: {', '.join(CMD.include)}")
                # Only run functions whose measurements are included
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_flashcache_stats']):
                    LOG.info("Collecting Flash Cache statistics...")
                    collect_flashcache_stats(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_storage_metrics']):
                    LOG.info("Collecting storage metrics (disks, interface, volumes)...")
                    collect_storage_metrics(sys, live_stats_snapshot=live_stats_snapshot)
                
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_controller_metrics']):
                    LOG.info("Collecting controller metrics...")
                    collect_controller_metrics(sys, live_stats_snapshot=live_stats_snapshot)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_symbol_stats']):
                    LOG.info("Collecting power and temperature data...")
                    collect_symbol_stats(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_system_state']):
                    LOG.info("Collecting system state and failure information...")
                    collect_system_failures(sys, checksums)
                    collect_interface_alerts(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_storage_pools']):
                    LOG.info("Collecting storage pool configuration...")
                    collect_config_storage_pools(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_volume_mappings']):
                    LOG.info("Collecting volume mappings...")
                    collect_config_volume_mappings(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_volumes']):
                    LOG.info("Collecting volume configuration...")
                    collect_config_volumes(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_hosts']):
                    LOG.info("Collecting host configuration...")
                    collect_config_hosts(sys)
                LOG.info("Collecting interface configuration...")
                collect_config_interfaces(sys)
                LOG.info("Collecting controller configuration...")
                collect_config_controllers(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_drives']):
                    LOG.info("Collecting drive configuration...")
                    collect_config_drives(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_workloads']):
                    LOG.info("Collecting workload configuration...")
                    collect_config_workloads(sys)
                if 'config_system' in CMD.include or any(m in CMD.include for m in FUNCTION_MEASUREMENTS.get('collect_config_system', [])):
                    LOG.info('Collecting system configuration...')
                    collect_config_system(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_snapshots_all']):
                    collect_config_snapshots_all(sys)
            else:
                # Default: collect all measurements
                LOG.info("Starting full collection cycle for all measurements...")
                LOG.info("Collecting storage metrics (disks, interface, volumes)...")
                collect_storage_metrics(sys, live_stats_snapshot=live_stats_snapshot)

                LOG.info("Collecting Flash Cache statistics...")
                collect_flashcache_stats(sys)

                LOG.info("Collecting controller metrics...")
                collect_controller_metrics(sys, live_stats_snapshot=live_stats_snapshot)
                LOG.info("Collecting power and temperature data...")
                collect_symbol_stats(sys)
                LOG.info("Collecting system state and failure information...")
                collect_system_failures(sys, checksums)
                collect_interface_alerts(sys)
                LOG.info("Collecting storage pool configuration...")
                collect_config_storage_pools(sys)
                LOG.info("Collecting volume mappings...")
                collect_config_volume_mappings(sys)
                LOG.info("Collecting volume configuration...")
                collect_config_volumes(sys)
                LOG.info("Collecting host configuration...")
                collect_config_hosts(sys)
                LOG.info("Collecting interface configuration...")
                collect_config_interfaces(sys)
                LOG.info("Collecting controller configuration...")
                collect_config_controllers(sys)
                LOG.info("Collecting drive configuration...")
                collect_config_drives(sys)
                LOG.info("Collecting workload configuration...")
                collect_config_workloads(sys)
                LOG.info('Collecting system configuration...')
                collect_config_system(sys)
                collect_config_snapshots_all(sys)

            LOG.info(f"Collection cycle completed for system '{sys_name}' ({sys_id})")


        time_difference = time.time() - time_start
        if CMD.showIteration:
            LOG.info(
                f"Time interval: {CMD.intervalTime:07.4f} Time to collect and send: {time_difference:07.4f} Iteration: {loopIteration:00.0f}")
            loopIteration += 1

        wait_time = CMD.intervalTime - time_difference
        if CMD.intervalTime < time_difference:
            LOG.error(
                f"The interval specified is not long enough. Time used: {time_difference:07.4f} Time interval specified: {CMD.intervalTime:07.4f}")
            wait_time = time_difference

        time.sleep(wait_time)
