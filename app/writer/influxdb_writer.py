"""
InfluxDB writer for E-Series Performance Analyzer.
Writes enriched performance data to InfluxDB 3.x with proper field type handling.
"""

import logging
import os
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from influxdb_client_3 import InfluxDBClient3
from app.writer.base import Writer
from app.schema.base_model import BaseModel

LOG = logging.getLogger(__name__)

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
        self.url = config.get('influxdb_url') or os.getenv('INFLUXDB_URL', 'https://influxdb:8086')
        self.token = config.get('influxdb_token') or os.getenv('INFLUXDB_TOKEN', '')
        self.database = config.get('influxdb_database') or os.getenv('INFLUXDB_DATABASE', 'eseries_perf')
        self.org = config.get('influxdb_org') or os.getenv('INFLUXDB_ORG', 'netapp')
        self.bucket = config.get('influxdb_bucket') or os.getenv('INFLUXDB_BUCKET', 'eseries_perf')
        self.tls_ca = config.get('tls_ca', None)
        # Get TLS validation setting from config (passed from main.py)
        self.tls_validation = config.get('tls_validation', 'strict')
        
        # Initialize client
        self.client = None
        self._initialize_client()
        
        LOG.info(f"InfluxDBWriter initialized: {self.url} -> {self.database}")
    
    def _initialize_client(self):
        """Initialize the InfluxDB client with proper TLS configuration."""
        try:
            # InfluxDB always requires strict TLS validation - ignore user's tls_validation setting
            if self.tls_validation == 'disable' or self.tls_validation == 'none':
                LOG.warning("TLS validation 'disable'/'none' not supported for InfluxDB - InfluxDB requires strict TLS validation")
            
            # Always use strict TLS validation for InfluxDB
            client_kwargs = {
                'host': self.url,
                'database': self.database, 
                'token': self.token,
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
            
            # GET existing databases - always use strict TLS validation for InfluxDB
            get_url = f"{self.url}/api/v3/configure/database?format=json"
            response = requests.get(get_url, headers=headers, timeout=10, verify=True)
            
            if response.status_code == 200:
                databases_data = response.json()
                databases = databases_data.get('databases', [])
                
                if self.database not in databases:
                    LOG.info(f"Database '{self.database}' does not exist, creating it")
                    
                    # POST to create database - always use strict TLS validation for InfluxDB
                    create_url = f"{self.url}/api/v3/configure/database"
                    create_data = {"db": self.database}
                    create_response = requests.post(create_url, json=create_data, headers=headers, timeout=10, verify=True)
                    
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
    
    def write(self, measurements: Dict[str, Any]) -> bool:
        """
        Write measurement data to InfluxDB.
        
        Args:
            measurements: Dictionary of measurement name -> measurement data
            
        Returns:
            bool: True if all writes succeeded, False otherwise
        """
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
                
                LOG.info(f"Processing InfluxDB measurement: {measurement_name} ({len(measurement_data) if hasattr(measurement_data, '__len__') else 1} records)")
                
                # Convert to InfluxDB line protocol format
                records = self._convert_to_line_protocol(measurement_name, measurement_data)
                
                if records:
                    # Debug: Log a sample record structure
                    if len(records) > 0:
                        sample_record = records[0]
                        LOG.debug(f"Sample record for {measurement_name}: tags={sample_record.get('tags', {})}, fields={list(sample_record.get('fields', {}).keys())}")
                    
                    # Debug: Log first few records as line protocol to see what's being sent
                    try:
                        from influxdb_client_3.write_client.client.write.point import Point
                        if len(records) > 0:
                            # Convert first record to line protocol for debugging
                            if isinstance(records[0], Point):
                                line_protocol_sample = records[0].to_line_protocol()
                            else:
                                # If it's a dict, manually create line protocol format for debugging
                                rec = records[0]
                                tags = rec.get('tags', {})
                                fields = rec.get('fields', {})
                                timestamp = rec.get('time', '')
                                
                                tag_str = ','.join([f'{k}={v}' for k, v in tags.items()]) if tags else ''
                                field_str = ','.join([f'{k}={v}' for k, v in fields.items()]) if fields else ''
                                line_protocol_sample = f"{measurement_name},{tag_str} {field_str} {timestamp}"
                            
                            LOG.debug(f"Sample line protocol for {measurement_name}: {line_protocol_sample}")
                    except Exception as debug_e:
                        LOG.debug(f"Could not generate debug line protocol: {debug_e}")
                    
                    # Write to InfluxDB in batches to avoid timeouts
                    batch_size = 50  # Write 50 records at a time - with no_sync=True should be fast
                    total_records = len(records)
                    
                    for i in range(0, total_records, batch_size):
                        batch = records[i:i + batch_size]
                        batch_num = (i // batch_size) + 1
                        total_batches = (total_records + batch_size - 1) // batch_size
                        
                        try:
                            LOG.debug(f"Writing batch {batch_num}/{total_batches} ({len(batch)} records)")
                            # NOTE: no_sync=True provides significant write performance improvement (19s vs 30+ seconds)
                            # but comes with durability risk - data may be lost on unexpected shutdown before WAL flush.
                            # This is acceptable for performance metrics collection where some data loss is tolerable
                            # vs. the alternative of write timeouts causing complete collection failures.
                            # InfluxDB WAL flush interval is configurable (default 10s in our entrypoint.sh).
                            self.client.write(
                                batch,
                                database=self.database,
                                time_precision='s',  # Second-level precision to avoid nanosecond bloat
                                no_sync=True  # Reduce write latency at cost of durability risk (see comment above)
                            )
                            written_count += len(batch)
                            LOG.debug(f"Successfully wrote batch {batch_num}/{total_batches}")
                                
                        except Exception as batch_e:
                            LOG.error(f"Failed to write batch {batch_num}/{total_batches}: {batch_e}")
                            success = False
                            break
                    
                    LOG.info(f"Successfully wrote {written_count} records to InfluxDB measurement: {measurement_name} (in {total_batches} batches)")
                else:
                    LOG.warning(f"No valid records converted for measurement: {measurement_name}")
                    
            except Exception as e:
                LOG.error(f"Failed to write InfluxDB measurement {measurement_name}: {e}", exc_info=True)
                success = False
        
        if written_count > 0:
            LOG.info(f"InfluxDB write completed: {written_count} total records")
        
        return success
    
    def _convert_to_line_protocol(self, measurement_name: str, data: Any) -> List[Dict[str, Any]]:
        """
        Convert measurement data to InfluxDB line protocol format.
        
        Args:
            measurement_name: Name of the measurement
            data: Raw measurement data (list of dicts or dataclasses)
            
        Returns:
            List of InfluxDB record dictionaries
        """
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
                if 'volume' in measurement_name.lower():
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
            'storage_pool': self._sanitize_tag_value(str(data.get('storage_pool', 'unknown')))
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
                try:
                    fields[field_name] = float(value)
                except (ValueError, TypeError):
                    LOG.debug(f"Could not convert {field_name} to float: {value}")
        
        # Get timestamp - convert observedTimeInMS to seconds
        timestamp = self._extract_timestamp(data)
        
        if not fields:
            LOG.debug(f"No valid fields found for volume record: {tags['volume_name']}")
            return None
        
        return {
            'measurement': 'analysed_volume_statistics',  # Use descriptive measurement name
            'tags': tags,
            'fields': fields,
            'time': timestamp
        }
    
    def _convert_drive_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert drive performance data to InfluxDB record format."""
        # TODO: Implement when we add drive performance data
        LOG.debug(f"Drive record conversion not implemented yet for {measurement_name}")
        return None
    
    def _convert_controller_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert controller performance data to InfluxDB record format."""
        # TODO: Implement when we add controller performance data  
        LOG.debug(f"Controller record conversion not implemented yet for {measurement_name}")
        return None
    
    def _convert_interface_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert interface performance data to InfluxDB record format."""
        # TODO: Implement when we add interface performance data
        LOG.debug(f"Interface record conversion not implemented yet for {measurement_name}")
        return None
    
    def _convert_system_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert system performance data to InfluxDB record format."""
        # TODO: Implement when we add system performance data
        LOG.debug(f"System record conversion not implemented yet for {measurement_name}")
        return None
    
    def _convert_generic_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert generic record data to InfluxDB record format."""
        # Special handling for performance_data wrapper - treat as volume performance
        if measurement_name == 'performance_data':
            LOG.debug(f"Converting performance_data as volume performance record")
            return self._convert_volume_record('analysed_volume_statistics', data)
        
        LOG.debug(f"Generic record conversion not implemented yet for {measurement_name}")
        return None
    
    def _get_field_value(self, data_dict: Dict[str, Any], field_name: str) -> Any:
        """Get field value, trying both snake_case and camelCase variants using BaseModel conversion."""
        
        # Try snake_case first (enriched field names)
        snake_case = field_name.lower().replace(' ', '_')
        if snake_case in data_dict:
            return data_dict[snake_case]
        
        # Try camelCase equivalent using BaseModel conversion
        camel_case = BaseModel.snake_to_camel(snake_case)
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
        
        # Replace spaces with underscores
        sanitized = value.replace(' ', '_')
        
        # Remove or escape problematic characters for InfluxDB tags
        # InfluxDB doesn't like commas, spaces, equals signs in tag values
        sanitized = sanitized.replace(',', '_').replace('=', '_').replace('\n', '_').replace('\r', '_')
        
        # If empty after sanitization, return unknown
        if not sanitized.strip():
            return 'unknown'
            
        return sanitized

    def close(self):
        """Close the InfluxDB client connection."""
        if self.client:
            # InfluxDBClient3 doesn't require explicit close
            self.client = None
            LOG.info("InfluxDB client closed")