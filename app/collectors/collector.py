"""
Collector module for reading raw JSON API responses and using schema models
"""
import json
import os
import logging
from typing import Dict, Any, List, Optional, Type, TypeVar
from pathlib import Path
from datetime import datetime
import re

from app.schema.base_model import BaseModel
from app.utils.model_mixins import CaseConversionMixin
from app.read.batched_json_reader import BatchedJsonReader

# Type variable for generic model handling
T = TypeVar('T', bound=BaseModel)

logger = logging.getLogger(__name__)

class APICollector:
    """Base collector class for handling API interactions and JSON files"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the collector with configuration
        
        Args:
            config: Dictionary containing configuration parameters
        """
        self.config = config
        self.json_path = config.get('json_path')
        
    def read_json_file(self, file_path: str) -> Dict[str, Any]:
        """
        Read a JSON file and return its contents as a dictionary
        
        Args:
            file_path: Path to the JSON file
            
        Returns:
            Dictionary containing the JSON data
            
        Raises:
            FileNotFoundError: If the file does not exist
            json.JSONDecodeError: If the file is not valid JSON
        """
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"JSON file not found: {file_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in file {file_path}: {str(e)}")
            raise
    
    def write_json_file(self, data: Dict[str, Any], file_path: str) -> None:
        """
        Write data to a JSON file
        
        Args:
            data: Dictionary to write to the file
            file_path: Path to the JSON file
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
            
    def get_timestamp_from_filename(self, filename: str) -> Optional[datetime]:
        """
        Extract timestamp from filename with pattern *_YYYYMMDD_HHMMSS.json
        
        Args:
            filename: The filename to parse
            
        Returns:
            datetime object if pattern matched, None otherwise
        """
        # Match pattern like endpoint_20250910_123045.json
        match = re.search(r'_(\d{8})_(\d{6})\.json$', filename)
        if match:
            date_str, time_str = match.groups()
            try:
                return datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
            except ValueError:
                return None
        return None
    
    def get_files_sorted_by_timestamp(self, directory: str, pattern: str) -> List[str]:
        """
        Get list of files matching pattern, sorted by timestamp in filename
        
        Args:
            directory: Directory to search
            pattern: Glob pattern for files
            
        Returns:
            List of file paths sorted by timestamp
        """
        files = list(Path(directory).glob(pattern))
        # Sort files by timestamp in filename
        return sorted(
            [str(f) for f in files],
            key=lambda x: self.get_timestamp_from_filename(x) or datetime.fromtimestamp(0)
        )
    
    def get_latest_file(self, directory: str, pattern: str) -> Optional[str]:
        """
        Get the latest file matching pattern based on timestamp in filename
        
        Args:
            directory: Directory to search
            pattern: Glob pattern for files
            
        Returns:
            Path to the latest file or None if no files found
        """
        files = self.get_files_sorted_by_timestamp(directory, pattern)
        return files[-1] if files else None
    
    def parse_model_from_json(self, json_data: Dict[str, Any], model_class: Type[T]) -> T:
        """
        Parse JSON data into a model instance
        
        Args:
            json_data: Dictionary containing JSON data
            model_class: The model class to instantiate
            
        Returns:
            Instance of the model class
        """
        return model_class.from_api_response(json_data)
    
    def collect_from_json(self, file_path: str, model_class: Type[T]) -> T:
        """
        Collect data from a JSON file and parse it into a model
        
        Args:
            file_path: Path to the JSON file
            model_class: The model class to instantiate
            
        Returns:
            Instance of the model class
        """
        data = self.read_json_file(file_path)
        return self.parse_model_from_json(data, model_class)
    
    def collect_list_from_json(self, file_path: str, model_class: Type[T]) -> List[T]:
        """
        Collect a list of objects from a JSON file and parse each into a model
        
        Args:
            file_path: Path to the JSON file
            model_class: The model class to instantiate
            
        Returns:
            List of model class instances
        """
        data = self.read_json_file(file_path)
        if isinstance(data, list):
            return [self.parse_model_from_json(item, model_class) for item in data]
        else:
            logger.warning(f"Expected list in JSON file {file_path}, got {type(data)}")
            return []
    
    def collect_from_json_directory(self, directory: str, pattern: str, model_class: Type[T], 
                                   sort_by: str = 'timestamp') -> List[T]:
        """
        Collect data from multiple JSON files in a directory
        
        Args:
            directory: Directory to search for JSON files
            pattern: Glob pattern for files (e.g., 'volumes_*.json')
            model_class: The model class to instantiate
            sort_by: How to sort files ('timestamp', 'mtime', 'name')
            
        Returns:
            List of model instances from all matching files
        """
        if sort_by == 'timestamp':
            files = self.get_files_sorted_by_timestamp(directory, pattern)
        else:
            files = list(Path(directory).glob(pattern))
            if sort_by == 'mtime':
                files.sort(key=lambda x: x.stat().st_mtime)
            elif sort_by == 'name':
                files.sort()
            files = [str(f) for f in files]
        
        results = []
        for file_path in files:
            logger.debug(f"Processing file: {file_path}")
            try:
                data = self.read_json_file(file_path)
                if isinstance(data, list):
                    # If the file contains a list, extend results with all items
                    results.extend([self.parse_model_from_json(item, model_class) for item in data])
                else:
                    # If the file contains a single object, add it to results
                    results.append(self.parse_model_from_json(data, model_class))
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {str(e)}")
                continue
                
        logger.debug(f"Collected {len(results)} items from {len(files)} files")
        return results
    
    def collect_latest_from_json(self, directory: str, pattern: str, model_class: Type[T]) -> Optional[T]:
        """
        Collect data from the latest JSON file matching pattern
        
        Args:
            directory: Directory to search for JSON files
            pattern: Glob pattern for files
            model_class: The model class to instantiate
            
        Returns:
            Model instance from the latest file or None if no files found
        """
        latest_file = self.get_latest_file(directory, pattern)
        if latest_file:
            logger.info(f"Processing latest file: {latest_file}")
            return self.collect_from_json(latest_file, model_class)
        else:
            logger.warning(f"No files found matching pattern {pattern} in {directory}")
            return None
    
    def validate_json_structure(self, file_path: str, expected_keys: List[str]) -> bool:
        """
        Validate that a JSON file contains expected keys
        
        Args:
            file_path: Path to the JSON file
            expected_keys: List of keys that should be present
            
        Returns:
            True if all expected keys are present, False otherwise
        """
        try:
            data = self.read_json_file(file_path)
            if isinstance(data, dict):
                missing_keys = [key for key in expected_keys if key not in data]
                if missing_keys:
                    logger.warning(f"Missing keys in {file_path}: {missing_keys}")
                    return False
                return True
            elif isinstance(data, list) and data:
                # Check first item in list
                first_item = data[0]
                if isinstance(first_item, dict):
                    missing_keys = [key for key in expected_keys if key not in first_item]
                    if missing_keys:
                        logger.warning(f"Missing keys in first item of {file_path}: {missing_keys}")
                        return False
                    return True
            return False
        except Exception as e:
            logger.error(f"Error validating JSON structure in {file_path}: {str(e)}")
            return False
    
    def get_available_endpoints(self, directory: str) -> Dict[str, List[str]]:
        """
        Scan directory for available API endpoint JSON files
        
        Args:
            directory: Directory to scan
            
        Returns:
            Dictionary mapping endpoint names to lists of available files
        """
        endpoints = {}
        json_files = Path(directory).glob('*.json')
        
        for file_path in json_files:
            # Extract endpoint name from filename (before first underscore or timestamp)
            filename = file_path.name
            # Try to extract endpoint name (everything before _YYYYMMDD pattern)
            match = re.match(r'^([^_]+)(?:_\d{8}_\d{6})?\.json$', filename)
            if match:
                endpoint = match.group(1)
            else:
                # Fallback: use everything before first underscore
                endpoint = filename.split('_')[0].replace('.json', '')
            
            if endpoint not in endpoints:
                endpoints[endpoint] = []
            endpoints[endpoint].append(str(file_path))
        
        # Sort files for each endpoint
        for endpoint in endpoints:
            endpoints[endpoint] = sorted(endpoints[endpoint])
            
        return endpoints


class ESeriesCollector(APICollector):
    """
    E-Series specific collector that handles both live API calls and JSON file reading
    """
    
    # API endpoint mappings from tools/collect_items.py
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
        
        # Volume consistency groups (from manual collector endpoints)
        'volume_consistency_group_config': 'devmgr/v2/storage-systems/{system_id}/consistency_groups',
        'volume_consistency_group_members': 'devmgr/v2/storage-systems/{system_id}/consistency-groups/member-volumes',
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
    
    # ID dependency mapping - defines which endpoints need IDs from other endpoints
    ID_DEPENDENCIES = {
        'snapshot_groups_repository_utilization': {
            'id_source': 'snapshot_groups',
            'id_field': 'pitGroupRef',  # Field name containing the ID
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
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize E-Series collector
        
        Args:
            config: Configuration dictionary containing connection details and options
        """
        super().__init__(config)
        self.from_json = config.get('from_json', False)
        self.json_directory = config.get('json_directory', './json_data')
        
        # API connection details for live mode
        self.base_url = config.get('base_url')  # e.g., 'https://10.113.1.158:8443'
        self.system_id = config.get('system_id', '1')  # Default system ID
        self.session = config.get('session')  # HTTP session with auth
        self.headers = config.get('headers', {'Accept': 'application/json'})
        
        # Initialize batched reader for JSON replay mode
        self.batched_reader = None
        if self.from_json:
            self.batched_reader = BatchedJsonReader(self.json_directory)
            logger.info(f"Initialized BatchedJsonReader with {self.batched_reader.get_total_batches()} timestamp batches")
    
    def has_more_data(self) -> bool:
        """
        Check if there is more data available for collection.
        
        Returns:
            True if more data is available (more batches in JSON mode, always True for live API)
        """
        if self.from_json and self.batched_reader:
            return self.batched_reader.has_more_batches()
        return True  # Live API mode always has data available
    
    def get_current_batch_files(self) -> List[str]:
        """
        Get the current batch of files to process.
        
        Returns:
            List of file paths for the current batch, or empty list if no more batches
        """
        if self.from_json and self.batched_reader:
            return self.batched_reader.get_next_batch()
        return []
    
    def _build_api_url(self, endpoint_key: str) -> str:
        """
        Build the full API URL for a given endpoint
        
        Args:
            endpoint_key: Key from API_ENDPOINTS mapping
            
        Returns:
            Complete URL for the API endpoint
        """
        if endpoint_key not in self.API_ENDPOINTS:
            raise ValueError(f"Unknown endpoint: {endpoint_key}")
            
        endpoint_path = self.API_ENDPOINTS[endpoint_key]
        # Replace system_id placeholder
        endpoint_path = endpoint_path.format(system_id=self.system_id)
        
        # Combine with base URL
        return f"{self.base_url}/{endpoint_path}"
    
    def _call_api(self, endpoint_key: str) -> Dict[str, Any]:
        """
        Make an API call to the specified endpoint
        
        Args:
            endpoint_key: Key from API_ENDPOINTS mapping
            
        Returns:
            JSON response as dictionary
            
        Raises:
            Exception: If API call fails or session not configured
        """
        if not self.session:
            raise Exception("No session configured for API calls")
            
        if not self.base_url:
            raise Exception("No base_url configured for API calls")
            
        url = self._build_api_url(endpoint_key)
        logger.info(f"Making API call to: {url}")
        
        try:
            response = self.session.get(url, headers=self.headers)
            response.raise_for_status()  # Raise exception for HTTP errors
            return response.json()
        except Exception as e:
            logger.error(f"API call failed for {url}: {e}")
            raise
    
    def _collect_from_api(self, endpoint_key: str, model_class: Type[T]) -> List[T]:
        """
        Collect data from API endpoint and parse into model instances
        
        Args:
            endpoint_key: Key from API_ENDPOINTS mapping
            model_class: Model class to parse the response into
            
        Returns:
            List of model instances
        """
        try:
            data = self._call_api(endpoint_key)
            
            results = []
            if isinstance(data, list):
                results.extend([self.parse_model_from_json(item, model_class) for item in data])
            elif isinstance(data, dict):
                results.append(self.parse_model_from_json(data, model_class))
            else:
                logger.warning(f"Unexpected response type for {endpoint_key}: {type(data)}")
                
            logger.info(f"Collected {len(results)} items from API endpoint {endpoint_key}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to collect from API endpoint {endpoint_key}: {e}")
            return []
    
    def _collect_with_id_dependency(self, endpoint_key: str, model_class: Type[T]) -> List[T]:
        """
        Collect data from an endpoint that requires IDs from another endpoint
        
        Args:
            endpoint_key: Key from API_ENDPOINTS mapping that requires IDs
            model_class: Model class to parse the response into
            
        Returns:
            List of model instances from all ID-based calls
        """
        if endpoint_key not in self.ID_DEPENDENCIES:
            logger.error(f"No ID dependency defined for {endpoint_key}")
            return []
            
        dependency = self.ID_DEPENDENCIES[endpoint_key]
        id_source = dependency['id_source']
        id_field = dependency['id_field']
        
        logger.info(f"Collecting IDs from {id_source} for {endpoint_key}")
        
        # First, get the parent objects to extract IDs from
        try:
            parent_objects = self._collect_from_api(id_source, BaseModel)
            if not parent_objects:
                logger.warning(f"No parent objects found from {id_source} for {endpoint_key}")
                return []
                
            logger.info(f"Found {len(parent_objects)} parent objects from {id_source}")
            
        except Exception as e:
            logger.error(f"Failed to get parent objects from {id_source}: {e}")
            return []
        
        # Extract IDs and collect data for each
        all_results = []
        successful_calls = 0
        
        for parent_obj in parent_objects:
            try:
                # Extract the ID from the parent object
                if hasattr(parent_obj, id_field):
                    obj_id = getattr(parent_obj, id_field)
                elif hasattr(parent_obj, '_raw_data') and id_field in parent_obj._raw_data:
                    obj_id = parent_obj._raw_data[id_field]
                else:
                    logger.warning(f"Could not find {id_field} in parent object from {id_source}")
                    continue
                
                if not obj_id:
                    continue
                    
                # Make API call with the specific ID
                url = self._build_api_url_with_id(endpoint_key, obj_id)
                logger.debug(f"Collecting from ID-specific URL: {url}")
                
                if not self.session:
                    raise Exception("No session configured for API calls")
                
                response = self.session.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                # Defensive handling: skip empty responses
                if isinstance(data, list) and len(data) == 0:
                    logger.debug(f"Skipping empty response for {endpoint_key} ID {obj_id}")
                    continue
                elif isinstance(data, list) and len(data) > 0:
                    all_results.extend([self.parse_model_from_json(item, model_class) for item in data])
                elif isinstance(data, dict) and data:  # Non-empty dict
                    all_results.append(self.parse_model_from_json(data, model_class))
                    
                successful_calls += 1
                
            except Exception as e:
                logger.warning(f"Failed to collect {endpoint_key} for ID {obj_id}: {e}")
                continue
        
        logger.info(f"Collected {len(all_results)} items from {successful_calls}/{len(parent_objects)} ID-based calls for {endpoint_key}")
        return all_results
    
    def _build_api_url_with_id(self, endpoint_key: str, obj_id: str) -> str:
        """
        Build API URL with both system_id and object ID placeholders filled
        
        Args:
            endpoint_key: Key from API_ENDPOINTS mapping
            obj_id: The specific object ID to use
            
        Returns:
            Complete URL with all placeholders filled
        """
        if endpoint_key not in self.API_ENDPOINTS:
            raise ValueError(f"Unknown endpoint: {endpoint_key}")
            
        endpoint_path = self.API_ENDPOINTS[endpoint_key]
        # Replace both system_id and id placeholders
        endpoint_path = endpoint_path.format(system_id=self.system_id, id=obj_id)
        
        return f"{self.base_url}/{endpoint_path}"
    
    def collect_hierarchical_data(self, endpoint_key: str, model_class: Type[T]) -> List[T]:
        """
        Public method to collect data that may require ID dependencies
        
        Args:
            endpoint_key: Key from API_ENDPOINTS mapping
            model_class: Model class to parse the response into
            
        Returns:
            List of model instances
        """
        if self.from_json:
            # In JSON mode, use existing collection logic
            pattern = f"*{endpoint_key.replace('_', '*')}*"
            return self.collect_from_json_directory(
                directory=self.json_directory,
                pattern=pattern,
                model_class=model_class,
                sort_by='timestamp'
            )
        else:
            # In API mode, check if this endpoint requires ID dependency
            if endpoint_key in self.ID_DEPENDENCIES:
                return self._collect_with_id_dependency(endpoint_key, model_class)
            else:
                return self._collect_from_api(endpoint_key, model_class)
    

    
    def _collect_from_files(self, files: List[str], pattern_prefix: str, model_class: Type[T]) -> List[T]:
        """
        Collect data from a specific list of files matching a pattern prefix.
        
        Args:
            files: List of file paths to process
            pattern_prefix: Prefix to match in filenames (e.g., 'volumes_config_')
            model_class: The model class to use for parsing
            
        Returns:
            List of model instances
        """
        results = []
        
        # Handle both old and new filename patterns
        # Old: volume_expansion_progress_202509132332.json
        # New: events_volume_expansion_progress_1_objectid_202509132332.json
        matching_files = []
        for f in files:
            basename = os.path.basename(f)
            # Check old pattern first (backward compatibility)
            if pattern_prefix in basename:
                matching_files.append(f)
            # Check new pattern: category_endpoint_sysid_[objectid_]timestamp.json
            elif f"_{pattern_prefix.rstrip('_')}_" in basename:
                matching_files.append(f)
        
        if not matching_files:
            return results
            
        logger.info(f"Processing {len(matching_files)} files matching '{pattern_prefix}' from current batch")
        
        for file_path in matching_files:
            try:
                data = self.read_json_file(file_path)
                if isinstance(data, list):
                    results.extend([self.parse_model_from_json(item, model_class) for item in data])
                elif isinstance(data, dict):
                    results.append(self.parse_model_from_json(data, model_class))
                logger.debug(f"Processed {file_path}: {len(data) if isinstance(data, list) else 1} items")
            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")
                continue
                
        logger.info(f"Collected {len(results)} items from {len(matching_files)} files")
        return results
            
    def collect_volumes(self, model_class: Type[T]) -> List[T]:
        """
        Collect volume data either from API or JSON files (legacy method for compatibility)
        
        Args:
            model_class: The volume model class to use
            
        Returns:
            List of volume model instances
        """
        if self.from_json:
            # Use batch-aware collection if BatchedJsonReader is available
            if self.batched_reader:
                return self.collect_volumes_from_current_batch(model_class)
            else:
                return self.collect_from_json_directory(
                    directory=self.json_directory,
                    pattern='*volumes_config*',
                    model_class=model_class,
                    sort_by='timestamp'
                )
        else:
            return self._collect_from_api('volumes_config', model_class)
    
    def collect_system_config(self, model_class: Type[T]) -> Optional[T]:
        """
        Collect system configuration either from API or JSON files
        
        Args:
            model_class: The system config model class to use
            
        Returns:
            System config model instance or None
        """
        if self.from_json:
            # Use batch-aware collection if BatchedJsonReader is available
            if self.batched_reader:
                return self.collect_system_config_from_current_batch(model_class)
            else:
                return self.collect_latest_from_json(
                    directory=self.json_directory,
                    pattern='*system_config*',
                    model_class=model_class
                )
        else:
            results = self._collect_from_api('system_config', model_class)
            return results[0] if results else None
    
    def collect_performance_data(self, model_class: Type[T], endpoint: str) -> List[T]:
        """
        Collect performance data for a specific endpoint
        
        Args:
            model_class: The performance model class to use
            endpoint: The performance endpoint name (e.g., 'analysed-volume-statistics')
            
        Returns:
            List of performance model instances
        """
        if self.from_json:
            pattern = f'*{endpoint.replace("-", "_")}*'
            return self.collect_from_json_directory(
                directory=self.json_directory,
                pattern=pattern,
                model_class=model_class,
                sort_by='timestamp'
            )
        else:
            # Map endpoint names to API endpoint keys
            endpoint_mapping = {
                'analysed-volume-statistics': 'analysed_volume_statistics',
                'analysed-drive-statistics': 'analysed_drive_statistics', 
                'analysed-system-statistics': 'analysed_system_statistics',
                'analysed-interface-statistics': 'analysed_interface_statistics',
                'analysed-controller-statistics': 'analyzed_controller_statistics',
            }
            
            api_endpoint_key = endpoint_mapping.get(endpoint)
            if not api_endpoint_key:
                logger.error(f"Unknown performance endpoint: {endpoint}")
                return []
                
            # Special handling for analyzed controller statistics
            if endpoint == 'analysed-controller-statistics':
                return self._collect_analyzed_controller_statistics(model_class)
            
            return self._collect_from_api(api_endpoint_key, model_class)
    
    def _collect_analyzed_controller_statistics(self, model_class: Type[T]) -> List[T]:
        """
        Special handling for analyzed controller statistics with defensive parsing.
        
        This endpoint is unique because:
        1. It has a wrapper structure with 'statistics' array
        2. The array can contain 0, 1, 2+ items depending on timing
        3. We need to handle empty responses gracefully
        4. For multiple responses, sort by time and take the 2 most recent
        """
        try:
            # Get the raw response 
            response = self._call_api('analyzed_controller_statistics')
            if not response:
                logger.debug("No response from analyzed controller statistics endpoint")
                return []
            
            # Check if we got the expected structure
            if 'statistics' not in response:
                logger.warning("analyzed controller statistics response missing 'statistics' field")
                return []
            
            statistics_array = response['statistics']
            
            # Handle empty statistics array
            if not statistics_array or len(statistics_array) == 0:
                logger.debug("analyzed controller statistics returned empty statistics array")
                return []
            
            # Handle multiple statistics - sort by observedTimeInMS and take 2 most recent
            if len(statistics_array) > 2:
                logger.debug(f"Got {len(statistics_array)} controller statistics, sorting and taking 2 most recent")
                # Sort by observedTimeInMS (newest first)
                sorted_stats = sorted(statistics_array, 
                                    key=lambda x: int(x.get('observedTimeInMS', 0)), 
                                    reverse=True)
                statistics_array = sorted_stats[:2]
            
            # Create the model instance with the processed statistics array
            processed_response = {'statistics': statistics_array}
            model_instance = model_class.from_api_response(processed_response)
            
            logger.debug(f"Successfully processed {len(statistics_array)} controller statistics records")
            return [model_instance]
            
        except Exception as e:
            logger.error(f"Failed to collect analyzed controller statistics: {e}")
            return []
    
    def list_available_data(self) -> Dict[str, Any]:
        """
        List available data sources (either from JSON directory or API endpoints)
        
        Returns:
            Dictionary containing information about available data
        """
        if self.from_json:
            endpoints = self.get_available_endpoints(self.json_directory)
            return {
                'source': 'json_files',
                'directory': self.json_directory,
                'endpoints': endpoints,
                'total_files': sum(len(files) for files in endpoints.values())
            }
        else:
            return {
                'source': 'api',
                'status': 'not_implemented'
            }
    
    def collect_hosts(self, model_class: Type[T]) -> List[T]:
        """Collect host configuration data"""
        
        if self.from_json:
            # Use batch-aware collection if BatchedJsonReader is available
            if self.batched_reader:
                return self.collect_hosts_from_current_batch(model_class)
            else:
                pattern = "*hosts*"
                return self.collect_from_json_directory(self.json_directory, pattern, model_class, sort_by='filename')
        else:
            return self._collect_from_api('hosts', model_class)
    
    def collect_host_groups(self, model_class: Type[T]) -> List[T]:
        """Collect host group configuration data"""
        
        if self.from_json:
            # Use batch-aware collection if BatchedJsonReader is available
            if self.batched_reader:
                return self.collect_host_groups_from_current_batch(model_class)
            else:
                pattern = "*host_group*"
                return self.collect_from_json_directory(self.json_directory, pattern, model_class, sort_by='filename')
        else:
            return self._collect_from_api('host_groups', model_class)
    
    def collect_storage_pools(self, model_class: Type[T]) -> List[T]:
        """Collect storage pool configuration data"""
        
        if self.from_json:
            # Use batch-aware collection if BatchedJsonReader is available
            if self.batched_reader:
                return self.collect_storage_pools_from_current_batch(model_class)
            else:
                pattern = "*storage_pool*"
                return self.collect_from_json_directory(self.json_directory, pattern, model_class, sort_by='filename')
        else:
            return self._collect_from_api('storage_pools', model_class)
    
    def collect_volume_mappings(self, model_class: Type[T]) -> List[T]:
        """Collect volume mapping configuration data"""
        
        if self.from_json:
            # Use batch-aware collection if BatchedJsonReader is available
            if self.batched_reader:
                return self.collect_volume_mappings_from_current_batch(model_class)
            else:
                pattern = "*volume_mapping*"
                return self.collect_from_json_directory(self.json_directory, pattern, model_class, sort_by='filename')
        else:
            return self._collect_from_api('volume_mappings_config', model_class)
    
    def collect_drives(self, model_class: Type[T]) -> List[T]:
        """Collect drive configuration data"""
        
        if self.from_json:
            # Use batch-aware collection if BatchedJsonReader is available
            if self.batched_reader:
                return self.collect_drives_from_current_batch(model_class)
            else:
                pattern = "*drive_config*"
                return self.collect_from_json_directory(self.json_directory, pattern, model_class, sort_by='filename')
        else:
            return self._collect_from_api('drive_config', model_class)
    
    def collect_controllers(self, model_class: Type[T]) -> List[T]:
        """Collect controller configuration data"""
        
        if self.from_json:
            # Use batch-aware collection if BatchedJsonReader is available
            if self.batched_reader:
                return self.collect_controllers_from_current_batch(model_class)
            else:
                pattern = "*controller_config*"
                return self.collect_from_json_directory(self.json_directory, pattern, model_class, sort_by='filename')
        else:
            return self._collect_from_api('controller_config', model_class)
    
    def collect_system_configs(self, model_class: Type[T]) -> List[T]:
        """Collect system configuration data"""
        
        if self.from_json:
            pattern = "*system_config*"
            return self.collect_from_json_directory(self.json_directory, pattern, model_class, sort_by='filename')
        else:
            return self._collect_from_api('system_config', model_class)
    
    # Batch-aware collection methods for JSON replay
    def collect_volumes_from_current_batch(self, model_class: Type[T]) -> List[T]:
        """Collect volumes from current batch."""
        return self._collect_from_batch('volumes', model_class)
    
    def collect_system_config_from_current_batch(self, model_class: Type[T]) -> Optional[T]:
        """Collect system config from current batch."""
        results = self._collect_from_batch('system', model_class)
        return results[0] if results else None
    
    def collect_performance_data_from_current_batch(self, model_class: Type[T], endpoint: str) -> List[T]:
        """Collect performance data from current batch."""
        return self._collect_from_batch(endpoint, model_class)
    
    def collect_hosts_from_current_batch(self, model_class: Type[T]) -> List[T]:
        """Collect host config from current batch."""
        return self._collect_from_batch('hosts', model_class)
    
    def collect_host_groups_from_current_batch(self, model_class: Type[T]) -> List[T]:
        """Collect host groups config from current batch."""
        return self._collect_from_batch('host_group', model_class)
    
    def collect_drives_from_current_batch(self, model_class: Type[T]) -> List[T]:
        """Collect drive config from current batch."""
        return self._collect_from_batch('drive_config', model_class)
    
    def collect_controllers_from_current_batch(self, model_class: Type[T]) -> List[T]:
        """Collect controller config from current batch."""
        return self._collect_from_batch('controller_config', model_class)
    
    def collect_storage_pools_from_current_batch(self, model_class: Type[T]) -> List[T]:
        """Collect storage pool config from current batch."""
        return self._collect_from_batch('storage_pool', model_class)
    
    def collect_volume_mappings_from_current_batch(self, model_class: Type[T]) -> List[T]:
        """Collect volume mappings config from current batch."""
        return self._collect_from_batch('volume_mapping', model_class)

    def get_batch_info(self) -> Dict[str, Any]:
        """Get batch information from the batch reader."""
        if not self.batched_reader:
            return {
                'available_batches': 0,
                'batch_window_minutes': 0,
                'total_files': 0,
                'current_batch': None
            }
        
        batch_info = self.batched_reader.get_current_batch_info()
        return {
            'available_batches': self.batched_reader.get_total_batches(),
            'batch_window_minutes': self.batched_reader.batch_size_minutes,
            'total_files': sum(len(files) for _, files in self.batched_reader.batches),
            'current_batch': batch_info[0] if batch_info else None
        }
    
    def _collect_from_batch(self, endpoint: str, model_class: Type[T]) -> List[T]:
        """Collect data from current batch files for given endpoint."""
        if not self.batched_reader:
            return []
        
        # Get current batch of files (without advancing)
        batch_files = self.batched_reader.get_current_batch()
        
        # Filter files for the specified endpoint
        endpoint_files = []
        endpoint_pattern = endpoint.lower().replace('-', '_')
        logger.debug(f"🔍 Filtering files for endpoint '{endpoint}' → pattern '{endpoint_pattern}'")
        logger.debug(f"🔍 Total batch files: {len(batch_files)}")
        
        for file_path in batch_files:
            filename = os.path.basename(file_path).lower()
            if endpoint_pattern in filename:
                endpoint_files.append(file_path)
                logger.debug(f"🔍 MATCH: {filename}")
            else:
                if 'performance' in filename and any(x in filename for x in ['volume', 'drive', 'system', 'interface', 'controller']):
                    logger.debug(f"🔍 NO MATCH: {filename}")
        
        logger.info(f"🔍 Found {len(endpoint_files)} files for endpoint '{endpoint}'")
        
        all_data = []
        
        for file_path in endpoint_files:
            try:
                # Use the parent class JSON reading functionality
                parsed_data = self.collect_from_json_directory(
                    directory=os.path.dirname(file_path),
                    pattern=os.path.basename(file_path),
                    model_class=model_class,
                    sort_by='filename'
                )
                all_data.extend(parsed_data)
            except Exception as e:
                logger.error(f"Failed to parse {file_path}: {e}")
                continue
        
        return all_data
    
    def advance_batch(self) -> bool:
        """Advance to the next batch after processing current one."""
        if not self.batched_reader:
            return False
        return self.batched_reader.advance_to_next_batch()