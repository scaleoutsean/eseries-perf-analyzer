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

# Import enrichment classes
from app.enrichment.event_enrichment import EventEnrichment

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

    def enrich_config_data(self, config_data_dict, sys_info=None):
        """Enrich configuration data with system information for better InfluxDB tags."""
        if not isinstance(config_data_dict, dict):
            return config_data_dict
            
        # Load enrichment data if needed
        self._load_enrichment_data()
        
        enriched_config = {}
        
        for config_type, config_items in config_data_dict.items():
            if not isinstance(config_items, list) or not config_items:
                enriched_config[config_type] = config_items
                continue
                
            enriched_items = []
            
            for config_item in config_items:
                # Start with original item
                enriched_item = config_item.copy() if isinstance(config_item, dict) else config_item
                
                # Extract raw data if it's a BaseModel object
                if hasattr(config_item, '_raw_data'):
                    enriched_item = config_item._raw_data.copy()
                elif hasattr(config_item, '__dict__'):
                    enriched_item = config_item.__dict__.copy()
                
                # Add system information - prioritize cache (real data), fallback to sys_info
                if self.system_enricher and self.system_enricher.system_config_cache:
                    # Use system enricher cache (preferred - has real data from JSON/API)
                    # Just take the first (and likely only) system in the cache
                    for system_wwn, system_config in self.system_enricher.system_config_cache.items():
                        if isinstance(system_config, dict):
                            enriched_item['storage_system'] = system_config.get('name', system_config.get('id', system_wwn))
                            enriched_item['storage_system_wwn'] = system_config.get('wwn', system_wwn)
                            enriched_item['storage_system_model'] = system_config.get('model', 'unknown')
                            break
                elif sys_info and isinstance(sys_info, dict):
                    # Fallback to sys_info parameter
                    enriched_item['storage_system'] = sys_info.get('name', sys_info.get('id', 'unknown'))
                    enriched_item['storage_system_wwn'] = sys_info.get('wwn', sys_info.get('world_wide_name', 'unknown'))
                    enriched_item['storage_system_model'] = sys_info.get('model', 'unknown')
                else:
                    # No system info available
                    enriched_item['storage_system'] = 'unknown'
                    enriched_item['storage_system_wwn'] = 'unknown'
                    enriched_item['storage_system_model'] = 'unknown'
                
                # Type-specific enrichment
                if config_type == 'HostConfig':
                    # Add valuable host fields that were getting dropped
                    if hasattr(config_item, 'label') and config_item.label:
                        enriched_item['host_name'] = config_item.label
                    elif hasattr(config_item, 'name') and config_item.name:
                        enriched_item['host_name'] = config_item.name
                    else:
                        enriched_item['host_name'] = enriched_item.get('label', enriched_item.get('name', 'unknown'))
                
                elif config_type == 'VolumeConfig':
                    # Add valuable volume fields
                    enriched_item['volume_name'] = enriched_item.get('label', enriched_item.get('name', 'unknown'))
                    enriched_item['volume_capacity'] = enriched_item.get('capacity', enriched_item.get('totalSizeInBytes', 0))
                
                elif config_type == 'VolumeMappingsConfig':
                    # Cross-reference volume information for mappings
                    volume_ref = enriched_item.get('volumeRef', 'unknown')
                    # Try to find volume info from volume enricher lookup
                    if hasattr(self.volume_enricher, 'volume_lookup') and volume_ref in self.volume_enricher.volume_lookup:
                        vol_data = self.volume_enricher.volume_lookup[volume_ref]
                        enriched_item['volume_name'] = vol_data.get('label', vol_data.get('name', 'unknown'))
                        enriched_item['pool_id'] = vol_data.get('volumeGroupRef', 'unknown')
                    else:
                        enriched_item['volume_name'] = 'unknown'
                        enriched_item['pool_id'] = 'unknown'
                
                elif config_type == 'StoragePoolConfig':
                    # Add valuable pool fields  
                    enriched_item['pool_name'] = enriched_item.get('label', enriched_item.get('name', 'unknown'))
                    enriched_item['pool_raid_level'] = enriched_item.get('raidLevel', 'unknown')
                    enriched_item['pool_capacity'] = enriched_item.get('totalRaidedSpace', 0)
                
                enriched_items.append(enriched_item)
            
            enriched_config[config_type] = enriched_items
            self.logger.info(f"Enriched {len(enriched_items)} {config_type} items with system information")
        
        return enriched_config

    def enrich_event_data(self, event_data_list, sys_info=None):
        """Enrich event data with system information for better InfluxDB tags."""
        if not isinstance(event_data_list, list):
            return event_data_list
            
        # Load enrichment data if needed
        self._load_enrichment_data()
        
        enriched_events = []
        
        for event_item in event_data_list:
            # Start with original item
            enriched_item = event_item.copy() if isinstance(event_item, dict) else event_item
            
            # Extract raw data if it's a BaseModel object
            if hasattr(event_item, '_raw_data'):
                enriched_item = event_item._raw_data.copy()
            elif hasattr(event_item, '__dict__'):
                enriched_item = event_item.__dict__.copy()
            
            # Add system information - prioritize cache (real data), fallback to sys_info
            if self.system_enricher and self.system_enricher.system_config_cache:
                # Use system enricher cache (preferred - has real data from JSON/API)
                for system_wwn, system_config in self.system_enricher.system_config_cache.items():
                    if isinstance(system_config, dict):
                        enriched_item['storage_system'] = system_config.get('name', system_config.get('id', system_wwn))
                        enriched_item['storage_system_wwn'] = system_config.get('wwn', system_wwn) 
                        enriched_item['storage_system_model'] = system_config.get('model', 'unknown')
                        break
            elif sys_info and isinstance(sys_info, dict):
                # Fallback to sys_info parameter
                enriched_item['storage_system'] = sys_info.get('name', sys_info.get('id', 'unknown'))
                enriched_item['storage_system_wwn'] = sys_info.get('wwn', sys_info.get('world_wide_name', 'unknown'))
                enriched_item['storage_system_model'] = sys_info.get('model', 'unknown')
            else:
                # No system info available
                enriched_item['storage_system'] = 'unknown'
                enriched_item['storage_system_wwn'] = 'unknown'
                enriched_item['storage_system_model'] = 'unknown'
            
            enriched_events.append(enriched_item)
        
        self.logger.info(f"Enriched {len(enriched_events)} event items with system information")
        return enriched_events

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
    
    # Initialize event enrichment for deduplication
    event_enrichment = EventEnrichment({
        'enable_event_deduplication': True,
        'event_dedup_window_minutes': 5,
        'enable_grafana_annotations': False
    }, enrichment_processor.system_enricher)
    LOG.info("EventEnrichment initialized with deduplication enabled and system enricher cache")
    
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
                        
                        # Collect all performance data types from current batch
                        from app.schema.models import AnalysedVolumeStatistics, AnalysedDriveStatistics, AnalysedSystemStatistics, AnalysedInterfaceStatistics, AnalyzedControllerStatistics
                        
                        # Volume performance
                        volume_perf = eseries_collector.collect_performance_data_from_current_batch(
                            AnalysedVolumeStatistics, 'analysed-volume-statistics')
                        LOG.info(f"Collected {len(volume_perf)} volume performance records from current batch")
                        if volume_perf:
                            perf = volume_perf[0]
                            LOG.info(f"First perf record - Volume: {perf.volumeId}, IOPs: {perf.combinedIOps}, Observed: {perf.observedTime}")
                        
                        # Drive performance
                        drive_perf = eseries_collector.collect_performance_data_from_current_batch(
                            AnalysedDriveStatistics, 'analysed-drive-statistics')
                        LOG.info(f"Collected {len(drive_perf)} drive performance records from current batch")
                        
                        # System performance  
                        system_perf = eseries_collector.collect_performance_data_from_current_batch(
                            AnalysedSystemStatistics, 'analysed-system-statistics')
                        LOG.info(f"Collected {len(system_perf)} system performance records from current batch")
                        
                        # Interface performance
                        interface_perf = eseries_collector.collect_performance_data_from_current_batch(
                            AnalysedInterfaceStatistics, 'analysed-interface-statistics')
                        LOG.info(f"Collected {len(interface_perf)} interface performance records from current batch")
                        
                        # Controller performance (note: 'analyzed' with 'z')
                        controller_perf = eseries_collector.collect_performance_data_from_current_batch(
                            AnalyzedControllerStatistics, 'analyzed-controller-statistics')
                        LOG.info(f"Collected {len(controller_perf)} controller performance records from current batch")
                        
                        # Advance to next batch after processing all data types
                        batch_advanced = eseries_collector.advance_batch()
                        LOG.info(f"Advanced to next batch: {batch_advanced}")
                        
                        # Collect configuration data in JSON mode
                        try:
                            config_data = config_collector.collect_config(sys_info)
                            LOG.info(f"🔍 DEBUG Checkpoint 2C-JSON: config_data collected, type={type(config_data)}, keys={list(config_data.keys()) if isinstance(config_data, dict) else 'Not a dict'}")
                            # Add JSON mode metadata
                            if isinstance(config_data, dict):
                                config_data["json_mode"] = True
                                config_data["batch_processed"] = 1
                                config_data["total_batches"] = batch_info['available_batches']
                            else:
                                config_data = {"json_mode": True, "batch_processed": 1, "total_batches": batch_info['available_batches'], "original_data": config_data}
                        except Exception as e:
                            LOG.error(f"Failed to collect config data in JSON mode: {e}")
                            config_data = {"json_mode": True, "batch_processed": 1, "total_batches": batch_info['available_batches'], "error": str(e)}
                        
                        # Combine all performance data types for processing
                        all_performance_data = {
                            'analysed_volume_statistics': volume_perf,
                            'analysed_drive_statistics': drive_perf, 
                            'analysed_system_statistics': system_perf,
                            'analysed_interface_statistics': interface_perf,
                            'analyzed_controller_statistics': controller_perf
                        }
                        
                        # Convert performance records to dictionaries for processing
                        perf_data = {}
                        for perf_type, records in all_performance_data.items():
                            perf_data[perf_type] = []
                            for perf_record in records:
                                if hasattr(perf_record, '_raw_data'):
                                    perf_data[perf_type].append(perf_record._raw_data)
                                elif hasattr(perf_record, '__dict__'):
                                    perf_data[perf_type].append(perf_record.__dict__)
                                else:
                                    # Fallback if it's already a dict
                                    perf_data[perf_type].append(perf_record)
                    else:
                        LOG.warning("No more batches available for processing - stopping iterations")
                        # Try to collect config data even when exhausted
                        try:
                            config_data = config_collector.collect_config(sys_info)
                            LOG.info(f"🔍 DEBUG Checkpoint 2C-JSON-EXHAUSTED: config_data collected, type={type(config_data)}, keys={list(config_data.keys()) if isinstance(config_data, dict) else 'Not a dict'}")
                        except Exception as e:
                            LOG.error(f"Failed to collect config data when exhausted: {e}")
                            config_data = {}
                        
                        perf_data = {}
                        
                        # Signal that we should stop looping
                        LOG.info("All JSON batches processed - exiting")
                        break
                    
                    # Collect event data in JSON mode
                    try:
                        event_data = event_collector.collect_events(sys_info)
                        LOG.info(f"Collected event data from JSON: {event_data.get('total_active', 0)} active events")
                    except Exception as e:
                        LOG.error(f"Failed to collect event data from JSON: {e}")
                        event_data = {}
                    
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
                    # Collect performance data from all performance types
                    perf_result = perf_collector.collect_metrics(sys_info)
                    # Extract actual performance data from wrapper structure
                    perf_data = perf_result.get('performance_data', {}) if isinstance(perf_result, dict) and 'performance_data' in perf_result else perf_result
                    LOG.info(f"Collected performance data successfully: {list(perf_data.keys()) if isinstance(perf_data, dict) else 'single type'}")
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
                        if isinstance(value, list):
                            LOG.info(f"🔍 DEBUG - {key}: {len(value)} items")
                
                # Process and enrich data - handle multiple performance types
                enriched_data = {}
                if isinstance(perf_data, dict):
                    # Process each performance type separately
                    for perf_type, perf_records in perf_data.items():
                        if isinstance(perf_records, list) and len(perf_records) > 0:
                            LOG.info(f"Enriching {perf_type}: {len(perf_records)} records")
                            enriched_records = enrichment_processor.process(perf_records, measurement_type=perf_type)
                            enriched_data[perf_type] = enriched_records
                            LOG.info(f"✅ Enriched {perf_type}: {len(enriched_records)} records")
                        elif isinstance(perf_records, list):
                            LOG.info(f"No {perf_type} data to enrich (empty list)")
                        else:
                            LOG.warning(f"Unexpected {perf_type} data type: {type(perf_records)}")
                else:
                    # Legacy handling for single performance type (backwards compatibility)
                    enriched_data = enrichment_processor.process(perf_data)
                
                LOG.info(f"Enriched performance data successfully - {len(enriched_data)} performance types processed")
                
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
                LOG.error("🔥🔥🔥 ENTERING WRITER SECTION - DEBUG CHECKPOINT 1")
                print("🔥🔥🔥 ENTERING WRITER SECTION - DEBUG CHECKPOINT 1")
                try:
                    # Initialize writer_data with performance data
                    writer_data = {}
                    
                    # Add performance data - map performance types to InfluxDB measurement names
                    performance_type_mapping = {
                        'volume_performance': 'analysed_volume_statistics',
                        'drive_performance': 'analysed_drive_statistics', 
                        'controller_performance': 'analysed_controller_statistics',
                        'system_performance': 'analysed_system_statistics',
                        'interface_performance': 'analysed_interface_statistics'
                    }
                    
                    if isinstance(enriched_data, dict):
                        # Handle multiple performance types
                        for perf_type, perf_records in enriched_data.items():
                            if isinstance(perf_records, list) and len(perf_records) > 0:
                                # Map to correct measurement name
                                measurement_name = performance_type_mapping.get(perf_type, perf_type)
                                writer_data[measurement_name] = perf_records
                                LOG.info(f"Adding {len(perf_records)} {measurement_name} records to write")
                    elif isinstance(enriched_data, list):
                        # Legacy handling - assume volume performance
                        writer_data["analysed_volume_statistics"] = enriched_data
                        LOG.info(f"Adding {len(enriched_data)} volume performance records to write (legacy mode)")
                    else:
                        # Fallback
                        writer_data["performance_data"] = enriched_data
                    
                    LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2 - Data preparation complete")
                    print("🔥🔥🔥 DEBUG CHECKPOINT 2 - Data preparation complete")
                    
                    LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2A - About to check config data")
                    print("🔥🔥🔥 DEBUG CHECKPOINT 2A - About to check config data")
                    
                    # Add config data if collection was scheduled for this iteration
                    LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2C - About to process config data")
                    print("🔥🔥🔥 DEBUG CHECKPOINT 2C - About to process config data")
                    
                    if isinstance(config_data, dict) and config_data.get("status") == "scheduled_collection":
                        collected_config = config_data.get("collected_data", {})
                        if isinstance(collected_config, dict) and collected_config:
                            LOG.info(f"Adding config data to write: {list(collected_config.keys())}")
                            
                            # Enrich config data with storage_system and valuable fields
                            enriched_config_data = enrichment_processor.enrich_config_data(collected_config, sys_info)
                            
                            # Add each config type as a separate measurement
                            for config_type, config_items in enriched_config_data.items():
                                if config_items:  # Only add non-empty config data
                                    writer_data[f"config_{config_type.lower()}"] = config_items
                    
                    LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2D - Config processing complete, about to process events")
                    print("🔥🔥🔥 DEBUG CHECKPOINT 2D - Config processing complete, about to process events")
                    
                    # Process event data with deduplication
                    LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2E - Starting event processing check")
                    print("🔥🔥🔥 DEBUG CHECKPOINT 2E - Starting event processing check")
                    
                    LOG.error(f"🔥🔥🔥 DEBUG CHECKPOINT 2F - event_data type: {type(event_data)}")
                    print(f"🔥🔥🔥 DEBUG CHECKPOINT 2F - event_data type: {type(event_data)}")
                    
                    if isinstance(event_data, dict) and event_data:
                        LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2H - Inside event processing block")
                        print("🔥🔥🔥 DEBUG CHECKPOINT 2H - Inside event processing block")
                        processed_events = []
                        events_to_process = None
                        
                        # Extract events from the event_data structure
                        LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2I - About to extract events")
                        print("🔥🔥🔥 DEBUG CHECKPOINT 2I - About to extract events")
                        
                        if "events" in event_data and event_data["events"]:
                            events_to_process = event_data["events"]
                            LOG.error(f"🔥🔥🔥 DEBUG CHECKPOINT 2J - Found events: {len(event_data['events'])} types")
                            print(f"🔥🔥🔥 DEBUG CHECKPOINT 2J - Found events: {len(event_data['events'])} types")
                        elif "active_events" in event_data and event_data["active_events"]:
                            events_to_process = event_data["active_events"]
                            LOG.error(f"🔥🔥🔥 DEBUG CHECKPOINT 2K - Found active_events: {len(event_data['active_events'])} types")
                            print(f"🔥🔥🔥 DEBUG CHECKPOINT 2K - Found active_events: {len(event_data['active_events'])} types")
                        
                        LOG.error(f"🔥🔥🔥 DEBUG CHECKPOINT 2L - events_to_process: {events_to_process is not None}")
                        print(f"🔥🔥🔥 DEBUG CHECKPOINT 2L - events_to_process: {events_to_process is not None}")
                        
                        if events_to_process:
                            # Process each event type through deduplication
                            LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2M - Starting event loop processing")
                            print("🔥🔥🔥 DEBUG CHECKPOINT 2M - Starting event loop processing")
                            total_events_before = 0
                            total_events_after = 0
                            
                            LOG.error(f"🔥🔥🔥 DEBUG CHECKPOINT 2N - About to iterate over {len(events_to_process)} event types")
                            print(f"🔥🔥🔥 DEBUG CHECKPOINT 2N - About to iterate over {len(events_to_process)} event types")
                            
                            for endpoint_name, event_list in events_to_process.items():
                                LOG.error(f"🔥🔥🔥 DEBUG CHECKPOINT 2O - Processing {endpoint_name}")
                                print(f"🔥🔥🔥 DEBUG CHECKPOINT 2O - Processing {endpoint_name}")
                                if isinstance(event_list, list) and event_list:
                                    # Skip volume expansion progress events - mostly inactive placeholder data
                                    # TODO: Re-evaluate when we understand what constitutes meaningful expansion events
                                    if "volume_expansion_progress" in endpoint_name.lower():
                                        LOG.info(f"Event {endpoint_name}: {len(event_list)} → 0 (skipped - mostly inactive data)")
                                        continue
                                    
                                    total_events_before += len(event_list)
                                    LOG.error(f"🔥🔥🔥 DEBUG CHECKPOINT 2P - About to enrich {len(event_list)} {endpoint_name} events")
                                    print(f"🔥🔥🔥 DEBUG CHECKPOINT 2P - About to enrich {len(event_list)} {endpoint_name} events")
                                    
                                    # Apply deduplication
                                    enriched_events = event_enrichment.enrich_event_data(
                                        endpoint_name, event_list, sys_info
                                    )
                                    LOG.error(f"🔥🔥🔥 DEBUG CHECKPOINT 2Q - Event enrichment completed for {endpoint_name}")
                                    print(f"🔥🔥🔥 DEBUG CHECKPOINT 2Q - Event enrichment completed for {endpoint_name}")
                                    
                                    # Add storage_system enrichment to deduplicated events
                                    if enriched_events:
                                        enriched_events = enrichment_processor.enrich_event_data(enriched_events, sys_info)
                                        LOG.info(f"Events enriched with storage_system tags for {endpoint_name}")
                                    
                                    if enriched_events:
                                        processed_events.extend(enriched_events)
                                        total_events_after += len(enriched_events)
                                        LOG.info(f"Event {endpoint_name}: {len(event_list)} → {len(enriched_events)} (after dedup)")
                                    else:
                                        LOG.info(f"Event {endpoint_name}: {len(event_list)} → 0 (duplicate/filtered)")
                            
                            LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2B-PRE - About to check processed_events")
                            print("🔥🔥🔥 DEBUG CHECKPOINT 2B-PRE - About to check processed_events")
                            
                            if processed_events:
                                LOG.error(f"🔥🔥🔥 DEBUG CHECKPOINT 2B-1 - Adding {len(processed_events)} events to writer_data")
                                print(f"🔥🔥🔥 DEBUG CHECKPOINT 2B-1 - Adding {len(processed_events)} events to writer_data")
                                try:
                                    writer_data["system_events"] = processed_events
                                    LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2B-2 - Successfully assigned events to writer_data")
                                    print("🔥🔥🔥 DEBUG CHECKPOINT 2B-2 - Successfully assigned events to writer_data")
                                except Exception as events_e:
                                    LOG.error(f"🚨 EXCEPTION assigning events to writer_data: {events_e}")
                                    print(f"🚨 EXCEPTION assigning events to writer_data: {events_e}")
                                    raise
                                LOG.info(f"Adding {len(processed_events)} events to write (filtered from {total_events_before} total)")
                            else:
                                LOG.info(f"No events to write after deduplication (filtered {total_events_before} duplicates)")
                                
                            LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 2B - Event processing loop completed")
                            print("🔥🔥🔥 DEBUG CHECKPOINT 2B - Event processing loop completed")
                    
                    try:
                        LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 3 PRE-CHECK - Before checkpoint 3")
                        print("🔥🔥🔥 DEBUG CHECKPOINT 3 PRE-CHECK - Before checkpoint 3")
                        LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 3 - Event processing complete, about to convert data")
                        print("🔥🔥🔥 DEBUG CHECKPOINT 3 - Event processing complete, about to convert data")
                    except Exception as checkpoint_e:
                        LOG.error(f"🚨 EXCEPTION caught at checkpoint 3: {checkpoint_e}")
                        print(f"🚨 EXCEPTION caught at checkpoint 3: {checkpoint_e}")
                        raise  # Re-raise to maintain original behavior
                    
                    # Debug: Check what we're sending to the writer
                    LOG.info(f"� WRITER DEBUG - About to process {len(writer_data)} data types")
                    LOG.info(f"�🔍 DEBUG - Sending to writer: {list(writer_data.keys())}")
                    for key, value in writer_data.items():
                        if isinstance(value, list) and len(value) > 0:
                            item_type = type(value[0]).__name__
                            LOG.info(f"🔍 DEBUG - {key}: {len(value)} items of type {item_type}")
                            LOG.info(f"🔍 DEBUG - First {key} item type check - hasattr model_dump: {hasattr(value[0], 'model_dump')}")
                            LOG.info(f"🔍 DEBUG - First {key} item type check - hasattr __dict__: {hasattr(value[0], '__dict__')}")
                            LOG.info(f"🔍 DEBUG - First {key} item type check - is BaseModel: {value[0].__class__.__name__}")
                    
                    LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 4 - About to start BaseModel conversion")
                    print("🔥🔥🔥 DEBUG CHECKPOINT 4 - About to start BaseModel conversion")
                    
                    # Convert BaseModel objects to dictionaries for JSON serialization
                    def convert_to_serializable(obj, depth=0, max_depth=10):
                        """Recursively convert objects to JSON-serializable format."""
                        # Prevent infinite recursion
                        if depth > max_depth:
                            return f"<MAX_DEPTH_REACHED:{type(obj).__name__}>"
                        
                        # Log problematic types for debugging
                        obj_type = type(obj)
                        type_name = obj_type.__name__
                        module_name = getattr(obj_type, '__module__', 'unknown')
                        
                        # Handle None first
                        if obj is None:
                            return None
                        
                        # Handle basic JSON-serializable types
                        if isinstance(obj, (str, int, float, bool)):
                            return obj
                        
                        # Handle BaseModel objects with comprehensive checks
                        if (hasattr(obj, 'model_dump') or 
                            type_name == 'BaseModel' or 
                            'BaseModel' in str(obj_type.__bases__) or
                            'pydantic' in module_name.lower() or
                            hasattr(obj, 'model_fields')):
                            LOG.debug(f"Converting BaseModel object: {type_name} from {module_name}")
                            if hasattr(obj, 'model_dump'):
                                return convert_to_serializable(obj.model_dump(), depth + 1, max_depth)
                            elif hasattr(obj, 'dict'):
                                return convert_to_serializable(obj.dict(), depth + 1, max_depth)
                            elif hasattr(obj, '__dict__'):
                                return convert_to_serializable(obj.__dict__, depth + 1, max_depth)
                            else:
                                LOG.warning(f"BaseModel object {type_name} has no serialization method")
                                return str(obj)
                        
                        # Handle dictionaries recursively
                        elif isinstance(obj, dict):
                            return {key: convert_to_serializable(value, depth + 1, max_depth) for key, value in obj.items()}
                        
                        # Handle lists recursively
                        elif isinstance(obj, list):
                            return [convert_to_serializable(item, depth + 1, max_depth) for item in obj]
                        
                        # Handle tuples recursively
                        elif isinstance(obj, tuple):
                            return tuple(convert_to_serializable(item, depth + 1, max_depth) for item in obj)
                        
                        # Handle datetime objects
                        elif hasattr(obj, 'isoformat'):
                            return obj.isoformat()
                        
                        # Handle objects with __dict__ (custom classes)
                        elif hasattr(obj, '__dict__') and not isinstance(obj, type):
                            LOG.debug(f"Converting custom object: {type_name} from {module_name}")
                            return convert_to_serializable(obj.__dict__, depth + 1, max_depth)
                        
                        # Last resort: convert to string with warning
                        else:
                            LOG.warning(f"Converting unknown object type to string: {type_name} from {module_name}")
                            return str(obj)

                    serializable_data = {}
                    for key, value in writer_data.items():
                        try:
                            LOG.info(f"Converting {key} data: {len(value) if hasattr(value, '__len__') else 1} items")
                            serializable_data[key] = convert_to_serializable(value)
                            LOG.info(f"Successfully converted {key} to serializable format")
                        except Exception as conv_e:
                            LOG.error(f"Failed to convert {key}: {conv_e}")
                            LOG.error(f"Value type: {type(value)}")
                            if hasattr(value, '__len__') and len(value) > 0:
                                LOG.error(f"First item type: {type(value[0])}")
                            # Try simple dict conversion as fallback
                            if hasattr(value, '__dict__'):
                                serializable_data[key] = value.__dict__
                            elif isinstance(value, list):
                                # Try converting each item individually
                                fallback_items = []
                                for item in value:
                                    if hasattr(item, '__dict__'):
                                        fallback_items.append(item.__dict__)
                                    else:
                                        fallback_items.append(item)
                                serializable_data[key] = fallback_items
                            else:
                                serializable_data[key] = value
                    
                    LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 5 - BaseModel conversion completed")
                    print("🔥🔥🔥 DEBUG CHECKPOINT 5 - BaseModel conversion completed")
                    
                    # Final check before writing - ensure complete JSON serializability
                    LOG.info(f"🔍 DEBUG - About to write: {list(serializable_data.keys())}")
                    for key, value in serializable_data.items():
                        if isinstance(value, list) and len(value) > 0:
                            LOG.info(f"🔍 DEBUG - {key}: {len(value)} items, first type: {type(value[0])}")
                    
                    # Final safety check - try JSON serializing to catch any BaseModel objects
                    try:
                        import json
                        json.dumps(serializable_data, default=str)
                        LOG.debug("Data passed JSON serialization check")
                    except (TypeError, ValueError) as json_error:
                        LOG.error(f"Data serialization check failed: {json_error}")
                        # Force convert any remaining non-serializable objects to strings
                        def force_serialize_dict(data_dict):
                            """Force serialize a dictionary, ensuring it remains a dictionary."""
                            if not isinstance(data_dict, dict):
                                LOG.error(f"Expected dict, got {type(data_dict)}")
                                return {"error": "Invalid data structure", "data": str(data_dict)}
                            
                            def serialize_value(obj):
                                try:
                                    json.dumps(obj)
                                    return obj
                                except (TypeError, ValueError):
                                    if isinstance(obj, dict):
                                        return {k: serialize_value(v) for k, v in obj.items()}
                                    elif isinstance(obj, list):
                                        return [serialize_value(item) for item in obj]
                                    else:
                                        return str(obj)
                            
                            return {k: serialize_value(v) for k, v in data_dict.items()}
                        
                        serializable_data = force_serialize_dict(serializable_data)
                        LOG.info("Applied emergency serialization conversion")
                    
                    LOG.error("🔥🔥🔥 DEBUG CHECKPOINT 6 - JSON safety check completed")
                    print("🔥🔥🔥 DEBUG CHECKPOINT 6 - JSON safety check completed")
                    
                    # Debug: Check for remaining BaseModel objects before write (ALWAYS RUN)
                    LOG.info("🔧 ALWAYS RUN - Starting comprehensive BaseModel detection")
                    
                    def find_basemodel_objects(obj, path="root", depth=0):
                        from pydantic import BaseModel
                        found_objects = []
                        
                        # Limit recursion depth to prevent infinite loops
                        if depth > 50:
                            return found_objects
                        
                        try:
                            if isinstance(obj, BaseModel):
                                # Safe way to represent BaseModel without triggering serialization
                                obj_type = str(type(obj).__name__)
                                obj_repr = f"<BaseModel {obj_type} at {hex(id(obj))}>"
                                found_objects.append((path, obj_type, obj_repr))
                            elif isinstance(obj, dict):
                                for k, v in obj.items():
                                    found_objects.extend(find_basemodel_objects(v, f"{path}.{k}", depth + 1))
                            elif isinstance(obj, list):
                                for i, item in enumerate(obj):
                                    found_objects.extend(find_basemodel_objects(item, f"{path}[{i}]", depth + 1))
                        except Exception as e:
                            # If any operation fails, record it but continue
                            found_objects.append((path, "ERROR", f"Detection failed: {str(e)}"))
                        
                        return found_objects
                    
                    # Test the function with a known BaseModel to verify it works
                    LOG.info("🧪 Testing BaseModel detection function...")
                    try:
                        from pydantic import BaseModel
                        class TestModel(BaseModel):
                            test_field: str = "test"
                        test_model = TestModel()
                        test_result = find_basemodel_objects({"test": test_model}, "test_data")
                        LOG.info(f"🧪 Test result: {len(test_result)} objects found (should be 1)")
                    except Exception as test_e:
                        LOG.error(f"🧪 Test failed: {test_e}")
                    
                    LOG.info(f"� WRITER DEBUG - About to scan serializable_data with {len(serializable_data) if isinstance(serializable_data, dict) else 'unknown'} keys")
                    
                    try:
                        basemodel_objects = find_basemodel_objects(serializable_data, path="serializable_data")
                        LOG.info(f"🔧 BaseModel scan returned {len(basemodel_objects) if basemodel_objects else 0} objects")
                        if basemodel_objects:
                            LOG.error(f"❌ FOUND BaseModel objects in data - this WILL cause JSON error:")
                            for obj_path, obj_type, obj_repr in basemodel_objects[:5]:  # Show first 5
                                LOG.error(f"  - Path: {obj_path}")
                                LOG.error(f"    Type: {obj_type}")
                                LOG.error(f"    Repr: {obj_repr[:100]}...")
                            if len(basemodel_objects) > 5:
                                LOG.error(f"  ... and {len(basemodel_objects) - 5} more BaseModel objects")
                        else:
                            LOG.info("✅ NO BaseModel objects found in data")
                    except Exception as e:
                        LOG.error(f"❌ BaseModel detection FAILED: {e}")
                        import traceback
                        LOG.error(f"❌ Traceback: {traceback.format_exc()}")
                    
                    LOG.info("🔧 BaseModel detection complete")
                    
                    # Also check the top-level keys of serializable_data
                    LOG.info(f"🔍 serializable_data keys: {list(serializable_data.keys()) if isinstance(serializable_data, dict) else 'not a dict'}")
                    for key in serializable_data:
                        if hasattr(serializable_data[key], '__len__') and not isinstance(serializable_data[key], str):
                            LOG.info(f"  - {key}: {len(serializable_data[key])} items")
                    
                    LOG.error("🚨🚨🚨 CRITICAL DEBUG CHECKPOINT - About to call writer.write()")
                    print("🚨🚨🚨 CRITICAL DEBUG CHECKPOINT - About to call writer.write()")
                    
                    # FINAL BaseModel check and data dump before writer.write()
                    LOG.error("🔥 FINAL CHECKPOINT - Just before writer.write() call")
                    print("🔥 FINAL CHECKPOINT - Just before writer.write() call")
                    try:
                        import pickle
                        import os
                        
                        debug_dir = "/home/app/samples/out"
                        os.makedirs(debug_dir, exist_ok=True)
                        
                        LOG.error(f"🔍 FINAL DEBUG - About to call writer.write() with data keys: {list(serializable_data.keys()) if isinstance(serializable_data, dict) else type(serializable_data)}")
                        
                        # First, safely pickle the data (this should always work)
                        try:
                            with open(f"{debug_dir}/writer_input_final.pkl", "wb") as f:
                                pickle.dump(serializable_data, f)
                            LOG.error(f"✅ Successfully pickled final writer input")
                        except Exception as pickle_e:
                            LOG.error(f"❌ Pickle dump failed: {pickle_e}")
                        
                        # Force BaseModel detection one more time
                        def find_basemodel_final_check(obj, path="root", max_depth=3):
                            if max_depth <= 0:
                                return []
                            
                            findings = []
                            try:
                                if hasattr(obj, '__class__'):
                                    obj_type_str = str(type(obj))
                                    obj_mro_str = str(type(obj).__mro__)
                                    if 'BaseModel' in obj_type_str or 'BaseModel' in obj_mro_str:
                                        findings.append(f"🚨 BASEMODEL FOUND: {path} -> {type(obj)} | MRO: {obj_mro_str}")
                                
                                if isinstance(obj, dict):
                                    for key, value in obj.items():
                                        findings.extend(find_basemodel_final_check(value, f"{path}.{key}", max_depth-1))
                                elif isinstance(obj, (list, tuple)) and len(obj) > 0:
                                    # Check first few items
                                    for i in range(min(3, len(obj))):
                                        findings.extend(find_basemodel_final_check(obj[i], f"{path}[{i}]", max_depth-1))
                            except Exception as e:
                                findings.append(f"❌ Error checking {path}: {e}")
                            
                            return findings
                        
                        basemodel_findings = find_basemodel_final_check(serializable_data)
                        if basemodel_findings:
                            LOG.error(f"🚨 CRITICAL: BaseModel objects found RIGHT BEFORE writer.write():")
                            for finding in basemodel_findings:
                                LOG.error(f"  {finding}")
                            
                            # Save to file
                            try:
                                with open(f"{debug_dir}/CRITICAL_basemodel_before_write.txt", "w") as f:
                                    f.write("BaseModel objects found RIGHT BEFORE writer.write() call:\n")
                                    for finding in basemodel_findings:
                                        f.write(f"{finding}\n")
                                LOG.error(f"✅ Saved BaseModel findings to file")
                            except Exception as file_e:
                                LOG.error(f"❌ Failed to save findings: {file_e}")
                        else:
                            LOG.error("✅ Final check: No BaseModel objects detected before writer.write()")
                        
                        # Try JSON dump LAST (this might fail due to BaseModel)
                        try:
                            import json
                            with open(f"{debug_dir}/writer_input_final.json", "w") as f:
                                json.dump(serializable_data, f, indent=2, default=str)
                            LOG.error(f"✅ Successfully dumped final writer input to JSON")
                        except Exception as json_e:
                            LOG.error(f"❌ JSON dump failed (expected if BaseModel present): {json_e}")
                        
                    except Exception as final_debug_e:
                        LOG.error(f"❌ Final debug check failed: {final_debug_e}")
                        # Make sure we still try to create a basic dump
                        try:
                            debug_dir = "/home/app/samples/out"
                            os.makedirs(debug_dir, exist_ok=True)
                            with open(f"{debug_dir}/debug_failure.txt", "w") as f:
                                f.write(f"Final debug failed: {final_debug_e}\n")
                                f.write(f"Data type: {type(serializable_data)}\n")
                                if isinstance(serializable_data, dict):
                                    f.write(f"Data keys: {list(serializable_data.keys())}\n")
                        except:
                            pass
                    
                    success = writer.write(serializable_data)
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
            
            # Check if this is the final iteration BEFORE sleeping
            if CMD.maxIterations > 0 and loop_iteration == (CMD.maxIterations - 1):
                LOG.info(f"Completed final iteration ({CMD.maxIterations}). Exiting gracefully.")
                break
            LOG.info(f"Current iteration before increment: {loop_iteration}, Max iterations: {CMD.maxIterations}")
            
            # Sleep for the remaining interval time only if we have more iterations to do
            if elapsed < CMD.intervalTime:
                LOG.info(f"Sleeping for {CMD.intervalTime - elapsed:.2f} seconds until next collection")
                time.sleep(CMD.intervalTime - elapsed)
                        
            # Increment loop counter for next iteration
            loop_iteration += 1
    
    except KeyboardInterrupt:
        LOG.info("Interrupted by user. Exiting gracefully.")
    finally:
        # Clean up session and logout
        if 'session' in locals() and session and 'active_endpoint' in locals() and active_endpoint:
            logout_session(session, active_endpoint)
            session.close()
        executor.shutdown()
