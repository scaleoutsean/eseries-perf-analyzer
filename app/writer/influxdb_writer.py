"""
InfluxDB writer for E-Series Performance Analyzer.
Writes enriched performance data to InfluxDB 3.x with proper field type handling.
"""

import logging
import os
import time
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from influxdb_client_3 import InfluxDBClient3
from app.writer.base import Writer
from app.schema.base_model import BaseModel
from app.schema.models import (
    AnalysedDriveStatistics, AnalysedSystemStatistics, 
    AnalysedInterfaceStatistics, AnalyzedControllerStatistics,
    VolumeConfig, DriveConfig, ControllerConfig, StoragePoolConfig,
    VolumeMappingsConfig, SystemConfig, TrayConfig, InterfaceConfig
)
from app.validator.schema_validator import validate_measurements_for_influxdb
import inspect
from dataclasses import fields

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
            
            # Determine TLS verification - use custom CA if available, otherwise strict validation
            ca_cert_path = self.tls_ca or os.getenv('INFLUXDB3_TLS_CA')
            verify_tls = ca_cert_path if ca_cert_path and os.path.exists(ca_cert_path) else True
            
            # GET existing databases - always use strict TLS validation for InfluxDB
            get_url = f"{self.url}/api/v3/configure/database?format=json"
            response = requests.get(get_url, headers=headers, timeout=10, verify=verify_tls)
            
            if response.status_code == 200:
                databases_data = response.json()
                databases = databases_data.get('databases', [])
                
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
    
    def write(self, measurements: Dict[str, Any]) -> bool:
        """
        Write measurement data to InfluxDB.
        
        Args:
            measurements: Dictionary of measurement name -> measurement data
            
        Returns:
            bool: True if all writes succeeded, False otherwise
        """
        # Apply schema-based validation before writing to InfluxDB
        LOG.error("SCHEMA_VALIDATION_START - About to apply schema validation")
        try:
            from app.validator.schema_validator import validate_measurements_for_influxdb
            LOG.error("SCHEMA_VALIDATION_IMPORT - Successfully imported schema validator")
            measurements = validate_measurements_for_influxdb(measurements)
            LOG.error("SCHEMA_VALIDATION_COMPLETE - Schema validation completed")
        except Exception as e:
            LOG.error(f"🔥 Schema validation failed: {e}")
            import traceback
            LOG.error(traceback.format_exc())
        
        # DEBUG: Dump what InfluxDB writer receives
        try:
            import json
            import pickle
            import os
            debug_dir = "/home/app/samples/out"
            os.makedirs(debug_dir, exist_ok=True)
            
            LOG.info(f"DEBUG: About to dump measurements with keys: {list(measurements.keys()) if measurements else 'None'}")
            
            # Comprehensive BaseModel detection
            def find_basemodels_in_measurements(obj, path="root"):
                """Recursively find BaseModel objects in measurement data"""
                findings = []
                
                try:
                    # Check if this object itself is a BaseModel
                    if hasattr(obj, '__class__'):
                        obj_mro = str(type(obj).__mro__)
                        if 'BaseModel' in obj_mro:
                            findings.append(f"BaseModel at {path}: {type(obj)} (MRO: {obj_mro})")
                    
                    # Recursively check containers
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            findings.extend(find_basemodels_in_measurements(value, f"{path}.{key}"))
                    elif isinstance(obj, (list, tuple)):
                        for i, item in enumerate(obj):
                            findings.extend(find_basemodels_in_measurements(item, f"{path}[{i}]"))
                except Exception as e:
                    findings.append(f"Error checking {path}: {e}")
                
                return findings
            
            # Check for BaseModel objects
            basemodel_findings = find_basemodels_in_measurements(measurements, "measurements")
            if basemodel_findings:
                LOG.error(f"DEBUG: BaseModel objects found in writer input:")
                for finding in basemodel_findings:
                    LOG.error(f"  {finding}")
                
                # Save findings to file
                with open(f"{debug_dir}/writer_input_basemodel_findings.txt", "w") as f:
                    f.write("BaseModel objects found in InfluxDB writer input:\n")
                    for finding in basemodel_findings:
                        f.write(f"{finding}\n")
            else:
                LOG.info(f"DEBUG: No BaseModel objects found in writer input")
            
            # Try JSON dump
            try:
                with open(f"{debug_dir}/influxdb_writer_input.json", "w") as f:
                    json.dump(measurements, f, indent=2, default=str)
                LOG.info(f"DEBUG: Successfully dumped InfluxDB writer input to JSON")
            except Exception as json_e:
                LOG.error(f"DEBUG: JSON dump failed: {json_e}")
                # Try pickle as fallback
                try:
                    with open(f"{debug_dir}/influxdb_writer_input.pkl", "wb") as f:
                        pickle.dump(measurements, f)
                    LOG.info(f"DEBUG: Successfully pickled InfluxDB writer input")
                except Exception as pickle_e:
                    LOG.error(f"DEBUG: Pickle dump also failed: {pickle_e}")
            
        except Exception as dump_e:
            LOG.error(f"DEBUG: Failed to dump writer input: {dump_e}")
            # Try to dump structure info at least
            try:
                with open(f"{debug_dir}/influxdb_writer_structure.txt", "w") as f:
                    for key, value in measurements.items():
                        f.write(f"{key}: {type(value)}\n")
                        if isinstance(value, list) and value:
                            f.write(f"  List item type: {type(value[0])}\n")
                LOG.info(f"DEBUG: Dumped structure info to {debug_dir}/influxdb_writer_structure.txt")
            except Exception as struct_e:
                LOG.error(f"DEBUG: Failed to dump structure info: {struct_e}")
        
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
                            
                            # DEBUG: Dump what we're about to send to InfluxDB client
                            try:
                                import json
                                import pickle
                                debug_dir = "/home/app/samples/out"
                                
                                # Try JSON dump first
                                try:
                                    with open(f"{debug_dir}/influxdb_client_batch_{measurement_name}_{batch_num}.json", "w") as f:
                                        json.dump(batch, f, indent=2, default=str)
                                    LOG.info(f"DEBUG: Successfully dumped JSON batch {batch_num} for {measurement_name}")
                                except Exception as json_e:
                                    LOG.error(f"DEBUG: JSON dump failed for batch {batch_num}: {json_e}")
                                    # If JSON fails, it might be a BaseModel issue - let's pickle it
                                    try:
                                        with open(f"{debug_dir}/influxdb_client_batch_{measurement_name}_{batch_num}.pkl", "wb") as f:
                                            pickle.dump(batch, f)
                                        LOG.info(f"DEBUG: Successfully pickled batch {batch_num} for {measurement_name}")
                                    except Exception as pickle_e:
                                        LOG.error(f"DEBUG: Pickle dump also failed: {pickle_e}")
                                
                                # Detailed BaseModel detection on the batch data
                                def find_basemodels_recursive(obj, path="root"):
                                    """Recursively find BaseModel objects in data structure"""
                                    findings = []
                                    
                                    if hasattr(obj, '__class__') and 'BaseModel' in str(type(obj).__mro__):
                                        findings.append(f"BaseModel at {path}: {type(obj)}")
                                    elif isinstance(obj, dict):
                                        for key, value in obj.items():
                                            findings.extend(find_basemodels_recursive(value, f"{path}.{key}"))
                                    elif isinstance(obj, (list, tuple)):
                                        for i, item in enumerate(obj):
                                            findings.extend(find_basemodels_recursive(item, f"{path}[{i}]"))
                                    
                                    return findings
                                
                                basemodel_findings = find_basemodels_recursive(batch, f"batch_{batch_num}")
                                if basemodel_findings:
                                    LOG.error(f"DEBUG: BaseModel objects found in batch {batch_num}:")
                                    for finding in basemodel_findings:
                                        LOG.error(f"  {finding}")
                                    
                                    # Save findings to file
                                    with open(f"{debug_dir}/basemodel_findings_batch_{batch_num}.txt", "w") as f:
                                        f.write(f"BaseModel objects found in {measurement_name} batch {batch_num}:\n")
                                        for finding in basemodel_findings:
                                            f.write(f"{finding}\n")
                                else:
                                    LOG.info(f"DEBUG: No BaseModel objects found in batch {batch_num}")
                                    
                            except Exception as batch_dump_e:
                                LOG.error(f"DEBUG: Failed to dump batch {batch_num}: {batch_dump_e}")
                            
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
        LOG.error(f"🔥 _convert_to_line_protocol called with measurement_name={measurement_name}, data_len={len(data) if hasattr(data, '__len__') else 1}")
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
                    LOG.error(f"🔥 About to call _convert_config_record for {measurement_name}")
                    record = self._convert_config_record(measurement_name, item_dict)
                elif measurement_name == 'system_events':
                    record = self._convert_event_record(measurement_name, item_dict)
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
                # Use value as-is from model - AnalysedVolumeStatistics defines these as Optional[float]
                fields[field_name] = value
        
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
        """Convert drive performance data to InfluxDB record format using schema."""
        return self._convert_schema_record(measurement_name, data, AnalysedDriveStatistics, {
            'drive_id': ('diskId', 'unknown'),
            'drive_slot': ('driveSlot', 'unknown'),
            'controller_id': ('sourceController', 'unknown'),
            'volume_group_id': ('volGroupId', 'unknown'),
            'volume_group_name': ('volGroupName', 'unknown'),
            'tray_id': ('trayId', 'unknown')
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
                    'source_controller': ('sourceController', 'unknown')
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
                'source_controller': ('sourceController', 'unknown')
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
            'channel_number': ('channelNumber', 'unknown')
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

    def _get_model_class_for_measurement(self, measurement_name: str):
        """Map measurement names to their corresponding model classes."""
        model_mapping = {
            'config_volumeconfig': VolumeConfig,
            'config_driveconfig': DriveConfig, 
            'config_controllerconfig': ControllerConfig,
            'config_storagepoolconfig': StoragePoolConfig,
            'config_volumemappingsconfig': VolumeMappingsConfig,
            'config_systemconfig': SystemConfig,
            'config_trayconfig': TrayConfig,
            'config_interfaceconfig': InterfaceConfig,
            # Add statistics models too
            'analyzed_drive_statistics': AnalysedDriveStatistics,
            'analyzed_system_statistics': AnalysedSystemStatistics,
            'analyzed_interface_statistics': AnalysedInterfaceStatistics,
            'analyzed_controller_statistics': AnalyzedControllerStatistics,
        }
        return model_mapping.get(measurement_name)

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
        
        for field_name, field_info in model_fields.items():
            # Skip internal fields and complex objects
            if field_name.startswith('_') or field_name in ['listOfMappings', 'metadata', 'perms', 'cache', 'cacheSettings', 'mediaScan']:
                continue
                
            value = self._get_field_value(data, field_name)
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
                    # For string fields, we typically don't store them as InfluxDB fields
                    # They're usually tags or skipped
                    continue
                    
                else:
                    # For complex types, skip or handle specially
                    LOG.debug(f"Skipping field {field_name}: complex type {field_type}")
                    
            except (ValueError, TypeError) as e:
                LOG.debug(f"Error converting field {field_name}: {e}")
                
        return fields

    def _convert_config_record(self, measurement_name: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert configuration data to InfluxDB record format."""
        LOG.info(f"🔥 _convert_config_record called with measurement_name={measurement_name}")
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
                    'controller_id': self._sanitize_tag_value(str(data.get('controllerRef', data.get('id', 'unknown')))),
                    'controller_status': self._sanitize_tag_value(str(data.get('status', 'unknown')))
                })
            elif 'drive' in config_type:
                tags.update({
                    'drive_id': self._sanitize_tag_value(str(data.get('driveRef', data.get('id', 'unknown')))),
                    'drive_type': self._sanitize_tag_value(str(data.get('driveMediaType', 'unknown'))),
                    'drive_status': self._sanitize_tag_value(str(data.get('status', 'unknown')))
                })
            else:
                # Generic config record - try to find common ID fields
                for id_field in ['id', 'ref', 'wwn', 'controllerRef', 'volumeRef']:
                    if id_field in data:
                        tags['config_id'] = self._sanitize_tag_value(str(data[id_field]))
                        break
            
            # Use schema-based validation to extract properly typed fields
            LOG.info(f"🔍 SCHEMA DEBUG - Processing measurement: {measurement_name}")
            model_class = self._get_model_class_for_measurement(measurement_name)
            LOG.info(f"🔍 SCHEMA DEBUG - Found model class: {model_class}")
            
            if model_class:
                LOG.info(f"Using schema validation for {measurement_name} with model {model_class.__name__}")
                fields = self._validate_and_extract_fields_from_model(model_class, data)
                LOG.info(f"🔍 SCHEMA DEBUG - Extracted fields: {list(fields.keys())}")
                
                # Debug logging for capacity field
                if 'capacity' in fields:
                    LOG.info(f"🔍 SCHEMA-BASED CAPACITY - value={fields['capacity']}, type={type(fields['capacity'])}")
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
            
            if not fields:
                # If no numeric fields, add at least one field to make it a valid InfluxDB record
                fields['config_present'] = 1
            
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
    
    def _convert_schema_record(self, measurement_name: str, data: Dict[str, Any], 
                             schema_class, tag_fields: Dict[str, tuple], 
                             numeric_fields: List[str]) -> Optional[Dict[str, Any]]:
        """Generic conversion using schema model."""
        try:
            # Create schema instance from data
            schema_instance = schema_class.from_api_response(data)
            
            # DEBUG: Log when BaseModel objects are created in writer
            if hasattr(schema_instance, '__class__') and 'BaseModel' in str(type(schema_instance)):
                LOG.info(f"🔍 WRITER DEBUG: Created BaseModel instance in _convert_schema_record: {type(schema_instance)} for {measurement_name}")
            
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