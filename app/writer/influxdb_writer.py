"""
InfluxDB writer for E-Series Performance Analyzer.
Writes enriched performance data to InfluxDB 3.x with proper field type handling.

Note: this file leverages batching_example.py from the https://github.com/InfluxCommunity/influxdb3-python project
License: Apache License, Version 2.0, January 2004 (http://www.apache.org/licenses/)
"""

import logging
import os
import time
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from influxdb_client_3 import InfluxDBClient3, WritePrecision, WriteOptions, write_client_options
from influxdb_client_3.exceptions.exceptions import InfluxDBError
from app.writer.base import Writer
from app.schema.base_model import BaseModel
from app.schema.models import (
    AnalysedDriveStatistics, AnalysedSystemStatistics, 
    AnalysedInterfaceStatistics, AnalyzedControllerStatistics
)
from app.validator.schema_validator import validate_measurements_for_influxdb, SchemaValidator
import inspect
from dataclasses import fields

LOG = logging.getLogger(__name__)

class BatchingCallback(object):
    """
    Callback handler for batched InfluxDB writes.
    
    Tracks write success/failure statistics and provides timing information
    for performance monitoring and debugging.
    """

    def __init__(self):
        self.write_status_msg = None
        self.write_count = 0
        self.error_count = 0
        self.retry_count = 0
        self.start = time.time_ns()

    def success(self, conf, data: str):
        """Called when a batch write succeeds."""
        self.write_count += 1
        self.write_status_msg = f"SUCCESS: {self.write_count} batches written"
        LOG.debug(f"Batch write successful: {len(data)} bytes")

    def error(self, conf, data: str, exception: InfluxDBError):
        """Called when a batch write fails permanently."""
        self.error_count += 1
        self.write_status_msg = f"FAILURE: {exception}"
        LOG.error(f"Batch write failed: {len(data)} bytes, error: {exception}")

    def retry(self, conf, data: str, exception: InfluxDBError):
        """Called when a batch write fails but will be retried."""
        self.retry_count += 1
        LOG.warning(f"Batch write retry {self.retry_count}: {len(data)} bytes, error: {exception}")

    def elapsed_ms(self) -> int:
        """Get elapsed time in milliseconds."""
        return (time.time_ns() - self.start) // 1_000_000
    
    def get_stats(self) -> Dict[str, Any]:
        """Get write statistics."""
        return {
            'writes': self.write_count,
            'errors': self.error_count, 
            'retries': self.retry_count,
            'elapsed_ms': self.elapsed_ms(),
            'status': self.write_status_msg
        }

class InfluxDBWriter(Writer):
    """
    Writer implementation for InfluxDB 3.x.
    
    Handles:
    - Second-level timestamp precision (no nanosecond bloat)
    - Automatic field type conversion using BaseModel mixin
    - observedTimeInMS conversion to seconds since epoch
    - Enriched tag and field mapping
    """
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize InfluxDB writer with configuration."""
        
        # Extract InfluxDB connection parameters from environment variables or config
        import os
        self.url = config.get('influxdb_url') or os.getenv('INFLUXDB_URL', 'https://influxdb:8181')
        self.token = config.get('influxdb_token') or os.getenv('INFLUXDB_TOKEN', '')
        self.database = config.get('influxdb_database') or os.getenv('INFLUXDB_DATABASE', 'epa')
        self.org = config.get('influxdb_org') or os.getenv('INFLUXDB_ORG', 'netapp')
        self.bucket = config.get('influxdb_bucket') or os.getenv('INFLUXDB_BUCKET', 'epa')
        self.tls_ca = config.get('tls_ca', None)
        # Get TLS validation setting from config (passed from main.py)
        self.tls_validation = config.get('tls_validation', 'strict')
        
        # Initialize batching configuration for performance optimization (before client init)
        # Use smaller batch size and shorter flush interval for single-iteration runs
        # max_iterations = int(os.getenv('MAX_ITERATIONS', '0'))
        # if max_iterations == 1:
        #     # Single iteration: optimize for immediate writes
        #     self.batch_size = 100   # Smaller batch size for immediate flushing
        #     self.flush_interval = 5_000  # 5 seconds - immediate flush for single runs
        #     LOG.info("Single iteration mode: using immediate batching (batch_size=100, flush_interval=5s)")
        # else:
        # Multi-iteration: optimize for throughput
        self.batch_size = 500  # Target batch size
        self.flush_interval = 60_000  # 60 seconds - matches collection interval
        LOG.info("Multi-iteration mode: using throughput batching (batch_size=500, flush_interval=60s)")

        self.batch_callback = BatchingCallback()  # Initialize callback for batching statistics
        
        # Initialize client
        self.client = None
        self._initialize_client()
        
        # Initialize schema validator for model-based type conversion
        self.schema_validator = SchemaValidator()
        
        # Enable debug file output only when COLLECTOR_LOG_LEVEL=DEBUG
        self.enable_debug_output = os.getenv('COLLECTOR_LOG_LEVEL', '').upper() == 'DEBUG'

        # Use COLLECTOR_LOG_FILE directory for debug outputs, disable if not available
        collector_log_file = os.getenv('COLLECTOR_LOG_FILE', '')
        if collector_log_file and collector_log_file != 'None':
            debug_dir = os.path.dirname(collector_log_file) if os.path.dirname(collector_log_file) else '.'
            if os.path.exists(debug_dir) and os.access(debug_dir, os.W_OK):
                self.debug_output_dir = debug_dir
                LOG.info(f"InfluxDB debug file output enabled (COLLECTOR_LOG_LEVEL=DEBUG) -> {self.debug_output_dir}")
            else:
                LOG.warning(f"Debug output directory {debug_dir} not accessible, disabling debug file output")
                self.enable_debug_output = False
        else:
            # No COLLECTOR_LOG_FILE specified, disable debug output
            LOG.debug("No COLLECTOR_LOG_FILE specified, debug file output disabled")
            self.enable_debug_output = False

        LOG.info(f"InfluxDBWriter initialized: {self.url} -> {self.database}")
    
    def _initialize_client(self):
        """Initialize the InfluxDB client with proper TLS configuration."""
        try:
            # InfluxDB always requires strict TLS validation - ignore user's tls_validation setting
            if self.tls_validation == 'disable' or self.tls_validation == 'none':
                LOG.warning("TLS validation 'disable'/'none' not supported for InfluxDB - InfluxDB requires strict TLS validation")
            
            # Configure write options for efficient batching (following official example)
            write_options = WriteOptions(
                batch_size=self.batch_size,         # Dynamic batch size based on MAX_ITERATIONS
                flush_interval=self.flush_interval, # Dynamic flush interval for immediate vs throughput mode
                jitter_interval=2_000,       # 2 seconds
                retry_interval=5_000,        # 5 seconds
                max_retries=5,
                max_retry_delay=30_000,      # 30 seconds
                max_close_wait=120_000,      # 2 minutes - enough time for cleanup
                exponential_base=2
            )
            
            # Configure write client options with callbacks (following official example)
            wco = write_client_options(
                success_callback=self.batch_callback.success,
                error_callback=self.batch_callback.error,
                retry_callback=self.batch_callback.retry,
                write_options=write_options
            )
            
            # Always use strict TLS validation for InfluxDB
            client_kwargs = {
                'host': self.url,
                'database': self.database, 
                'token': self.token,
                'enable_gzip': True,  # Enable gzip compression for better performance
                'write_client_options': wco,  # Batching configuration
                'verify_ssl': True,  # InfluxDB always uses strict TLS validation
                'timeout': 60000  # 60 second timeout (in milliseconds)
            }
            
            # Check for custom CA certificate from environment or config
            ca_cert_path = self.tls_ca or os.getenv('INFLUXDB3_TLS_CA')
            if ca_cert_path and os.path.exists(ca_cert_path):
                LOG.info(f"Using custom CA certificate: {ca_cert_path}")
                client_kwargs['ssl_ca_cert'] = ca_cert_path
            elif ca_cert_path:
                LOG.warning(f"CA certificate path specified but file not found: {ca_cert_path}")
            
            self.client = InfluxDBClient3(**client_kwargs)
            LOG.info(f"InfluxDB client created successfully with strict TLS validation to {self.url}")
            
            # Ensure database exists (with proper TLS handling)
            self._ensure_database_exists()
            
        except Exception as e:
            LOG.error(f"Failed to create InfluxDB client: {e}")
            raise

    def _ensure_database_exists(self):
        """Ensure the target database exists, creating it if necessary."""
        try:
            import requests
            
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Accept': 'application/json'
            }
            
            # Determine TLS verification - use custom CA if available, otherwise strict validation
            ca_cert_path = self.tls_ca or os.getenv('INFLUXDB3_TLS_CA')
            verify_tls = ca_cert_path if ca_cert_path and os.path.exists(ca_cert_path) else True
            
            # GET existing databases - always use strict TLS validation for InfluxDB
            get_url = f"{self.url}/api/v3/configure/database?format=json"
            response = requests.get(get_url, headers=headers, timeout=10, verify=verify_tls)
            
            if response.status_code == 200:
                databases_data = response.json()
                LOG.debug(f"Database list response type: {type(databases_data)}, content: {databases_data}")
                
                # Handle multiple response formats from InfluxDB database API
                databases = []
                if isinstance(databases_data, list):
                    # Check if it's a list of database name objects: [{"iox::database": "name"}]
                    if databases_data and isinstance(databases_data[0], dict) and "iox::database" in databases_data[0]:
                        databases = [db_obj["iox::database"] for db_obj in databases_data]
                        LOG.debug(f"API returned database object list: {databases}")
                    else:
                        # Simple list of database names: ["_internal", "epa"]
                        databases = databases_data
                        LOG.debug(f"API returned database name list: {databases}")
                elif isinstance(databases_data, dict):
                    databases = databases_data.get('databases', [])
                    LOG.debug(f"API returned database dict, extracted list: {databases}")
                else:
                    LOG.warning(f"Unexpected database list response format: {type(databases_data)}")
                    databases = []
                
                if self.database not in databases:
                    LOG.info(f"Database '{self.database}' does not exist, creating it")
                    
                    # POST to create database - use same TLS validation as GET request
                    create_url = f"{self.url}/api/v3/configure/database"
                    create_data = {"db": self.database}
                    create_response = requests.post(create_url, json=create_data, headers=headers, timeout=10, verify=verify_tls)
                    
                    if create_response.status_code in [200, 201, 204]:
                        LOG.info(f"Successfully created database '{self.database}'")
                    else:
                        LOG.error(f"Failed to create database '{self.database}': HTTP {create_response.status_code}")
                        LOG.error(f"Response: {create_response.text}")
                else:
                    LOG.info(f"Database '{self.database}' already exists")
            else:
                LOG.warning(f"Failed to check database existence: HTTP {response.status_code}")
                LOG.warning(f"Response: {response.text}")
                
        except Exception as db_error:
            LOG.warning(f"Could not verify database existence (will be created on first write): {db_error}")
    
    def write(self, measurements: Dict[str, Any], loop_iteration: int = 1) -> bool:
        """
        Write measurement data to InfluxDB using automatic client-side batching.
        
        Args:
            measurements: Dictionary of measurement name -> measurement data
            loop_iteration: Current iteration number for debug file naming
            
        Returns:
            bool: True if all writes succeeded, False otherwise
        """
        # Apply schema-based validation before writing to InfluxDB
        LOG.debug("Applying schema validation to measurements")
        try:
            from app.validator.schema_validator import validate_measurements_for_influxdb
            measurements = validate_measurements_for_influxdb(measurements)
            LOG.debug("Schema validation completed successfully")
        except Exception as e:
            LOG.error(f"Schema validation failed: {e}")
            import traceback
            LOG.error(traceback.format_exc())
        
        if not self.client:
            LOG.error("InfluxDB client not available")
            return False
        
        success = True
        written_count = 0
        
        for measurement_name, measurement_data in measurements.items():
            try:
                if not measurement_data:
                    LOG.debug(f"No data for measurement: {measurement_name}")
                    continue
                
                LOG.info(f"Processing InfluxDB measurement: {measurement_name} (Batch size: {len(measurement_data) if hasattr(measurement_data, '__len__') else 1} records)")
                
                # Debug tray config specifically
                if 'trayconfig' in measurement_name:
                    LOG.info(f"🔍 TRAY DEBUG: Processing {measurement_name} with {len(measurement_data) if hasattr(measurement_data, '__len__') else 1} records")
                
                # Convert to InfluxDB Point objects
                points = self._convert_to_points(measurement_name, measurement_data)
                
                # Debug tray config point conversion
                if 'trayconfig' in measurement_name:
                    LOG.info(f"🔍 TRAY DEBUG: Converted to {len(points)} points for {measurement_name}")
                
                if points:
                    # Write points using client's automatic batching (following official example)
                    # The client automatically batches writes based on write_options configuration
                    for point in points:
                        try:
                            self.client.write(record=point)
                            written_count += 1
                        except Exception as point_e:
                            LOG.error(f"Failed to write point: {point_e}")
                            success = False
                    
                    LOG.info(f"Successfully submitted {len(points)} points for {measurement_name} (automatic batching enabled)")
                else:
                    LOG.warning(f"No valid points converted for measurement: {measurement_name}")
                    
            except Exception as e:
                LOG.error(f"Failed to process InfluxDB measurement {measurement_name}: {e}", exc_info=True)
                success = False
        
        if written_count > 0:
            LOG.info(f"InfluxDB write submitted: {written_count} total points (batched by client)")
            
            # For single iteration mode, flush immediately to avoid delays during close()
            if os.getenv('MAX_ITERATIONS', '5') == '1':
                try:
                    LOG.info("Single iteration detected - flushing InfluxDB client immediately")
                    if (self.client and hasattr(self.client, '_client') and 
                        hasattr(self.client._client, 'write_api')):
                        write_api = self.client._client.write_api()
                        if hasattr(write_api, 'flush'):
                            write_api.flush()
                            LOG.info("InfluxDB write_api flushed successfully")
                        else:
                            LOG.debug("No flush method available on write_api")
                    else:
                        LOG.debug("No write_api available for flushing")
                except Exception as e:
                    LOG.warning(f"Failed to flush InfluxDB client: {e}")
        
        # Write debug output files if enabled
        if self.enable_debug_output:
            self._write_debug_input_json(measurements, loop_iteration)
            self._write_debug_line_protocol(measurements, loop_iteration)
        
        return success
    
    def _convert_to_points(self, measurement_name: str, data: Any) -> List:
        """
        Convert measurement data to InfluxDB Point objects for automatic batching.
        
        Args:
            measurement_name: Name of the measurement
            data: Raw measurement data (list of dicts or dataclasses)
            
        Returns:
            List of InfluxDB Point objects
        """
        # First convert to line protocol format (existing logic)
        records = self._convert_to_line_protocol(measurement_name, data)
        
        # Then convert dictionaries to Point objects
        from influxdb_client_3 import Point
        points = []
        
        for record in records:
            try:
                # Create Point object
                point = Point(measurement_name)
                
                # Add tags
                tags = record.get('tags', {})
                for tag_key, tag_value in tags.items():
                    if tag_value is not None:
                        point = point.tag(tag_key, str(tag_value))
                
                # Add fields  
                fields = record.get('fields', {})
                for field_key, field_value in fields.items():
                    if field_value is not None:
                        point = point.field(field_key, field_value)
                
                # Add timestamp
                timestamp = record.get('time')
                if timestamp:
                    point = point.time(timestamp, WritePrecision.S)
                
                points.append(point)
                
            except Exception as e:
                LOG.error(f"Failed to convert record to Point: {e}")
                continue
        
        LOG.debug(f"Converted {len(records)} records to {len(points)} Point objects for {measurement_name}")
        
        # Debug tray config point creation
        if 'trayconfig' in measurement_name:
            LOG.info(f"🔍 TRAY POINT DEBUG: {measurement_name} - {len(records)} records → {len(points)} points")
            if points and len(points) > 0:
                sample_point = points[0]
                LOG.info(f"🔍 TRAY POINT DEBUG: Sample point: {sample_point}")
            else:
                LOG.warning(f"🔍 TRAY POINT DEBUG: No points created for {measurement_name}!")
        
        return points
    
    def _convert_to_line_protocol(self, measurement_name: str, data: Any) -> List[Dict[str, Any]]:
        """
        Convert measurement data to InfluxDB line protocol format.
        
        Args:
            measurement_name: Name of the measurement
            data: Raw measurement data (list of dicts or dataclasses)
            
        Returns:
            List of InfluxDB record dictionaries
        """
        LOG.debug(f"Converting {measurement_name} to line protocol (data_len={len(data) if hasattr(data, '__len__') else 1})")
        records = []
        
        # Ensure data is a list
        if not isinstance(data, list):
            data = [data] if data else []
        
        for item in data:
            try:
                # Convert dataclass to dict if needed
                if hasattr(item, '__dict__'):
                    item_dict = item.__dict__
                elif isinstance(item, dict):
                    item_dict = item
                else:
                    LOG.warning(f"Unexpected data type for InfluxDB: {type(item)}")
                    continue
                
                # Determine measurement type and convert accordingly
                if measurement_name.startswith('config_'):
                    LOG.debug(f"Converting config record for {measurement_name}")
                    record = self._convert_config_record(measurement_name, item_dict)
                elif measurement_name == 'system_events':
                    record = self._convert_event_record(measurement_name, item_dict)
                elif measurement_name == 'system_failures':
                    record = self._convert_system_failures_record(measurement_name, item_dict)
                elif 'volume' in measurement_name.lower():
                    record = self._convert_volume_record(measurement_name, item_dict)
                elif 'drive' in measurement_name.lower():
                    record = self._convert_drive_record(measurement_name, item_dict)
                elif 'controller' in measurement_name.lower():
                    record = self._convert_controller_record(measurement_name, item_dict)
                elif 'interface' in measurement_name.lower():
                    record = self._convert_interface_record(measurement_name, item_dict)
                elif 'system' in measurement_name.lower():
                    record = self._convert_system_record(measurement_name, item_dict)
                else:
                    # Generic conversion for unknown measurement types
                    record = self._convert_generic_record(measurement_name, item_dict)
                
                if record:
                    records.append(record)
                    
            except Exception as e:
                LOG.warning(f"Failed to convert record in {measurement_name}: {e}")
                continue
        
        return records
    
    def _convert_volume_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert volume performance data to InfluxDB record format."""
        
        # Extract tags (indexed fields) - use both snake_case and camelCase
        # Sanitize tag values to avoid InfluxDB issues
        tags = {
            'volume_id': self._sanitize_tag_value(str(self._get_field_value(data, 'volume_id') or 'unknown')),
            'volume_name': self._sanitize_tag_value(str(self._get_field_value(data, 'volume_name') or 'unknown')),
            'controller_id': self._sanitize_tag_value(str(self._get_field_value(data, 'controller_id') or 'unknown')),
            'host': self._sanitize_tag_value(str(data.get('host', 'unknown'))),
            'host_group': self._sanitize_tag_value(str(data.get('host_group', 'unknown'))),
            'storage_pool': self._sanitize_tag_value(str(data.get('storage_pool', 'unknown'))),
            'storage_system_name': self._sanitize_tag_value(str(data.get('storage_system_name', 'unknown'))),
            'storage_system_wwn': self._sanitize_tag_value(str(data.get('storage_system_wwn', 'unknown')))
        }
        
        # Extract fields (values) using BaseModel conversion
        fields = {}
        
        # Performance metrics
        performance_fields = [
            'combined_iops', 'read_iops', 'other_iops',
            'combined_throughput', 'read_throughput', 'write_throughput',
            'combined_response_time', 'read_response_time', 'write_response_time',
            'average_queue_depth', 'queue_depth_max', 'queue_depth_total',
            'average_read_op_size', 'average_write_op_size',
            'read_cache_utilization', 'write_cache_utilization',
            'random_bytes_percent', 'random_ios_percent'
        ]
        
        for field_name in performance_fields:
            value = self._get_field_value(data, field_name)
            if value is not None:
                # Use value as-is from model - AnalysedVolumeStatistics defines these as Optional[float]
                fields[field_name] = value
        
        # Get timestamp - convert observedTimeInMS to seconds
        timestamp = self._extract_timestamp(data)
        
        if not fields:
            LOG.debug(f"No valid fields found for volume record: {tags['volume_name']}")
            return None
        
        return {
            'measurement': 'analyzed_volume_statistics',  # Use descriptive measurement name
            'tags': tags,
            'fields': fields,
            'time': timestamp
        }
    
    def _convert_drive_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert drive performance data to InfluxDB record format using schema."""
        return self._convert_schema_record(measurement_name, data, AnalysedDriveStatistics, {
            'drive_id': ('diskId', 'unknown'),
            'drive_slot': ('driveSlot', 'unknown'),
            'controller_id': ('sourceController', 'unknown'),
            'volume_group_id': ('volGroupId', 'unknown'),
            'volume_group_name': ('volGroupName', 'unknown'),
            'tray_id': ('trayId', 'unknown'),
            'storage_system_name': ('storageSystemName', 'unknown'),
            'storage_system_wwn': ('storageSystemWWN', 'unknown')
        }, [
            'combined_iops', 'read_iops', 'write_iops', 'other_iops',
            'combined_throughput', 'read_throughput', 'write_throughput',
            'combined_response_time', 'read_response_time', 'write_response_time',
            'average_queue_depth', 'queue_depth_max', 'average_read_op_size', 'average_write_op_size',
            'read_physical_iops', 'write_physical_iops', 'read_time_max', 'write_time_max',
            'random_bytes_percent', 'random_ios_percent'
        ])
    
    def _convert_controller_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert controller performance data to InfluxDB record format using schema."""
        # Controller statistics come wrapped in a "statistics" array
        if isinstance(data, dict) and 'statistics' in data:
            results = []
            for stat in data['statistics']:
                record = self._convert_schema_record(measurement_name, stat, AnalyzedControllerStatistics, {
                    'controller_id': ('controllerId', 'unknown'),
                    'source_controller': ('sourceController', 'unknown'),
                    'storage_system_name': ('storageSystemName', 'unknown'),
                    'storage_system_wwn': ('storageSystemWWN', 'unknown')
                }, [
                    'combined_iops', 'read_iops', 'write_iops', 'other_iops',
                    'combined_throughput', 'read_throughput', 'write_throughput',
                    'combined_response_time', 'read_response_time', 'write_response_time',
                    'average_read_op_size', 'average_write_op_size', 'read_physical_iops', 'write_physical_iops',
                    'cache_hit_bytes_percent', 'random_ios_percent', 'mirror_bytes_percent',
                    'full_stripe_writes_bytes_percent', 'max_cpu_utilization', 'cpu_avg_utilization'
                ])
                if record:
                    results.append(record)
            return results[0] if results else None
        else:
            return self._convert_schema_record(measurement_name, data, AnalyzedControllerStatistics, {
                'controller_id': ('controllerId', 'unknown'),
                'source_controller': ('sourceController', 'unknown'),
                'storage_system_name': ('storageSystemName', 'unknown'),
                'storage_system_wwn': ('storageSystemWWN', 'unknown')
            }, [
                'combined_iops', 'read_iops', 'write_iops', 'other_iops',
                'combined_throughput', 'read_throughput', 'write_throughput',
                'combined_response_time', 'read_response_time', 'write_response_time',
                'average_read_op_size', 'average_write_op_size', 'read_physical_iops', 'write_physical_iops',
                'cache_hit_bytes_percent', 'random_ios_percent', 'mirror_bytes_percent',
                'full_stripe_writes_bytes_percent', 'max_cpu_utilization', 'cpu_avg_utilization'
            ])
    
    def _convert_interface_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert interface performance data to InfluxDB record format using schema."""
        return self._convert_schema_record(measurement_name, data, AnalysedInterfaceStatistics, {
            'interface_id': ('interfaceId', 'unknown'),
            'controller_id': ('controllerId', 'unknown'),
            'channel_type': ('channelType', 'unknown'),
            'channel_number': ('channelNumber', 'unknown'),
            'storage_system_name': ('storageSystemName', 'unknown'),
            'storage_system_wwn': ('storageSystemWWN', 'unknown')
        }, [
            'combined_iops', 'read_iops', 'write_iops', 'other_iops',
            'combined_throughput', 'read_throughput', 'write_throughput',
            'combined_response_time', 'read_response_time', 'write_response_time',
            'average_read_op_size', 'average_write_op_size', 'queue_depth_total', 'queue_depth_max',
            'channel_error_counts'
        ])
    
    def _convert_system_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert system performance data to InfluxDB record format using schema."""
        return self._convert_schema_record(measurement_name, data, AnalysedSystemStatistics, {
            'storage_system_wwn': ('storageSystemWWN', 'unknown'),
            'storage_system_name': ('storageSystemName', 'unknown'),
            'source_controller': ('sourceController', 'unknown')
        }, [
            'combined_iops', 'read_iops', 'write_iops', 'other_iops',
            'combined_throughput', 'read_throughput', 'write_throughput',
            'combined_response_time', 'read_response_time', 'write_response_time',
            'average_read_op_size', 'average_write_op_size', 'read_physical_iops', 'write_physical_iops',
            'cache_hit_bytes_percent', 'random_ios_percent', 'mirror_bytes_percent',
            'full_stripe_writes_bytes_percent', 'max_cpu_utilization', 'cpu_avg_utilization',
            'raid0_bytes_percent', 'raid1_bytes_percent', 'raid5_bytes_percent', 'raid6_bytes_percent',
            'ddp_bytes_percent', 'read_hit_response_time', 'write_hit_response_time',
            'combined_hit_response_time', 'max_possible_bps_under_current_load', 'max_possible_iops_under_current_load'
        ])


    def _validate_and_extract_fields_from_model(self, model_class, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use the model class to validate and extract properly typed fields from data.
        
        This leverages your existing model type definitions and safe_int() conversions
        to ensure data types are correct before writing to InfluxDB.
        """
        if not model_class or not hasattr(model_class, '__dataclass_fields__'):
            return {}
            
        fields = {}
        model_fields = model_class.__dataclass_fields__
        
        # DEBUG: Log the actual data keys for HostConfig
        if 'hostconfig' in str(model_class).lower():
            LOG.debug(f"🔍 HOST DATA DEBUG - data keys: {list(data.keys())}")
        
        for field_name, field_info in model_fields.items():
            # Skip internal fields and complex objects
            if field_name.startswith('_') or field_name in ['listOfMappings', 'metadata', 'perms', 'cache', 'cacheSettings', 'mediaScan']:
                continue
                
            value = self._get_field_value(data, field_name)
            # DEBUG: Log field processing for HostConfig
            if 'hostconfig' in str(model_class).lower():
                LOG.debug(f"🔍 HOST FIELD DEBUG - {field_name}: value={value}, type={type(value)}, is_none={value is None}")
            if value is None:
                continue
                
            # Get the type annotation
            field_type = field_info.type
            
            # Handle Optional types (extract the inner type)
            if hasattr(field_type, '__origin__') and field_type.__origin__ is Union:
                # Optional[T] is Union[T, None]
                non_none_types = [t for t in field_type.__args__ if t is not type(None)]
                if non_none_types:
                    field_type = non_none_types[0]
            
            try:
                # Convert based on the expected type
                if field_type == int:
                    if isinstance(value, int):
                        fields[field_name] = value
                    elif isinstance(value, str) and (value.isdigit() or (value.startswith('-') and value[1:].isdigit())):
                        fields[field_name] = int(value)
                    elif isinstance(value, float) and value == int(value):
                        fields[field_name] = int(value)
                    else:
                        LOG.debug(f"Skipping field {field_name}: cannot convert {type(value).__name__} {value} to int")
                        
                elif field_type == float:
                    if isinstance(value, (int, float)):
                        fields[field_name] = float(value)
                    elif isinstance(value, str):
                        try:
                            fields[field_name] = float(value)
                        except ValueError:
                            LOG.debug(f"Skipping field {field_name}: cannot convert string '{value}' to float")
                    else:
                        LOG.debug(f"Skipping field {field_name}: cannot convert {type(value).__name__} to float")
                        
                elif field_type == bool:
                    if isinstance(value, bool):
                        fields[field_name] = int(value)  # InfluxDB stores booleans as 0/1
                    else:
                        LOG.debug(f"Skipping field {field_name}: expected bool, got {type(value).__name__}")
                        
                elif field_type == str:
                    # Store string fields as InfluxDB fields (valuable data like host names, labels, etc.)
                    if isinstance(value, str) and value:  # Only store non-empty strings
                        fields[field_name] = value
                    
                else:
                    # For complex types, skip or handle specially
                    LOG.debug(f"Skipping field {field_name}: complex type {field_type}")
                    
            except (ValueError, TypeError) as e:
                LOG.debug(f"Error converting field {field_name}: {e}")
                
        return fields

    def _convert_config_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert configuration data to InfluxDB record format."""
        LOG.debug(f"Converting config record for {measurement_name}")
        try:
            # Extract config type from measurement name (e.g., config_storage_pools -> storage_pools)
            config_type = measurement_name.replace('config_', '')
            
            # Create basic tags for configuration records
            tags = {
                'config_type': self._sanitize_tag_value(config_type),
                'storage_system': self._sanitize_tag_value(str(
                    data.get('storage_system',  # Use enriched storage_system first
                    data.get('storageSystemWWN', 
                    data.get('wwn', 'unknown')))))
            }
            
            # Add specific tags based on config type
            if 'storage_pool' in config_type:
                tags.update({
                    'pool_id': self._sanitize_tag_value(str(data.get('volumeGroupRef', data.get('id', 'unknown')))),
                    'pool_name': self._sanitize_tag_value(str(data.get('label', data.get('name', 'unknown')))),
                    'raid_level': self._sanitize_tag_value(str(data.get('raidLevel', 'unknown')))
                })
            elif 'volume' in config_type:
                tags.update({
                    'volume_id': self._sanitize_tag_value(str(data.get('volumeRef', data.get('id', 'unknown')))),
                    'volume_name': self._sanitize_tag_value(str(
                        data.get('volume_name',  # Use enriched volume_name first
                        data.get('label', 
                        data.get('name', 'unknown'))))),
                    'pool_id': self._sanitize_tag_value(str(
                        data.get('pool_id',  # Use enriched pool_id first  
                        data.get('volumeGroupRef', 'unknown'))))
                })
            elif 'controller' in config_type:
                tags.update({
                    'controller_id': self._sanitize_tag_value(str(data.get('id', 'unknown'))),
                    'controller_status': self._sanitize_tag_value(str(data.get('status', 'unknown')))
                    # Don't put controllerRef in tags - it should only be a field
                    # 'controller_id': self._sanitize_tag_value(str(data.get('controllerRef', data.get('id', 'unknown')))),
                })
            elif 'drive' in config_type:
                tags.update({
                    'drive_id': self._sanitize_tag_value(str(data.get('id', 'unknown'))),
                    'drive_type': self._sanitize_tag_value(str(data.get('driveMediaType', 'unknown'))),
                    'drive_status': self._sanitize_tag_value(str(data.get('status', 'unknown')))
                    # Don't put driveRef in tags - it should only be a field
                    # 'drive_id': self._sanitize_tag_value(str(data.get('driveRef', data.get('id', 'unknown')))),
                })
            elif 'tray' in config_type:
                tags.update({
                    'serial_number': self._sanitize_tag_value(str(data.get('serialNumber', 'unknown'))),
                    # Don't put partNumber in tags - it may not be unique across multiple trays of same model
                    # 'part_number': self._sanitize_tag_value(str(data.get('partNumber', 'unknown'))),
                })
            else:
                # Generic config record - try to find common ID fields
                for id_field in ['id', 'ref', 'wwn', 'controllerRef', 'volumeRef']:
                    if id_field in data:
                        tags['config_id'] = self._sanitize_tag_value(str(data[id_field]))
                        break
            
            # Use schema-based validation to extract properly typed fields
            LOG.debug(f"Processing schema validation for {measurement_name}")
            model_class = self.schema_validator.get_model_class(measurement_name)
            LOG.debug(f"Found model class: {model_class}")
            
            if model_class:
                LOG.debug(f"Using schema validation for {measurement_name} with model {model_class.__name__}")
                fields = self._validate_and_extract_fields_from_model(model_class, data)
                LOG.debug(f"Extracted fields: {list(fields.keys())}")
                
                # Debug logging for capacity field
                if 'capacity' in fields:
                    LOG.debug(f"Schema-based capacity: value={fields['capacity']}, type={type(fields['capacity'])}")
            else:
                LOG.debug(f"No model class found for {measurement_name}, using fallback field extraction")
                # Fallback to basic field extraction for unknown measurements
                fields = {}
                numeric_config_fields = [
                    'capacity', 'totalSizeInBytes', 'usableCapacity', 'freeSpace', 'usedSpace',
                    'driveCount', 'volumeCount', 'sequenceNum', 'trayId', 'slot'
                ]
                
                for field_name in numeric_config_fields:
                    value = self._get_field_value(data, field_name)
                    if value is not None and isinstance(value, (int, float)):
                        fields[field_name] = value
                        
                # Add boolean fields as integers (0/1)
                boolean_config_fields = ['active', 'offline', 'optimal', 'enabled', 'online', 'present']
                for field_name in boolean_config_fields:
                    value = data.get(field_name)
                    if isinstance(value, bool):
                        fields[field_name] = int(value)
            
            # Use current timestamp for config records (they don't have observedTime)
            import time
            timestamp = int(time.time())
            
            # Ensure we have at least one numeric field for InfluxDB
            if not fields:
                # If no numeric fields, add at least one field to make it a valid InfluxDB record
                fields['config_present'] = 1
            
            # For specific config types, try to extract additional numeric fields from raw data
            if 'interface' in config_type:
                # Extract basic numeric fields from nested InterfaceConfig data
                io_data = data.get('ioInterfaceTypeData', {})
                sas_data = io_data.get('sas', {}) if io_data else {}
                if sas_data:
                    # Extract numeric fields like channel, revision, isDegraded flag
                    if 'channel' in sas_data:
                        fields['channel'] = int(sas_data['channel'])
                    if 'revision' in sas_data:
                        fields['revision'] = int(sas_data['revision'])
                    if 'isDegraded' in sas_data:
                        fields['is_degraded'] = int(bool(sas_data['isDegraded']))
            
            elif 'tray' in config_type:
                # TrayConfig string fields (partNumber, serialNumber) are extracted by schema validation above
                # No additional numeric fields needed for tray config
                pass
            
            return {
                'measurement': measurement_name,
                'tags': tags,
                'fields': fields,
                'time': timestamp
            }
            
        except Exception as e:
            LOG.warning(f"Failed to convert config record {measurement_name}: {e}")
            return None

    def _convert_event_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert event data to InfluxDB record format."""
        try:
            # Create tags for event records
            tags = {
                'event_type': self._sanitize_tag_value(str(data.get('eventType', data.get('type', 'unknown')))),
                'storage_system': self._sanitize_tag_value(str(
                    data.get('storage_system',  # Use enriched storage_system first
                    data.get('storageSystemId', 
                    data.get('systemId', 'unknown'))))),
                'severity': self._sanitize_tag_value(str(data.get('severity', data.get('priority', 'info'))))
            }
            
            # Add event-specific tags
            if 'eventNumber' in data:
                tags['event_number'] = self._sanitize_tag_value(str(data['eventNumber']))
            
            if 'component' in data:
                tags['component'] = self._sanitize_tag_value(str(data['component']))
                
            if 'volumeId' in data:
                tags['volume_id'] = self._sanitize_tag_value(str(data['volumeId']))
                
            if 'volumeName' in data:
                tags['volume_name'] = self._sanitize_tag_value(str(data['volumeName']))
                
            if 'controllerId' in data:
                tags['controller_id'] = self._sanitize_tag_value(str(data['controllerId']))
            
            # Extract numeric fields from events
            fields = {}
            
            # Event counts and durations - preserve appropriate types
            integer_event_fields = ['count', 'collectionTime', 'lastCollectionTime', 'currentCollectionTime']
            float_event_fields = ['duration', 'progress', 'percentage']
            
            # Handle integer fields
            for field_name in integer_event_fields:
                value = self._get_field_value(data, field_name)
                if value is not None:
                    try:
                        fields[field_name] = int(value)
                    except (ValueError, TypeError):
                        pass  # Skip non-integer values
            
            # Handle float fields  
            for field_name in float_event_fields:
                value = self._get_field_value(data, field_name)
                if value is not None:
                    try:
                        fields[field_name] = float(value)
                    except (ValueError, TypeError):
                        pass  # Skip non-numeric values
            
            # Convert timestamp to seconds since epoch
            # For events, try timestamp field first, then fall back to observedTime
            timestamp = None
            if 'timestamp' in data:
                try:
                    # Parse ISO timestamp like "2025-09-13T14:26:10.195+00:00"
                    from datetime import datetime
                    dt = datetime.fromisoformat(data['timestamp'].replace('Z', '+00:00'))
                    timestamp = int(dt.timestamp())
                except:
                    timestamp = None
            
            if timestamp is None:
                timestamp = self._extract_timestamp(data)
            
            # Add at least one field for InfluxDB
            if not fields:
                fields['event_occurred'] = 1
            
            return {
                'measurement': 'system_events',  # Use consistent measurement name
                'tags': tags,
                'fields': fields,
                'time': timestamp
            }
            
        except Exception as e:
            LOG.warning(f"Failed to convert event record: {e}")
            return None
    
    def _convert_system_failures_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert system failures data to InfluxDB record format."""
        try:
            # Create tags for system failure records based on SystemFailures model
            tags = {
                'failure_type': self._sanitize_tag_value(str(data.get('failureType', 'unknown'))),
                'object_type': self._sanitize_tag_value(str(data.get('objectType', 'unknown'))),
                'storage_system': self._sanitize_tag_value(str(
                    data.get('storage_system',  # Use enriched storage_system first
                    data.get('storageSystemId', 
                    data.get('systemId', 'unknown')))))
            }
            
            # Fields for system failures - we need at least one numeric field for InfluxDB
            fields = {
                'failure_occurred': 1  # Simple indicator that failure occurred
            }
            
            # Add optional string fields as tags if they exist
            if 'objectRef' in data and data['objectRef']:
                tags['object_ref'] = self._sanitize_tag_value(str(data['objectRef']))
                
            if 'objectData' in data and data['objectData']:
                tags['object_data'] = self._sanitize_tag_value(str(data['objectData']))
                
            if 'extraData' in data and data['extraData']:
                tags['extra_data'] = self._sanitize_tag_value(str(data['extraData']))
            
            # Use current time as timestamp since system failures don't have observedTime
            import time
            timestamp = int(time.time())
            
            return {
                'measurement': 'system_failures',
                'tags': tags,
                'fields': fields,
                'time': timestamp
            }
            
        except Exception as e:
            LOG.warning(f"Failed to convert system failures record: {e}")
            return None
    
    def _convert_schema_record(self, measurement_name: str, data: Dict[str, Any], 
                             schema_class, tag_fields: Dict[str, tuple], 
                             numeric_fields: List[str]) -> Optional[Dict[str, Any]]:
        """Generic conversion using schema model."""
        try:
            # Create schema instance from data
            schema_instance = schema_class.from_api_response(data)
            
            # DEBUG: Log when BaseModel objects are created in writer
            if hasattr(schema_instance, '__class__') and 'BaseModel' in str(type(schema_instance)):
                LOG.debug(f"Created BaseModel instance in _convert_schema_record: {type(schema_instance)} for {measurement_name}")
            
            # Extract tags using provided mapping
            tags = {}
            for tag_name, (field_name, default_value) in tag_fields.items():
                # Get value from schema instance using camelCase field name
                value = getattr(schema_instance, field_name, None)
                if value is None:
                    # Try getting from raw data
                    value = schema_instance.get_raw(field_name, default_value)
                tags[tag_name] = self._sanitize_tag_value(str(value))
            
            # Extract numeric fields
            fields = {}
            for field_name in numeric_fields:
                # Convert snake_case to camelCase for schema access
                camel_field = BaseModel.snake_to_camel(field_name)
                value = getattr(schema_instance, camel_field, None)
                if value is None:
                    # Try getting from raw data
                    value = schema_instance.get_raw(camel_field, None)
                
                if value is not None:
                    # Use value as-is from model - schema defines appropriate types
                    fields[field_name] = value
            
            # Extract timestamp
            timestamp = self._extract_timestamp(data)
            
            # Clean up the schema instance reference to avoid BaseModel serialization issues
            del schema_instance
            
            if not fields:
                LOG.debug(f"No valid fields found for {measurement_name}")
                return None
            
            # Create the return record with primitive values only
            record = {
                'measurement': measurement_name,
                'tags': tags,
                'fields': fields,
                'time': timestamp
            }
            
            # DEBUG: Check for BaseModel objects in the record before returning
            def find_basemodel_in_record(obj, path=""):
                if hasattr(obj, '__class__') and 'BaseModel' in str(type(obj)):
                    LOG.error(f"🔍 WRITER DEBUG: Found BaseModel in record at {path}: {type(obj)}")
                    return True
                elif isinstance(obj, dict):
                    for k, v in obj.items():
                        if find_basemodel_in_record(v, f"{path}.{k}"):
                            return True
                elif isinstance(obj, (list, tuple)):
                    for i, v in enumerate(obj):
                        if find_basemodel_in_record(v, f"{path}[{i}]"):
                            return True
                return False
            
            find_basemodel_in_record(record, f"{measurement_name}_record")
                
            return record
            
        except Exception as e:
            LOG.warning(f"Error converting {measurement_name} using schema: {e}")
            return None

    def _convert_generic_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert generic record data to InfluxDB record format."""
        # Special handling for performance_data wrapper - treat as volume performance
        if measurement_name == 'performance_data':
            LOG.debug(f"Converting performance_data as volume performance record")
            return self._convert_volume_record('analyzed_volume_statistics', data)
        
        # Special handling for lockdown_status 
        if measurement_name == 'lockdown_status':
            return self._convert_lockdown_status_record(data)
        
        LOG.debug(f"Generic record conversion not implemented yet for {measurement_name}")
        return None
    
    def _convert_lockdown_status_record(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert lockdown status data to InfluxDB record format."""
        try:
            # Extract tags (indexed fields)
            tags = {
                'system_id': self._sanitize_tag_value(str(self._get_field_value(data, 'id') or 'unknown')),
                'lockdown_state': self._sanitize_tag_value(str(self._get_field_value(data, 'lockdownState') or 'unknown'))
            }
            
            # Extract fields (non-indexed data) 
            fields = {
                'is_lockdown': bool(self._get_field_value(data, 'isLockdown') or False),
                'lockdown_type': str(self._get_field_value(data, 'lockdownType') or 'unknown'),
                'storage_system_label': str(self._get_field_value(data, 'storageSystemLabel') or 'unknown')
            }
            
            # Add unlock key if present
            unlock_key_id = self._get_field_value(data, 'unlockKeyId')
            if unlock_key_id:
                fields['unlock_key_id'] = str(unlock_key_id)
            
            # Use current timestamp for lockdown status events
            timestamp = int(time.time())
            
            return {
                'measurement': 'lockdown_status',
                'tags': tags,
                'fields': fields,
                'time': timestamp
            }
            
        except Exception as e:
            LOG.warning(f"Failed to convert lockdown status record: {e}")
            return None
    
    def _get_field_value(self, data_dict: Dict[str, Any], field_name: str) -> Any:
        """Get field value, trying both snake_case and camelCase variants using proper conversion."""
        
        # Try direct match first (field_name as-is)
        if field_name in data_dict:
            return data_dict[field_name]
        
        # Try proper snake_case conversion (for camelCase field names)
        from app.utils import camel_to_snake_case
        snake_case = camel_to_snake_case(field_name)
        if snake_case in data_dict:
            return data_dict[snake_case]
        
        # Try camelCase equivalent (for snake_case field names)
        from app.utils import snake_to_camel_case
        camel_case = snake_to_camel_case(field_name)
        if camel_case in data_dict:
            return data_dict[camel_case]
            
        return None
    
    def _extract_timestamp(self, data: Dict[str, Any]) -> int:
        """
        Extract timestamp from data, converting observedTimeInMS to seconds.
        
        Args:
            data: Record data dictionary
            
        Returns:
            int: Unix timestamp in seconds
        """
        # Try to get observedTimeInMS first
        observed_time_ms = self._get_field_value(data, 'observed_time_in_ms')
        if observed_time_ms:
            try:
                # Convert string milliseconds to seconds (round down)
                timestamp_ms = int(observed_time_ms)
                timestamp_s = timestamp_ms // 1000  # Integer division for second precision
                LOG.debug(f"Converted observedTimeInMS {timestamp_ms} to seconds: {timestamp_s}")
                return timestamp_s
            except (ValueError, TypeError):
                LOG.debug(f"Could not convert observedTimeInMS to int: {observed_time_ms}")
        
        # Try other timestamp fields
        observed_time = self._get_field_value(data, 'observed_time')
        if observed_time:
            try:
                # Parse ISO 8601 timestamp
                dt = datetime.fromisoformat(observed_time.replace('Z', '+00:00'))
                timestamp_s = int(dt.timestamp())  # Round down to seconds
                LOG.debug(f"Converted observedTime {observed_time} to seconds: {timestamp_s}")
                return timestamp_s
            except (ValueError, TypeError):
                LOG.debug(f"Could not parse observedTime: {observed_time}")
        
        # Default to current time in seconds (no nanosecond bloat)
        current_time = int(time.time())  # Already in seconds, rounded down
        LOG.debug(f"Using current timestamp: {current_time}")
        return current_time
    
    def _sanitize_tag_value(self, value: str) -> str:
        """Sanitize tag values to avoid InfluxDB line protocol issues."""
        if not value:
            return 'unknown'
        
        # Strip leading/trailing whitespace and collapse multiple spaces
        sanitized = ' '.join(value.split())
        
        # Replace spaces with underscores
        sanitized = sanitized.replace(' ', '_')
        
        # Remove or escape problematic characters for InfluxDB tags
        # InfluxDB doesn't like commas, spaces, equals signs in tag values
        sanitized = sanitized.replace(',', '_').replace('=', '_').replace('\n', '_').replace('\r', '_')
        
        # If empty after sanitization, return unknown
        if not sanitized.strip():
            return 'unknown'
            
        return sanitized

    def get_batch_stats(self) -> Dict[str, Any]:
        """
        Get batching statistics from the client's automatic batching.
        
        Returns:
            Dictionary with batching statistics
        """
        if self.batch_callback:
            return self.batch_callback.get_stats()
        else:
            return {
                'writes': 0,
                'errors': 0, 
                'retries': 0,
                'elapsed_ms': 0,
                'status': 'No callback available'
            }

    def close(self, timeout_seconds=90, force_exit_on_timeout=False):
        """Close the InfluxDB client connection with timeout.
        
        Args:
            timeout_seconds: Maximum time to wait for graceful close
            force_exit_on_timeout: If True, force process exit after timeout to avoid zombie threads
        """
        if not self.client:
            return
        
        import threading
        import time
        
        timeout_seconds = 10  # Standard timeout for all modes
        LOG.info(f"Closing InfluxDB client with {timeout_seconds}s timeout...")        # Use a flag to track if close completed
        close_completed = threading.Event()
        close_error = []
        
        def close_thread():
            try:
                if self.client and hasattr(self.client, 'close') and callable(getattr(self.client, 'close')):
                    LOG.info("Calling InfluxDB client close() method")
                    start_close = time.time()
                    self.client.close()
                    close_elapsed = time.time() - start_close
                    LOG.info(f"InfluxDB client closed gracefully in {close_elapsed:.2f}s")
                close_completed.set()
            except Exception as e:
                close_error.append(e)
                LOG.warning(f"Error during graceful close: {e}")
                close_completed.set()
        
        # Start close in background thread
        closer = threading.Thread(target=close_thread, daemon=True)
        closer.start()
        
        # Wait for completion or timeout
        if close_completed.wait(timeout_seconds):
            if close_error:
                LOG.warning(f"Close completed with errors: {close_error[0]}")
            else:
                LOG.info("InfluxDB client closed successfully within timeout")
                # Even successful close may leave zombie threads - give them 5s to cleanup
                LOG.info("Waiting 5s for background threads to cleanup...")
                import time
                time.sleep(5)
        else:
            LOG.warning(f"InfluxDB client close timed out after {timeout_seconds}s - forcing shutdown")
            LOG.info("Pending writes may be lost, but avoiding indefinite hang")
        
        # Clear reference regardless
        self.client = None
        
        # Force process exit if requested to avoid zombie InfluxDB3 threads
        if force_exit_on_timeout:
            import os
            LOG.warning("Force exiting process to avoid zombie InfluxDB3 threads")
            LOG.info("All data has been preserved - terminating cleanly")
            os._exit(0)  # Hard exit - bypasses Python cleanup that can hang

    def _write_debug_input_json(self, measurements: Dict[str, Any], loop_iteration: int = 1):
        """
        Write input measurements to JSON file for debugging/validation.
        Only enabled when COLLECTOR_LOG_LEVEL=DEBUG.
        """
        if not self.enable_debug_output:
            return
            
        try:
            import json
            import os
            from datetime import datetime
            
            # Ensure output directory exists
            os.makedirs(self.debug_output_dir, exist_ok=True)
            
            # Use iteration-based filename to preserve iteration 1's config data
            if loop_iteration == 1:
                filename = "iteration_1_influxdb_writer_input_final.json"
            else:
                filename = "influxdb_writer_input_final.json"
            filepath = os.path.join(self.debug_output_dir, filename)
            
            # Convert data to JSON-serializable format
            serializable_data = {}
            for measurement_name, measurement_data in measurements.items():
                if measurement_data:  # Only include non-empty measurements
                    serializable_data[measurement_name] = []
                    if isinstance(measurement_data, list):
                        for item in measurement_data:
                            # Normalize to dict format
                            if hasattr(item, '__dict__'):
                                item_dict = item.__dict__
                            elif isinstance(item, dict):
                                item_dict = item
                            else:
                                item_dict = {"value": str(item)}
                            serializable_data[measurement_name].append(item_dict)
                    else:
                        # Single item
                        if hasattr(measurement_data, '__dict__'):
                            item_dict = measurement_data.__dict__
                        elif isinstance(measurement_data, dict):
                            item_dict = measurement_data
                        else:
                            item_dict = {"value": str(measurement_data)}
                        serializable_data[measurement_name] = [item_dict]
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(serializable_data, f, indent=2, default=str)
                
            LOG.info(f"InfluxDB writer input JSON saved to: {filepath}")
            
        except Exception as e:
            LOG.error(f"Failed to write InfluxDB debug input JSON: {e}")

    def _write_debug_line_protocol(self, measurements: Dict[str, Any], loop_iteration: int = 1):
        """
        Write generated line protocol to text file for debugging/validation.
        Only enabled when COLLECTOR_LOG_LEVEL=DEBUG.
        """
        if not self.enable_debug_output:
            return
            
        try:
            import os
            from datetime import datetime
            
            # Ensure output directory exists
            os.makedirs(self.debug_output_dir, exist_ok=True)
            
            # Use iteration-based filename to preserve iteration 1's config data
            if loop_iteration == 1:
                filename = "iteration_1_influxdb_line_protocol_final.txt"
            else:
                filename = "influxdb_line_protocol_final.txt"
            filepath = os.path.join(self.debug_output_dir, filename)
            
            # Generate line protocol for all measurements
            line_protocol_lines = []
            
            for measurement_name, measurement_data in measurements.items():
                if not measurement_data:
                    continue
                    
                # Convert to line protocol format (reuse existing logic)
                records = self._convert_to_line_protocol(measurement_name, measurement_data)
                
                for record in records:
                    try:
                        # Convert record dict to InfluxDB line protocol format
                        line = self._record_to_line_protocol(record)
                        if line:
                            line_protocol_lines.append(line)
                    except Exception as e:
                        LOG.debug(f"Failed to convert record to line protocol: {e}")
                        continue
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                for line in line_protocol_lines:
                    f.write(line + '\n')
                
            LOG.info(f"InfluxDB line protocol debug output saved to: {filepath} ({len(line_protocol_lines)} lines)")
            
        except Exception as e:
            LOG.error(f"Failed to write InfluxDB debug line protocol: {e}")

    def _record_to_line_protocol(self, record: Dict[str, Any]) -> str:
        """
        Convert a record dictionary to InfluxDB line protocol string format.
        
        Format: measurement,tag1=value1,tag2=value2 field1=value1,field2=value2 timestamp
        """
        try:
            measurement = record.get('measurement', 'unknown')
            tags = record.get('tags', {})
            fields = record.get('fields', {})
            timestamp = record.get('time', int(time.time()))
            
            # Build measurement name
            line_parts = [measurement]
            
            # Add tags
            if tags:
                tag_parts = []
                for tag_key, tag_value in sorted(tags.items()):
                    if tag_value is not None:
                        # Escape special characters in tag keys and values
                        escaped_key = str(tag_key).replace(',', r'\,').replace(' ', r'\ ').replace('=', r'\=')
                        escaped_value = str(tag_value).replace(',', r'\,').replace(' ', r'\ ').replace('=', r'\=')
                        tag_parts.append(f"{escaped_key}={escaped_value}")
                
                if tag_parts:
                    line_parts[0] += ',' + ','.join(tag_parts)
            
            # Add fields
            if fields:
                field_parts = []
                for field_key, field_value in sorted(fields.items()):
                    if field_value is not None:
                        # Escape field key
                        escaped_key = str(field_key).replace(',', r'\,').replace(' ', r'\ ').replace('=', r'\=')
                        
                        # Format field value based on type
                        if isinstance(field_value, str):
                            # String field - quote and escape
                            escaped_value = field_value.replace('"', r'\"').replace('\\', r'\\')
                            formatted_value = f'"{escaped_value}"'
                        elif isinstance(field_value, bool):
                            # Boolean field
                            formatted_value = 'true' if field_value else 'false'
                        elif isinstance(field_value, int):
                            # Integer field - add 'i' suffix
                            formatted_value = f"{field_value}i"
                        elif isinstance(field_value, float):
                            # Float field
                            formatted_value = str(field_value)
                        else:
                            # Default to string representation
                            str_value = str(field_value).replace('"', r'\"').replace('\\', r'\\')
                            formatted_value = f'"{str_value}"'
                        
                        field_parts.append(f"{escaped_key}={formatted_value}")
                
                if field_parts:
                    line_parts.append(' ' + ','.join(field_parts))
                else:
                    # No valid fields - skip this record
                    return ""
            else:
                # No fields - skip this record
                return ""
            
            # Add timestamp (in seconds, converted to nanoseconds for line protocol)
            line_parts.append(' ' + str(int(timestamp) * 1_000_000_000))
            
            return ''.join(line_parts)
            
        except Exception as e:
            LOG.debug(f"Failed to convert record to line protocol: {e}")
            return ""
