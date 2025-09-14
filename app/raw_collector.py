#!/usr/bin/env python3
"""
Raw API Data Collector for E-Series Performance Analyzer

This module handles collection of raw API responses for offline analysis.
Separate from the main application's enrichment pipeline.

Key features:
- Collects pure API responses without enrichment
- Handles ID-dependent endpoints (requires parent object IDs)
- Smart filename generation with categories
- Self-contained session management
- Single-threaded, simple loop design
"""

import json
import os
import time
import logging
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib3.exceptions import InsecureRequestWarning

# Import shared config
from app.config.endpoint_categories import ENDPOINT_CATEGORIES, EndpointCategory
from app.writer.json_writer import JsonWriter

# Disable SSL warnings for self-signed certificates
import urllib3
urllib3.disable_warnings(InsecureRequestWarning)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RawApiCollector:
    """
    Raw API response collector for E-Series systems
    """
    
    # API endpoint mappings (from collector.py)
    API_ENDPOINTS = {
        # System configuration
        'system_config': 'devmgr/v2/storage-systems/{system_id}',
        'controller_config': 'devmgr/v2/storage-systems/{system_id}/controllers',
        
        # Storage configuration
        'storage_pools': 'devmgr/v2/storage-systems/{system_id}/storage-pools',
        'volumes_config': 'devmgr/v2/storage-systems/{system_id}/volumes',
        'volume_mappings_config': 'devmgr/v2/storage-systems/{system_id}/volume-mappings',
        'drive_config': 'devmgr/v2/storage-systems/{system_id}/drives',
        'interfaces_config': 'devmgr/v2/storage-systems/{system_id}/interfaces',
        
        # Host connectivity
        'hosts': 'devmgr/v2/storage-systems/{system_id}/hosts',
        'host_groups': 'devmgr/v2/storage-systems/{system_id}/host-groups',
        
        # Performance endpoints
        'analysed_volume_statistics': 'devmgr/v2/storage-systems/{system_id}/analysed-volume-statistics',
        'analysed_drive_statistics': 'devmgr/v2/storage-systems/{system_id}/analysed-drive-statistics',
        'analysed_system_statistics': 'devmgr/v2/storage-systems/{system_id}/analysed-system-statistics',
        'analysed_interface_statistics': 'devmgr/v2/storage-systems/{system_id}/analysed-interface-statistics',
        'analyzed_controller_statistics': 'devmgr/v2/storage-systems/{system_id}/analyzed/controller-statistics?statisticsFetchTime=60',
        
        # Hardware inventory
        'hardware_inventory': 'devmgr/v2/storage-systems/{system_id}/hardware-inventory',
        'tray_config': 'devmgr/v2/storage-systems/{system_id}/tray',
        'ethernet_interface_config': 'devmgr/v2/storage-systems/{system_id}/configuration/ethernet-interfaces',
        
        # Advanced features
        'ssd_cache': 'devmgr/v2/storage-systems/{system_id}/flash-cache',
        'snapshot_schedules': 'devmgr/v2/storage-systems/{system_id}/snapshot-schedules',
        'snapshot_groups': 'devmgr/v2/storage-systems/{system_id}/snapshot-groups',
        'snapshot_volumes': 'devmgr/v2/storage-systems/{system_id}/snapshot-volumes',
        'snapshot_images': 'devmgr/v2/storage-systems/{system_id}/snapshot-images',
        'mirrors': 'devmgr/v2/storage-systems/{system_id}/mirror-pairs',
        'async_mirrors': 'devmgr/v2/storage-systems/{system_id}/async-mirrors',
        
        # Events and status endpoints
        'system_events': 'devmgr/v2/storage-systems/{system_id}/events',
        'system_failures': 'devmgr/v2/storage-systems/{system_id}/failures',
        'lockdown_status': 'devmgr/v2/storage-systems/{system_id}/lockdownstatus',
        'volume_parity_check_status': 'devmgr/v2/storage-systems/{system_id}/volumes/check-volume-parity/jobs',
        'volume_parity_job_check_errors': 'devmgr/v2/storage-systems/{system_id}/volumes/check-volume-parity/jobs/errors',
        'data_parity_scan_job_status': 'devmgr/v2/storage-systems/{system_id}/volumes/data-parity-repair-volume/jobs',
        'volume_copy_jobs': 'devmgr/v2/storage-systems/{system_id}/volume-copy-jobs',
        'volume_copy_job_progress': 'devmgr/v2/storage-systems/{system_id}/volume-copy-jobs-control',
        'drives_erase_progress': 'devmgr/v2/storage-systems/{system_id}/drives/erase/progress',
        'storage_pools_action_progress': 'devmgr/v2/storage-systems/{system_id}/storage-pools/{id}/action-progress',
        
        # ID-dependent endpoints (require parent object IDs)
        'snapshot_groups_repository_utilization': 'devmgr/v2/storage-systems/{system_id}/snapshot-groups/{id}/repository-utilization',
        'volume_expansion_progress': 'devmgr/v2/storage-systems/{system_id}/volumes/{id}/expand',
    }
    
    # ID dependency mapping (from collector.py)
    ID_DEPENDENCIES = {
        'snapshot_groups_repository_utilization': {
            'id_source': 'snapshot_groups',
            'id_field': 'pitGroupRef',
            'description': 'Repository utilization for each snapshot group'
        },
        'storage_pools_action_progress': {
            'id_source': 'storage_pools', 
            'id_field': 'volumeGroupRef',
            'description': 'Action progress for each storage pool'
        },
        'volume_expansion_progress': {
            'id_source': 'volumes_config',
            'id_field': 'volumeRef', 
            'description': 'Expansion progress for each volume'
        }
    }
    
    def __init__(self, base_url: str, username: str, password: str, output_dir: str, system_id: Optional[str] = None):
        """
        Initialize the raw API collector
        
        Args:
            base_url: E-Series API base URL (e.g., 'https://10.113.1.158:8443')
            username: API username
            password: API password
            output_dir: Directory for JSON output files
            system_id: Optional system ID (will be discovered if not provided)
        """
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.output_dir = output_dir
        self.system_id = system_id
        self.session: Optional[requests.Session] = None
        self.json_writer: Optional[JsonWriter] = None
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Cache for parent objects (for ID-dependent endpoints)
        self.parent_cache = {}
        
    def connect(self) -> bool:
        """
        Establish API session and discover system ID if needed
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Create session
            self.session = requests.Session()
            self.session.verify = False
            self.session.auth = (self.username, self.password)
            
            # Test connection and get system info
            systems_url = f"{self.base_url}/devmgr/v2/storage-systems"
            response = self.session.get(systems_url)
            response.raise_for_status()
            
            systems = response.json()
            if not systems:
                logger.error("No storage systems found")
                return False
                
            # Use provided system_id or first system
            if self.system_id:
                system_info = next((s for s in systems if s.get('wwn') == self.system_id or s.get('id') == self.system_id), None)
                if not system_info:
                    logger.error(f"System {self.system_id} not found")
                    return False
            else:
                system_info = systems[0]
                self.system_id = system_info.get('wwn', system_info.get('id'))
            
            logger.info(f"Connected to system: {system_info.get('name', 'Unknown')} (WWN: {self.system_id})")
            
            # Initialize JSON writer with actual system ID
            self.json_writer = JsonWriter(self.output_dir, self.system_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def _call_api(self, endpoint_key: str, object_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Make API call to specified endpoint
        
        Args:
            endpoint_key: Key from API_ENDPOINTS mapping
            object_id: Optional object ID for ID-dependent endpoints
            
        Returns:
            JSON response or None if failed
        """
        if endpoint_key not in self.API_ENDPOINTS:
            logger.warning(f"Unknown endpoint: {endpoint_key}")
            return None
            
        try:
            # Build URL
            endpoint_path = self.API_ENDPOINTS[endpoint_key]
            if object_id:
                endpoint_path = endpoint_path.format(system_id=self.system_id, id=object_id)
            else:
                endpoint_path = endpoint_path.format(system_id=self.system_id)
                
            url = f"{self.base_url}/{endpoint_path}"
            
            # Make request
            if not self.session:
                raise RuntimeError("Not connected - call connect() first")
            response = self.session.get(url)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"API call failed for {endpoint_key}: {e}")
            return None
            
    def collect_endpoint(self, endpoint_key: str) -> bool:
        """
        Collect data from a single endpoint (handling ID dependencies)
        
        Args:
            endpoint_key: Endpoint to collect from
            
        Returns:
            True if collection successful, False otherwise
        """
        try:
            # Check if this endpoint requires ID dependency
            if endpoint_key in self.ID_DEPENDENCIES:
                return self._collect_id_dependent_endpoint(endpoint_key)
            else:
                return self._collect_simple_endpoint(endpoint_key)
                
        except Exception as e:
            logger.error(f"Failed to collect {endpoint_key}: {e}")
            return False
    
    def _collect_simple_endpoint(self, endpoint_key: str) -> bool:
        """Collect from endpoint that doesn't require IDs"""
        data = self._call_api(endpoint_key)
        if data is not None:
            # Write to JSON using the writer
            if not self.json_writer:
                raise RuntimeError("JSON writer not initialized - call connect() first")
            writer_data = {endpoint_key: data}
            success = self.json_writer.write(writer_data)
            
            if success:
                item_count = len(data) if isinstance(data, list) else 1
                logger.info(f"✅ {endpoint_key}: {item_count} items")
                return True
            else:
                logger.error(f"❌ Failed to write {endpoint_key}")
                return False
        else:
            logger.warning(f"⚠️  {endpoint_key}: No data")
            return False
    
    def _collect_id_dependent_endpoint(self, endpoint_key: str) -> bool:
        """Collect from endpoint that requires parent object IDs"""
        dependency = self.ID_DEPENDENCIES[endpoint_key]
        id_source = dependency['id_source']
        id_field = dependency['id_field']
        
        # Get parent objects (use cache if available)
        if id_source not in self.parent_cache:
            parent_data = self._call_api(id_source)
            if not parent_data:
                logger.warning(f"❌ {endpoint_key}: Could not get parent data from {id_source}")
                return False
            self.parent_cache[id_source] = parent_data
        
        parent_objects = self.parent_cache[id_source]
        if not isinstance(parent_objects, list):
            parent_objects = [parent_objects]
        
        # Collect data for each parent object
        all_data = []
        success_count = 0
        
        for parent_obj in parent_objects:
            if not isinstance(parent_obj, dict) or id_field not in parent_obj:
                continue
                
            object_id = parent_obj[id_field]
            data = self._call_api(endpoint_key, object_id)
            
            if data is not None:
                if isinstance(data, list):
                    all_data.extend(data)
                else:
                    all_data.append(data)
                success_count += 1
        
        # Write aggregated data
        if all_data:
            if not self.json_writer:
                raise RuntimeError("JSON writer not initialized - call connect() first")
            writer_data = {endpoint_key: all_data}
            success = self.json_writer.write(writer_data)
            
            if success:
                logger.info(f"✅ {endpoint_key}: {len(all_data)} items from {success_count}/{len(parent_objects)} objects")
                return True
            else:
                logger.error(f"❌ Failed to write {endpoint_key}")
                return False
        else:
            logger.warning(f"⚠️  {endpoint_key}: No data from any object")
            return False
    
    def collect_by_category(self, category: EndpointCategory) -> Dict[str, bool]:
        """
        Collect all endpoints for a specific category
        
        Args:
            category: Category to collect
            
        Returns:
            Dictionary mapping endpoint names to success status
        """
        endpoints = ENDPOINT_CATEGORIES.get(category, set())
        results = {}
        
        logger.info(f"Collecting {category.value} endpoints: {len(endpoints)} total")
        
        for endpoint in endpoints:
            if endpoint in self.API_ENDPOINTS:
                results[endpoint] = self.collect_endpoint(endpoint)
            else:
                logger.warning(f"⚠️  Skipping unknown endpoint: {endpoint}")
                results[endpoint] = False
        
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"✅ {category.value}: {success_count}/{len(endpoints)} endpoints successful")
        
        return results
    
    def collect_all(self) -> Dict[str, Dict[str, bool]]:
        """
        Collect all categorized endpoints
        
        Returns:
            Nested dictionary: {category: {endpoint: success}}
        """
        if not self.session:
            logger.error("Not connected - call connect() first")
            return {}
        
        all_results = {}
        
        for category in EndpointCategory:
            logger.info(f"\n=== {category.value.upper()} COLLECTION ===")
            all_results[category.value] = self.collect_by_category(category)
            
            # Small delay between categories
            time.sleep(1)
        
        return all_results
    
    def disconnect(self):
        """Clean up session"""
        if self.session:
            self.session.close()
            self.session = None