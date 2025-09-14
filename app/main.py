#!/usr/bin/env python3

# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

"""
Entry point wrapper for the E-Series Performance collector.
This module orchestrates the collection, enrichment, and writing of E-Series metrics.

The application follows a modular architecture:
- collectors: Retrieve data from E-Series API endpoints
- cache: Store configuration data to minimize API calls
- enrichment: Combine performance metrics with configuration data
- writer: Output enriched data to various destinations (InfluxDB, JSON, Prometheus)
"""


import argparse
import sys
import logging
import os
import time
import base64
import concurrent.futures
import getpass
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timezone

# Import config collection scheduler
from app.config.collection_schedules import ConfigCollectionScheduler, ScheduleFrequency

# Import real collector classes
from app.collectors.config_collector import ConfigCollector
from app.collectors.performance_collector import PerformanceCollector
from app.collectors.event_collector import EventCollector

class EnrichmentProcessor:
    """Enrich performance data with configuration information."""
    def __init__(self, config_collector=None):
        self.config_collector = config_collector
        self.cache = config_collector.config_cache if config_collector else None
        self.volumes_cached = False
        self.system_cached = False
        self.logger = logging.getLogger(__name__)
        
        # Initialize enrichment processors
        from app.enrichment.volume_enrichment import VolumeEnrichmentProcessor
        from app.enrichment.drive_enrichment import DriveEnrichmentProcessor
        from app.enrichment.controller_enrichment import ControllerEnrichmentProcessor
        from app.enrichment.system_enrichment import SystemEnrichmentProcessor
        self.volume_enricher = VolumeEnrichmentProcessor()
        self.drive_enricher = DriveEnrichmentProcessor()
        self.controller_enricher = ControllerEnrichmentProcessor()
        self.system_enricher = SystemEnrichmentProcessor()
        self.enrichment_data_loaded = False
        
    def _load_enrichment_data(self):
        """Load all configuration data needed for enrichment"""
        if self.enrichment_data_loaded or not self.config_collector:
            return
            
        try:
            try:
                from app.schema.models import (
                    HostConfig, HostGroupsConfig, StoragePoolConfig, 
                    VolumeConfig, VolumeMappingsConfig, DriveConfig, ControllerConfig, SystemConfig
                )
            except ImportError as e:
                self.logger.error(f"Failed to import models: {e}")
                return
            
            # Check if we're in JSON mode and collect configuration data accordingly
            if hasattr(self.config_collector.eseries_collector, 'from_json') and self.config_collector.eseries_collector.from_json:
                # JSON replay mode - collect from JSON files
                self.logger.info("Loading enrichment data from JSON files...")
            else:
                # Live API mode - collect from API
                self.logger.info("Loading enrichment data from API...")
            
            # Use unified collection methods that handle both JSON and API modes automatically
            hosts = self.config_collector.eseries_collector.collect_hosts(HostConfig)
            host_groups = self.config_collector.eseries_collector.collect_host_groups(HostGroupsConfig)  
            storage_pools = self.config_collector.eseries_collector.collect_storage_pools(StoragePoolConfig)
            volumes = self.config_collector.eseries_collector.collect_volumes(VolumeConfig)
            volume_mappings = self.config_collector.eseries_collector.collect_volume_mappings(VolumeMappingsConfig)
            drives = self.config_collector.eseries_collector.collect_drives(DriveConfig)
            controllers = self.config_collector.eseries_collector.collect_controllers(ControllerConfig)
            system_configs = self.config_collector.eseries_collector.collect_system_configs(SystemConfig)
            
            # Convert to raw data for enrichment processors
            hosts_data = [host._raw_data if hasattr(host, '_raw_data') else host.__dict__ for host in hosts]
            host_groups_data = [hg._raw_data if hasattr(hg, '_raw_data') else hg.__dict__ for hg in host_groups]
            pools_data = [pool._raw_data if hasattr(pool, '_raw_data') else pool.__dict__ for pool in storage_pools] 
            volumes_data = [vol._raw_data if hasattr(vol, '_raw_data') else vol.__dict__ for vol in volumes]
            mappings_data = [mapping._raw_data if hasattr(mapping, '_raw_data') else mapping.__dict__ for mapping in volume_mappings]
            drives_data = [drive._raw_data if hasattr(drive, '_raw_data') else drive.__dict__ for drive in drives]
            controllers_data = [ctrl._raw_data if hasattr(ctrl, '_raw_data') else ctrl.__dict__ for ctrl in controllers]
            system_configs_data = [sys_cfg._raw_data if hasattr(sys_cfg, '_raw_data') else sys_cfg.__dict__ for sys_cfg in system_configs]
            
            # Load into volume enricher
            self.volume_enricher.load_configuration_data(
                hosts_data, host_groups_data, pools_data, volumes_data, mappings_data
            )
            
            # Load into drive enricher
            self.drive_enricher.load_configuration_data(drives_data, pools_data)
            
            # Load into controller enricher
            self.controller_enricher.load_configuration_data(controllers_data)
            
            # Load into system enricher
            self.system_enricher.build_system_config_cache(system_configs_data)
            
            self.enrichment_data_loaded = True
            self.logger.info("Loaded enrichment configuration data")
            
        except Exception as e:
            self.logger.error(f"Failed to load enrichment data: {e}")
        
    def _ensure_volumes_cached(self):
        """Ensure volume configuration is cached."""
        if not self.volumes_cached and self.config_collector and self.cache:
            try:
                self.logger.info("Loading volume configuration into cache...")
                from app.schema.models import VolumeConfig
                volumes = self.config_collector.eseries_collector.collect_volumes(VolumeConfig)
                
                # Cache volumes by ID for fast lookup
                for volume in volumes:
                    cache_key = f"volume:{volume.id}"
                    self.cache.set(cache_key, {
                        'id': volume.id,
                        'label': volume.label,
                        'name': volume.name,
                        'capacity': volume.capacity,
                        'volumeRef': volume.volumeRef,
                        'volumeGroupRef': volume.volumeGroupRef,
                        'wwn': volume.wwn
                    })
                
                self.cache.set('volumes:count', len(volumes))
                self.volumes_cached = True
                self.logger.info(f"Cached {len(volumes)} volumes for enrichment")
                
            except Exception as e:
                self.logger.error(f"Failed to cache volumes: {e}")
    
    def _ensure_system_cached(self):
        """Ensure system configuration is cached."""
        if not self.system_cached and self.config_collector and self.cache:
            try:
                self.logger.info("Loading system configuration into cache...")
                from app.schema.models import SystemConfig
                system_config = self.config_collector.eseries_collector.collect_system_config(SystemConfig)
                
                if system_config:
                    self.cache.set('system:config', {
                        'wwn': system_config.wwn,
                        'name': system_config.name,
                        'model': system_config.model,
                        'driveCount': system_config.driveCount
                    })
                    self.system_cached = True
                    self.logger.info(f"Cached system config - WWN: {system_config.wwn}, Name: {system_config.name}")
                
            except Exception as e:
                self.logger.error(f"Failed to cache system config: {e}")
    
    def process(self, perf_data, measurement_type=None):
        """Process and enrich performance data with configuration information."""
        # Load enrichment data if available
        self._load_enrichment_data()
        
        # For controller statistics response format (dict with 'statistics' array)
        if isinstance(perf_data, dict) and 'statistics' in perf_data:
            if self.enrichment_data_loaded:
                enriched_data = self.controller_enricher.process(perf_data)
                self.logger.info(f"Processed controller statistics response with {len(enriched_data.get('statistics', []))} records")
                return enriched_data
            else:
                self.logger.warning("Enrichment data not loaded - returning controller statistics unchanged")
                return perf_data
        
        # For performance data lists, determine type and enrich accordingly
        elif isinstance(perf_data, list):
            if self.enrichment_data_loaded:
                
                # Try to detect measurement type from data structure
                if not measurement_type and len(perf_data) > 0:
                    first_record = perf_data[0]
                    if 'volumeId' in first_record:
                        measurement_type = 'volume_performance'
                    elif 'diskId' in first_record:
                        measurement_type = 'drive_performance'
                    elif 'controllerId' in first_record or 'sourceController' in first_record:
                        # Check if it's system stats vs controller stats
                        if 'storageSystemWWN' in first_record and 'maxCpuUtilization' in first_record:
                            measurement_type = 'system_performance'
                        else:
                            measurement_type = 'controller_performance'
                    elif 'storageSystemWWN' in first_record and 'maxCpuUtilization' in first_record:
                        measurement_type = 'system_performance'
                
                # Route to appropriate enricher
                if measurement_type == 'volume_performance':
                    enriched_data = self.volume_enricher.enrich_volume_performance_batch(perf_data)
                    self.logger.info(f"Enriched {len(enriched_data)} volume performance records with host/pool tags")
                    return enriched_data
                elif measurement_type == 'drive_performance':
                    enriched_data = self.drive_enricher.enrich_drive_performance_batch(perf_data)
                    self.logger.info(f"Enriched {len(enriched_data)} drive performance records with config data")
                    return enriched_data
                elif measurement_type == 'controller_performance':
                    enriched_data = self.controller_enricher.enrich_controller_performance_batch(perf_data)
                    self.logger.info(f"Enriched {len(enriched_data)} controller performance records with config data")
                    return enriched_data
                elif measurement_type == 'system_performance':
                    # Check if this is system statistics by looking for system-specific fields
                    if first_record and ('storageSystemWWN' in first_record and 'maxCpuUtilization' in first_record):
                        enriched_data = self.system_enricher.enrich_system_statistics(perf_data)
                        self.logger.info(f"Enriched {len(enriched_data)} system performance records with config data")
                        return enriched_data
                else:
                    self.logger.warning(f"Unknown measurement type: {measurement_type}")
                    return perf_data
            else:
                self.logger.warning("Enrichment data not loaded - returning data unchanged")
                return perf_data
        
        # For JSON mode summary data
        elif isinstance(perf_data, dict) and 'performance_records' in perf_data:
            enriched_data = perf_data.copy()
            
            # Add cache stats if available
            if self.cache:
                enriched_data['cache_stats'] = {
                    'volumes_cached': 0,  # Will implement proper tracking
                    'cache_hits': 0,  # Will implement proper tracking
                    'cache_misses': 0
                }
                
                # System config will be added via proper enrichment
                # system_config = self.cache.get('system:config')
                # if system_config:
                #     enriched_data['system_info'] = system_config
            
            # Add enrichment status
            enriched_data['enrichment_status'] = {
                'volume_enrichment_loaded': self.enrichment_data_loaded,
                'cache_available': self.cache is not None
            }
            
            self.logger.info("Performance data summary enriched")
            return enriched_data
        
        # For other data types, ensure cached data is available  
        if self.cache:
            self._ensure_volumes_cached()
            self._ensure_system_cached()
        
        return perf_data

class ConfigCache:
    """Temporary stub for ConfigCache."""
    def __init__(self):
        self.data = {}
    
    def get(self, key):
        """Get cached data."""
        return self.data.get(key)
    
    def set(self, key, value):
        """Set cached data."""
        self.data[key] = value

# Import utility modules - define simple stubs for now
def get_controller(endpoint_type, api_list):
    """Get controller URL."""
    if not api_list:
        return "https://localhost:8443/devmgr/v2/storage-systems"
    return f"https://{api_list[0]}:8443/devmgr/v2/storage-systems"

def get_session(username, password, api_endpoints, tls_ca=None, tls_validation='strict'):
    """Get session with proper TLS validation - establishes initial connection."""
    # Local logger for this function
    logger = logging.getLogger(__name__)
    
    session = requests.Session()
    
    # Configure TLS validation based on user preference for SANtricity API
    if tls_validation == 'none':
        # Disable SSL verification and warnings for SANtricity API
        session.verify = False
        try:
            # Import urllib3 only when needed to disable warnings
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except ImportError:
            pass  # urllib3 not available, warnings will still show
        logger.warning("TLS validation is DISABLED for SANtricity API (--tlsValidation none). This is insecure.")
    elif tls_validation == 'normal':
        # Standard SSL verification
        session.verify = tls_ca if tls_ca else True
    elif tls_validation == 'strict':
        # Strict SSL verification (default)
        session.verify = tls_ca if tls_ca else True
    
    # Try to find a working endpoint
    for endpoint in api_endpoints:
        try:
            active_endpoint = f"https://{endpoint}:8443"
            
            # Test basic connectivity with a simple endpoint
            test_url = f"{active_endpoint}/devmgr/v2/storage-systems"
            response = session.get(test_url, timeout=10)
            
            # If we get any response (even 401), the endpoint is reachable
            logger.info(f"Successfully connected to SANtricity endpoint: {endpoint}")
            return session, active_endpoint
                    
        except Exception as e:
            logger.debug(f"Failed to connect to {endpoint}: {e}")
            continue
    
    # If we get here, all endpoints failed
    raise Exception(f"Failed to connect to any SANtricity endpoint: {api_endpoints}")

def get_fresh_token(session, active_endpoint, username, password):
    """Login using POST with JSON payload (matching working test implementation)."""
    logger = logging.getLogger(__name__)
    
    try:
        # Use the same POST + JSON approach as the working test file
        login_url = f"{active_endpoint}/devmgr/utils/login"
        login_payload = {
            "userId": username,
            "password": password,
            "xsrfProtected": False
        }
        
        logger.debug(f"Attempting POST login to {login_url} with user {username}")
        response = session.post(login_url, json=login_payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"Successfully logged into SANtricity at {active_endpoint}")
            # Return True for success - session cookies handle authentication
            return True
        else:
            logger.error(f"Login failed with status {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to login: {e}")
        return False

def logout_session(session, active_endpoint):
    """Logout from SANtricity (clean up session)."""
    logger = logging.getLogger(__name__)
    
    try:
        logout_url = f"{active_endpoint}/devmgr/utils/login"
        response = session.delete(logout_url, timeout=5)
        logger.debug(f"Logged out from SANtricity at {active_endpoint}")
    except Exception as e:
        logger.debug(f"Logout attempt failed (not critical): {e}")

class Settings:
    """Temporary stub for Settings."""
    def __init__(self, config_file=None, from_env=True):
        self.api_endpoints = []
        self.username = "admin"
        self.password = "admin"
        self.interval_time = 60
        self.influxdb_url = None
        self.influxdb_database = None
        self.influxdb_token = None
        self.tls_ca_path = None

def main():
    # CLI argument parsing
    parser = argparse.ArgumentParser(description="Collect E-Series metrics")
    parser.add_argument('--config', type=str, default=None,
        help='Path to YAML or JSON config file. Overrides CLI and .env args if used.')
    parser.add_argument('--api', nargs='+', default=[],
        help='List of E-Series API endpoints (IPv4 or IPv6 addresses or hostnames) to collect from. Overrides config file.')
    parser.add_argument('--username', '-u', type=str, default=None,
        help='Username for SANtricity API authentication. Can also be specified with -u.')
    parser.add_argument('--password', '-p', type=str, default=None,
        help='Password for SANtricity API authentication. Can also be specified with -p. If not provided, will prompt interactively.')
    parser.add_argument('--intervalTime', type=int, default=60,
        help='Collection interval in seconds (minimum 60). Determines how often metrics are collected or replayed.')
    parser.add_argument('--influxdbUrl', type=str, default=None,
        help='InfluxDB server URL (overrides config file and .env if set). Example: https://db.example.com:8181')
    parser.add_argument('--influxdbDatabase', type=str, default=None,
        help='InfluxDB database name (overrides config file and .env if set).')
    parser.add_argument('--influxdbToken', type=str, default=None,
        help='InfluxDB authentication token (overrides config file and .env if set).')
    parser.add_argument('--fromJson', type=str, default=None,
        help='Directory to replay previously collected JSON metrics instead of live collection.')
    parser.add_argument('--tlsCa', type=str, default=None,
        help='Path to CA certificate for verifying API/InfluxDB TLS connections (if not in system trust store).')
    parser.add_argument('--threads', type=int, default=4,
        help='Number of concurrent threads for metric collection. Default: 4. 4 or 8 is typical.')
    parser.add_argument('--tlsValidation', type=str, choices=['strict', 'normal', 'none'], default='strict',
        help='TLS validation mode for SANtricity API: strict (require valid CA and SKI/AKI), normal (default Python validation), none (disable all TLS validation, INSECURE, for testing only). Default: strict.')
    parser.add_argument('--logfile', type=str, default=None,
        help='Path to log file. If not provided, logs to console only.')
    parser.add_argument('--loglevel', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO',
        help='Log level for both console and file output. Default: INFO')
    parser.add_argument('--maxIterations', type=int, default=0,
        help='Maximum number of collection iterations to run before exiting. Default: 0 (run indefinitely). Set to a positive integer to exit after that many iterations.')
    parser.add_argument('--output', choices=['influxdb', 'prometheus', 'both'], default='influxdb',
        help='Output destination: influxdb (default), prometheus (metrics server), or both.')
    parser.add_argument('--prometheusPort', type=int, default=8000,
        help='Port for Prometheus metrics server (default: 8000).')

    CMD = parser.parse_args()

    # Configure logging
    FORMAT = '%(asctime)s - %(levelname)s - %(funcName)s - %(lineno)d - %(message)s'
    log_level = getattr(logging, CMD.loglevel.upper())
    if CMD.logfile:
        logging.basicConfig(filename=CMD.logfile, level=log_level,
                            format=FORMAT, datefmt='%Y-%m-%dT%H:%M:%SZ')
        logging.info('Logging to file: ' + CMD.logfile)
    else:
        logging.basicConfig(level=log_level, format=FORMAT,
                            datefmt='%Y-%m-%dT%H:%M:%SZ')
    
    # Configure external module log levels - prevent credential leakage in DEBUG
    # Never allow requests/urllib3 to log below INFO level due to credential exposure in URLs
    requests_level = max(log_level, logging.INFO)
    logging.getLogger("requests").setLevel(level=requests_level)
    logging.getLogger("urllib3").setLevel(level=requests_level)
    logging.getLogger("influxdb_client").setLevel(level=log_level)
    
    # Initialize main logger after configuration
    LOG = logging.getLogger(__name__)
    
    # Validate arguments
    if CMD.intervalTime < 60:
        print("Error: --intervalTime must be at least 60 seconds.", file=sys.stderr)
        sys.exit(1)
    if CMD.maxIterations < 0:
        print("Error: --maxIterations must be a non-negative integer.", file=sys.stderr)
        sys.exit(1)
    elif CMD.maxIterations > 0:
        LOG.info(f"Will run for {CMD.maxIterations} iterations and then exit")
    
    # Extract API endpoints and credentials
    username = CMD.username
    password = CMD.password
    api_list = list(CMD.api) if CMD.api else []
    
    # Load configuration from file or environment if needed
    settings = None
    if CMD.config is not None:
        settings = Settings(config_file=CMD.config, from_env=False)
    else:
        settings = Settings(from_env=True)
    
    # Override settings with command line arguments if provided
    if not CMD.api and not CMD.fromJson:
        CMD.api = settings.api_endpoints or []
    
    # Get credentials from settings if not provided on command line
    if not username and settings:
        username = settings.username
    if not password and settings:
        password = settings.password
    
    # Prompt for password if needed
    if not password and sys.stdin.isatty():
        try:
            password = getpass.getpass(f"Enter password for SANtricity user '{username or 'monitor'}': ")
        except KeyboardInterrupt:
            print("\nPassword input cancelled.")
            sys.exit(1)
        if not password:
            print("Error: Password cannot be empty.")
            sys.exit(1)
    
    # InfluxDB configuration precedence: CLI > config > env
    # Resolve InfluxDB configuration from CLI args -> env vars -> config file
    import os
    influxdb_url = CMD.influxdbUrl if CMD.influxdbUrl else (
        os.environ.get('INFLUXDB_URL') or (settings.influxdb_url if settings else None)
    )
    influxdb_database = CMD.influxdbDatabase if CMD.influxdbDatabase else (
        os.environ.get('INFLUXDB_DATABASE') or (settings.influxdb_database if settings else None)
    )
    influxdb_auth_token = CMD.influxdbToken if CMD.influxdbToken else (
        os.environ.get('INFLUXDB_TOKEN') or (settings.influxdb_token if settings else None)
    )
    
    # Initialize session variables
    session = None
    access_token = None
    active_endpoint = None
    san_headers = {}
    active_api_list = []
    sys_info = {}
    
    # If fromJson is specified, skip API connection and use JSON collector
    if CMD.fromJson:
        LOG.info(f"Running in JSON replay mode from directory: {CMD.fromJson}")
        if not os.path.exists(CMD.fromJson):
            LOG.error(f"JSON directory does not exist: {CMD.fromJson}")
            sys.exit(1)
        
        # Create dummy system info for JSON mode
        sys_info = {'name': 'JSON_REPLAY', 'wwn': 'JSON_REPLAY_MODE'}
        LOG.info("JSON replay mode initialized - skipping API connection")
    else:
        # Establish API session with simplified authentication
        try:
            LOG.info(f"Establishing API session with endpoints: {CMD.api}")
            session, active_endpoint = get_session(username, password, CMD.api, tls_ca=CMD.tlsCa, tls_validation=CMD.tlsValidation)
            
            LOG.info(f"Successfully connected to controller at {active_endpoint}")
            active_api_list = [active_endpoint.replace('https://', '').replace(':8443', '')]
            
            # Perform initial login (sets session cookies) 
            login_success = get_fresh_token(session, active_endpoint, username, password)
            if login_success:
                LOG.info(f"Successfully authenticated with SANtricity API using session cookies")
                # No headers needed - session cookies handle authentication
                san_headers = {}
            else:
                LOG.error("Failed to authenticate with SANtricity API")
                sys.exit(1)
            
            # Get system information - first get all storage systems, then use the first one's WWN
            try:
                # Get list of all storage systems first
                systems_resp = session.get(f"{get_controller('sys', active_api_list)}", headers=san_headers)
                systems_resp.raise_for_status()
                systems = systems_resp.json()
                
                if not systems or len(systems) == 0:
                    LOG.error("No storage systems found")
                    sys.exit(1)
                
                # Use the first system (or could be made configurable)
                system = systems[0]
                sys_id = system.get("wwn") 
                sys_name = system.get("name")
                
                if not sys_id:
                    LOG.error("Unable to retrieve system WWN - required for metrics collection")
                    sys.exit(1)
                
                LOG.info(f"Connected to E-Series system: WWN={sys_id}, Name={sys_name}")
                sys_info = {'name': sys_name, 'wwn': sys_id}
            except Exception as e:
                LOG.error(f"Failed to retrieve system information: {e}")
                sys.exit(1)
        except Exception as e:
            LOG.error(f"Failed to establish API session: {e}")
            sys.exit(1)
    
    # Initialize cache and config collection scheduler
    config_cache = ConfigCache()
    
    # Initialize config collection scheduler based on user's interval
    try:
        config_scheduler = ConfigCollectionScheduler(CMD.intervalTime)
        LOG.info(f"Initialized config collection scheduler with {CMD.intervalTime}s base interval")
        
        # Log schedule information
        schedule_info = config_scheduler.get_schedule_info()
        LOG.info("Config collection schedule:")
        for freq_name, info in schedule_info.items():
            LOG.info(f"  {freq_name}: every {info['multiplier']}x base ({info['effective_interval']}s) - {info['config_types']}")
    except Exception as e:
        LOG.error(f"Failed to initialize config scheduler: {e}")
        config_scheduler = None
    
    # Import the real ESeriesCollector for JSON mode
    if CMD.fromJson:
        from app.collectors.collector import ESeriesCollector
        from app.schema.models import VolumeConfig, SystemConfig, AnalysedVolumeStatistics
        
        # Configure the ESeriesCollector for JSON mode
        collector_config = {
            'from_json': True,
            'json_directory': CMD.fromJson,
            'json_path': CMD.fromJson  # Legacy config key
        }
        eseries_collector = ESeriesCollector(collector_config)
        LOG.info(f"Initialized ESeriesCollector for JSON directory: {CMD.fromJson}")
        
        # Create stub collectors that delegate to ESeriesCollector
        class JSONConfigCollector:
            def __init__(self, eseries_collector, scheduler=None, config_cache=None):
                self.eseries_collector = eseries_collector
                self.scheduler = scheduler
                self.config_cache = config_cache
                self.logger = logging.getLogger(__name__)
            def collect_config(self, sys_info):
                if not self.scheduler:
                    return {"status": "json_mode", "source": "json_files"}
                
                # Get config types to collect on this iteration
                collections_needed = self.scheduler.get_config_types_for_collection()
                
                if collections_needed:
                    self.logger.info(f"JSON mode: Scheduler indicates collection needed for {len(collections_needed)} frequencies")
                    for frequency, config_types in collections_needed.items():
                        self.logger.info(f"  {frequency.value}: {config_types}")
                    
                    return {
                        "status": "json_scheduled_collection",
                        "source": "json_files",
                        "iteration": self.scheduler.iteration_count,
                        "collections": {freq.value: types for freq, types in collections_needed.items()}
                    }
                else:
                    self.logger.info(f"JSON mode: No config collection needed on iteration {self.scheduler.iteration_count}")
                    return {"status": "json_no_collection", "source": "json_files", "iteration": self.scheduler.iteration_count}
        
        class JSONPerformanceCollector:
            def __init__(self, eseries_collector):
                self.eseries_collector = eseries_collector
            def collect_metrics(self, sys_info):
                return {"status": "json_mode", "source": "json_files"}
        
        # Configure the real collectors for JSON mode
        config_collector = ConfigCollector(
            session=None,
            headers=None,
            api_endpoints=None,
            config_cache=config_cache,
            scheduler=config_scheduler,
            from_json=True,
            json_directory=CMD.fromJson
        )
        
        perf_collector = PerformanceCollector(
            session=None,
            headers=None,
            api_endpoints=None,
            from_json=True,
            json_directory=CMD.fromJson
        )
        
        event_collector = EventCollector(
            session=None,
            headers=None,
            api_endpoints=None,
            from_json=True,
            json_directory=CMD.fromJson
        )
    else:
        # Use real collectors for live API mode
        base_url = get_controller('sys', active_api_list).replace('/devmgr/v2/storage-systems', '')
        config_collector = ConfigCollector(
            session=session,
            headers=san_headers,
            api_endpoints=active_api_list,
            config_cache=config_cache,
            scheduler=config_scheduler,
            from_json=False,
            base_url=base_url,
            system_id=sys_id  # Use actual system WWN
        )
        
        perf_collector = PerformanceCollector(
            session=session,
            headers=san_headers,
            api_endpoints=active_api_list,
            from_json=False,
            base_url=base_url,
            system_id=sys_id  # Use actual system WWN
        )
        
        event_collector = EventCollector(
            session=session,
            headers=san_headers,
            api_endpoints=active_api_list,
            from_json=False,
            base_url=base_url,
            system_id=sys_id  # Use actual system WWN
        )
    
    enrichment_processor = EnrichmentProcessor(config_collector)
    
    # Initialize thread pool
    executor = concurrent.futures.ThreadPoolExecutor(CMD.threads)
    
    # Initialize writer based on configuration
    from app.writer.factory import WriterFactory
    
    # Pass prometheus port through args for factory
    CMD.prometheus_port = CMD.prometheusPort
    
    writer = WriterFactory.create_writer(
        CMD, 
        influxdb_url=influxdb_url,
        influxdb_database=influxdb_database, 
        influxdb_token=influxdb_auth_token,
        system_id=sys_id if not CMD.fromJson else "1"
    )
    LOG.info(f"Writer initialized for output: {CMD.output}")
    
    # Start collection loop
    loop_iteration = 1
    try:
        while True:
            time_start = time.time()
            LOG.info(f"Starting collection iteration {loop_iteration} of {CMD.maxIterations if CMD.maxIterations > 0 else 'unlimited'}")
            
            # Increment scheduler iteration counter
            if config_scheduler:
                config_scheduler.increment_iteration()
                LOG.info(f"Config scheduler iteration: {config_scheduler.iteration_count}")
            
            # Refresh authentication for live API mode (not needed for JSON mode)
            if not CMD.fromJson and session and active_endpoint:
                LOG.debug("Refreshing SANtricity authentication for this iteration")
                login_success = get_fresh_token(session, active_endpoint, username, password)
                if login_success:
                    # No headers needed - session cookies handle authentication
                    san_headers = {}
                    LOG.debug("Successfully refreshed authentication session")
                else:
                    LOG.error("Failed to refresh authentication - continuing with existing session")
            
            if CMD.fromJson:
                # JSON replay mode - demonstrate batched reading
                try:
                    LOG.info("=== JSON Replay Mode - Batched Data Collection ===")
                    
                    # Get batch information
                    batch_info = eseries_collector.get_batch_info()
                    LOG.info(f"Batch reader initialized: {batch_info['available_batches']} batches available")
                    LOG.info(f"Batch window: {batch_info['batch_window_minutes']} minutes")
                    LOG.info(f"Total files: {batch_info['total_files']}")
                    
                    # Check if we have batches available and haven't exhausted them
                    if batch_info['available_batches'] > 0 and eseries_collector.batched_reader and eseries_collector.batched_reader.has_more_batches():
                        current_batch_info = eseries_collector.batched_reader.get_current_batch_info() if eseries_collector.batched_reader else None
                        if current_batch_info:
                            LOG.info(f"Processing batch {current_batch_info[0]} of {batch_info['available_batches']}...")
                        else:
                            LOG.info("Processing current batch...")
                        
                        # Collect system configuration from current batch
                        from app.schema.models import SystemConfig
                        system_config = eseries_collector.collect_system_config_from_current_batch(SystemConfig)
                        if system_config:
                            LOG.info(f"System config collected - WWN: {system_config.wwn}, Name: {system_config.name}")
                            LOG.info(f"Drive count: {system_config.driveCount}, Model: {system_config.model}")
                        else:
                            LOG.info("No system config data in current batch")
                        
                        # Collect volume configuration from current batch
                        from app.schema.models import VolumeConfig
                        volumes = eseries_collector.collect_volumes_from_current_batch(VolumeConfig)
                        LOG.info(f"Collected {len(volumes)} volumes from current batch")
                        if volumes:
                            vol = volumes[0]
                            LOG.info(f"First volume - ID: {vol.id}, Label: {vol.label}, Capacity: {vol.capacity}")
                        
                        # Collect performance data from current batch
                        from app.schema.models import AnalysedVolumeStatistics
                        volume_perf = eseries_collector.collect_performance_data_from_current_batch(
                            AnalysedVolumeStatistics, 'analysed-volume-statistics')
                        LOG.info(f"Collected {len(volume_perf)} volume performance records from current batch")
                        if volume_perf:
                            perf = volume_perf[0]
                            LOG.info(f"First perf record - Volume: {perf.volumeId}, IOPs: {perf.combinedIOps}, Observed: {perf.observedTime}")
                        
                        # Advance to next batch after processing all data types
                        batch_advanced = eseries_collector.advance_batch()
                        LOG.info(f"Advanced to next batch: {batch_advanced}")
                        
                        config_data = {"json_mode": True, "batch_processed": 1, "total_batches": batch_info['available_batches']}
                        # Pass volume performance records directly as a list for enrichment
                        # Convert dataclass instances to dictionaries for enrichment processor
                        perf_data = []
                        for perf_record in volume_perf:
                            if hasattr(perf_record, '_raw_data'):
                                perf_data.append(perf_record._raw_data)
                            elif hasattr(perf_record, '__dict__'):
                                perf_data.append(perf_record.__dict__)
                            else:
                                # Fallback if it's already a dict
                                perf_data.append(perf_record)
                    else:
                        LOG.warning("No more batches available for processing - stopping iterations")
                        config_data = {"json_mode": True, "batch_processed": 0, "total_batches": batch_info['available_batches'], "exhausted": True}
                        perf_data = {}
                        
                        # Signal that we should stop looping
                        if 'exhausted' in config_data:
                            LOG.info("All JSON batches processed - exiting")
                            break
                    
                except Exception as e:
                    LOG.error(f"Failed to process JSON data: {e}", exc_info=True)
                    config_data = {}
                    perf_data = {}
            else:
                # Live API mode
                # Collect configuration data first
                try:
                    # Collect configuration data (assuming a collect_config method)
                    config_data = config_collector.collect_config(sys_info)
                    LOG.info(f"Collected configuration data successfully")
                except Exception as e:
                    LOG.error(f"Failed to collect configuration data: {e}")
                    config_data = {}
                
                # Collect performance data
                try:
                    # Collect performance data (assuming a collect_performance method)
                    perf_result = perf_collector.collect_metrics(sys_info)
                    # Extract actual performance data from wrapper structure
                    perf_data = perf_result.get('performance_data', {}) if isinstance(perf_result, dict) and 'performance_data' in perf_result else perf_result
                    LOG.info(f"Collected performance data successfully")
                except Exception as e:
                    LOG.error(f"Failed to collect performance data: {e}")
                    perf_data = {}
                
                # Collect event data
                try:
                    # Collect event/status data
                    event_data = event_collector.collect_events(sys_info)
                    LOG.info(f"Collected event data: {event_data.get('total_active', 0)} active events")
                    
                    # Log any high-priority events - lockdown detection removed due to false positives
                        
                except Exception as e:
                    LOG.error(f"Failed to collect event data: {e}")
                    event_data = {}
            
            # Enrich performance data with configuration data
            try:
                # Debug: Check perf_data structure before enrichment
                LOG.info(f"🔍 DEBUG - perf_data before enrichment: type={type(perf_data)}")
                if isinstance(perf_data, dict):
                    LOG.info(f"🔍 DEBUG - perf_data keys: {list(perf_data.keys())}")
                    for key, value in perf_data.items():
                        if isinstance(value, list) and len(value) > 0:
                            LOG.info(f"🔍 DEBUG - {key}: {len(value)} items, first item keys: {list(value[0].keys()) if isinstance(value[0], dict) else 'Not a dict'}")
                
                # Process and enrich data
                enriched_data = enrichment_processor.process(perf_data)
                LOG.info(f"Enriched performance data successfully - type: {type(enriched_data)}")
                
                # Debug: Check enriched_data structure after enrichment
                if isinstance(enriched_data, dict):
                    LOG.info(f"Enriched data keys: {list(enriched_data.keys())}")
                    for key, value in enriched_data.items():
                        if isinstance(value, list) and len(value) > 0:
                            LOG.info(f"🔍 DEBUG - enriched {key}: {len(value)} items, first item keys: {list(value[0].keys()) if isinstance(value[0], dict) else 'Not a dict'}")
                elif isinstance(enriched_data, list):
                    LOG.info(f"Enriched data list length: {len(enriched_data)}")
            except Exception as e:
                LOG.error(f"Failed to enrich performance data: {e}", exc_info=True)
                enriched_data = perf_data
            
            # Send enriched data to writer if available
            if writer:
                try:
                    # Structure data properly for writer - use measurement type names as keys
                    if isinstance(enriched_data, list):
                        # For lists of performance records, wrap in appropriate measurement type name
                        writer_data = {"analysed_volume_statistics": enriched_data}
                    elif isinstance(enriched_data, dict):
                        # Already a dictionary, pass through
                        writer_data = enriched_data
                    
                    # Debug: Check what we're sending to the writer
                    LOG.info(f"🔍 DEBUG - Sending to writer: {list(writer_data.keys())}")
                    for key, value in writer_data.items():
                        if isinstance(value, list) and len(value) > 0:
                            item_type = type(value[0]).__name__
                            LOG.info(f"🔍 DEBUG - {key}: {len(value)} items of type {item_type}")
                            if hasattr(value[0], '__dict__'):
                                LOG.info(f"🔍 DEBUG - First {key} item attrs: {list(value[0].__dict__.keys())[:10]}")
                    else:
                        # Fallback
                        writer_data = {"performance_data": enriched_data}
                    
                    success = writer.write(writer_data)
                    if success:
                        LOG.info("Data successfully written to output destination")
                    else:
                        LOG.error("Failed to write data to output destination")
                except Exception as e:
                    LOG.error(f"Error writing data: {e}")
            else:
                LOG.warning("No writer available - data not persisted")
            
            # Complete the iteration
            time_end = time.time()
            elapsed = time_end - time_start
            
            # Increment loop counter
            loop_iteration += 1
            
            # Check if we've reached the maximum number of iterations
            if CMD.maxIterations > 0 and loop_iteration > CMD.maxIterations:
                LOG.info(f"Reached maximum number of iterations ({CMD.maxIterations}). Exiting gracefully.")
                break
            
            # Sleep for the remaining interval time
            if elapsed < CMD.intervalTime:
                LOG.info(f"Sleeping for {CMD.intervalTime - elapsed:.2f} seconds until next collection")
                time.sleep(CMD.intervalTime - elapsed)
    
    except KeyboardInterrupt:
        LOG.info("Interrupted by user. Exiting gracefully.")
    finally:
        # Clean up session and logout
        if 'session' in locals() and session and 'active_endpoint' in locals() and active_endpoint:
            logout_session(session, active_endpoint)
            session.close()
        executor.shutdown()
