"""
Prometheus exporter writer for E-Series Performance Analyzer.
"""

import logging
import threading
from typing import Dict, Any, Optional

from prometheus_client import Gauge, CollectorRegistry, start_http_server
from app.writer.base import Writer
from app.schema.base_model import BaseModel

# Initialize logger
LOG = logging.getLogger(__name__)

class PrometheusWriter(Writer):
    """
    Writer that outputs performance data as Prometheus metrics for scraping.
    Only handles performance data, not configuration data.
    """
    
    def __init__(self, port: int = 8000):
        """
        Initialize the Prometheus writer.
        
        Args:
            port: Port to serve Prometheus metrics on (default: 8000)
        """
        self.port = port
        self.server_started = False
        self.server_lock = threading.Lock()
        
        # Create custom registry to avoid conflicts with default registry
        self.prometheus_registry = CollectorRegistry()
        
        # Initialize all metric definitions
        self.prometheus_metrics = self._initialize_metrics()
        
        # Add JSON output capability for debugging/validation (similar to InfluxDB writer)
        # Only enable debug output when COLLECTOR_LOG_LEVEL=DEBUG
        import os
        self.enable_json_output = os.getenv('COLLECTOR_LOG_LEVEL', '').upper() == 'DEBUG'
        self.json_output_dir = "/home/app/samples/out"
        
        # Add HTML metrics output capability for direct comparison with InfluxDB
        self.enable_html_output = os.getenv('COLLECTOR_LOG_LEVEL', '').upper() == 'DEBUG'
        
        if self.enable_json_output:
            LOG.info(f"Prometheus debug file output enabled (COLLECTOR_LOG_LEVEL=DEBUG)")
        
        LOG.info(f"PrometheusWriter initialized, will serve metrics on port {port}")
    
    def _initialize_metrics(self) -> Dict[str, Dict[str, Gauge]]:
        """Initialize all Prometheus metric definitions."""
        metrics = {}
        
        # Volume metrics - most important for storage monitoring
        metrics['volumes'] = {
            'iops': Gauge('eseries_volume_iops_total', 'Volume IOPS',
                         ['volume_id', 'volume_name', 'host', 'host_group', 'storage_pool', 'controller_id', 'operation'], 
                         registry=self.prometheus_registry),
            'throughput': Gauge('eseries_volume_throughput_bytes_per_second', 'Volume throughput in bytes/sec',
                               ['volume_id', 'volume_name', 'host', 'host_group', 'storage_pool', 'controller_id', 'direction'], 
                               registry=self.prometheus_registry),
            'response_time': Gauge('eseries_volume_response_time_seconds', 'Volume response time in seconds',
                                  ['volume_id', 'volume_name', 'host', 'host_group', 'storage_pool', 'controller_id', 'operation'], 
                                  registry=self.prometheus_registry)
        }

        # Drive metrics - hardware level performance
        metrics['disks'] = {
            'iops': Gauge('eseries_disk_iops_total', 'Total IOPS for disk',
                         ['sys_id', 'sys_name', 'sys_tray', 'sys_tray_slot', 'vol_group_name'],
                         registry=self.prometheus_registry),
            'throughput': Gauge('eseries_disk_throughput_bytes_per_second', 'Disk throughput in bytes/sec',
                               ['sys_id', 'sys_name', 'sys_tray', 'sys_tray_slot', 'vol_group_name', 'direction'],
                               registry=self.prometheus_registry),
            'response_time': Gauge('eseries_disk_response_time_seconds', 'Disk response time in seconds',
                                  ['sys_id', 'sys_name', 'sys_tray', 'sys_tray_slot', 'vol_group_name', 'operation'],
                                  registry=self.prometheus_registry),
            'ssd_wear': Gauge('eseries_disk_ssd_wear_percent', 'SSD wear level percentage',
                             ['sys_id', 'sys_name', 'sys_tray', 'sys_tray_slot', 'vol_group_name', 'metric'],
                             registry=self.prometheus_registry)
        }

        # Controller metrics - system level performance
        metrics['controllers'] = {
            'iops': Gauge('eseries_controller_iops_total', 'Controller IOPS',
                         ['sys_id', 'sys_name', 'controller_id', 'operation'], 
                         registry=self.prometheus_registry),
            'throughput': Gauge('eseries_controller_throughput_bytes_per_second', 'Controller throughput in bytes/sec',
                               ['sys_id', 'sys_name', 'controller_id', 'direction'], 
                               registry=self.prometheus_registry),
            'cpu_utilization': Gauge('eseries_controller_cpu_utilization_percent', 'Controller CPU utilization',
                                    ['sys_id', 'sys_name', 'controller_id', 'metric'], 
                                    registry=self.prometheus_registry),
            'cache_hit': Gauge('eseries_controller_cache_hit_percent', 'Controller cache hit percentage',
                              ['sys_id', 'sys_name', 'controller_id'], 
                              registry=self.prometheus_registry)
        }

        # System metrics - overall health
        metrics['systems'] = {
            'cpu_utilization': Gauge('eseries_system_cpu_utilization_percent', 'System CPU utilization',
                                    ['sys_id', 'sys_name', 'metric'], 
                                    registry=self.prometheus_registry)
        }

        # Interface metrics - network/channel performance
        metrics['interface'] = {
            'iops': Gauge('eseries_interface_iops_total', 'Interface IOPS',
                         ['sys_id', 'sys_name', 'interface_id', 'channel_type', 'operation'], 
                         registry=self.prometheus_registry),
            'throughput': Gauge('eseries_interface_throughput_bytes_per_second', 'Interface throughput in bytes/sec',
                               ['sys_id', 'sys_name', 'interface_id', 'channel_type', 'direction'], 
                               registry=self.prometheus_registry),
            'queue_depth': Gauge('eseries_interface_queue_depth', 'Interface queue depth',
                                ['sys_id', 'sys_name', 'interface_id', 'channel_type', 'metric'], 
                                registry=self.prometheus_registry)
        }

        # Environmental metrics
        metrics['power'] = {
            'total_power': Gauge('eseries_power_consumption_watts', 'Total power consumption in watts',
                                ['sys_id', 'sys_name'], 
                                registry=self.prometheus_registry)
        }

        metrics['temp'] = {
            'temperature': Gauge('eseries_temperature_celsius', 'Temperature in Celsius',
                                ['sys_id', 'sys_name', 'sensor', 'sensor_seq'], 
                                registry=self.prometheus_registry)
        }

        return metrics
    
    def _start_prometheus_server(self):
        """Start the Prometheus HTTP server if not already started."""
        with self.server_lock:
            if not self.server_started:
                try:
                    start_http_server(self.port, registry=self.prometheus_registry)
                    self.server_started = True
                    LOG.info(f"Prometheus metrics server started on port {self.port}")
                except Exception as e:
                    LOG.error(f"Failed to start Prometheus server on port {self.port}: {e}")
                    raise
    
    def write(self, data: Dict[str, Any]) -> bool:
        """
        Write data to Prometheus metrics.
        
        Args:
            data: Dictionary containing measurement data
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Apply schema-based validation before processing (following InfluxDB writer pattern)
            LOG.debug("Applying schema validation to measurements for Prometheus")
            try:
                from app.validator.schema_validator import validate_measurements_for_influxdb
                data = validate_measurements_for_influxdb(data)
                LOG.debug("Schema validation completed successfully")
            except Exception as e:
                LOG.error(f"Schema validation failed: {e}")
                # Continue processing even if validation fails
            
            # Start the metrics server if not already started
            if not self.server_started:
                self._start_prometheus_server()
            
            # Debug: Log the incoming data structure
            LOG.info(f"PrometheusWriter received data type: {type(data)}")
            LOG.info(f"PrometheusWriter received data keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            
            if isinstance(data, dict):
                for key, value in data.items():
                    LOG.info(f"  {key}: type={type(value)}, length={len(value) if hasattr(value, '__len__') else 'N/A'}")
            
            # Only process performance data (skip config data and events)
            measurements_processed = 0
            
            # Process each measurement type in the data
            for measurement_name, measurement_data in data.items():
                LOG.info(f"Processing measurement: {measurement_name}, is_performance: {self._is_performance_measurement(measurement_name)}")
                if self._is_performance_measurement(measurement_name):
                    self._process_measurement(measurement_name, measurement_data)
                    measurements_processed += 1
                else:
                    LOG.debug(f"Skipping non-performance measurement: {measurement_name}")
            
            # Write JSON output for debugging/validation (similar to InfluxDB writer)
            self._write_json_output(data, "prometheus_writer_input")
            
            # Write HTML metrics output for direct comparison with InfluxDB
            self._write_html_metrics_output("prometheus_metrics_export")
            
            LOG.info(f"Updated {measurements_processed} Prometheus measurement types")
            return True
            
        except Exception as e:
            LOG.error(f"Error writing to Prometheus: {e}", exc_info=True)
            return False
    
    def _is_performance_measurement(self, measurement_name: str) -> bool:
        """Determine if a measurement contains performance data (not config)."""
        performance_indicators = [
            'volume_statistics', 'analysed_volume_statistics',
            'drive_statistics', 'analysed_drive_statistics', 
            'controller_statistics', 'analysed_controller_statistics',
            'interface_statistics', 'analysed_interface_statistics',
            'system_statistics', 'analysed_system_statistics'
        ]
        
        return any(indicator in measurement_name.lower() for indicator in performance_indicators)
    
    def _process_measurement(self, measurement_name: str, measurement_data: list):
        """Process a single measurement type and update corresponding Prometheus metrics."""
        try:
            LOG.info(f"_process_measurement called with {measurement_name}, data type: {type(measurement_data)}, length: {len(measurement_data) if hasattr(measurement_data, '__len__') else 'N/A'}")
            
            if hasattr(measurement_data, '__len__') and len(measurement_data) > 0:
                LOG.info(f"First item in {measurement_name}: type={type(measurement_data[0])}")
                if hasattr(measurement_data[0], '__dict__'):
                    LOG.info(f"First item attributes: {list(measurement_data[0].__dict__.keys())}")
            
            # Determine measurement type for metric mapping
            if 'volume' in measurement_name.lower():
                LOG.info(f"Processing as volume metrics: {len(measurement_data) if hasattr(measurement_data, '__len__') else 0} items")
                self._process_volume_metrics(measurement_data)
            elif 'drive' in measurement_name.lower():
                LOG.info(f"Processing as drive metrics: {len(measurement_data) if hasattr(measurement_data, '__len__') else 0} items")
                self._process_drive_metrics(measurement_data)
            elif 'controller' in measurement_name.lower():
                LOG.info(f"Processing as controller metrics: {len(measurement_data) if hasattr(measurement_data, '__len__') else 0} items")
                self._process_controller_metrics(measurement_data)
            elif 'interface' in measurement_name.lower():
                LOG.info(f"Processing as interface metrics: {len(measurement_data) if hasattr(measurement_data, '__len__') else 0} items")
                self._process_interface_metrics(measurement_data)
            elif 'system' in measurement_name.lower():
                LOG.info(f"Processing as system metrics: {len(measurement_data) if hasattr(measurement_data, '__len__') else 0} items")
                self._process_system_metrics(measurement_data)
            else:
                LOG.debug(f"Unknown performance measurement type: {measurement_name}")
                
        except Exception as e:
            LOG.error(f"Error processing measurement {measurement_name}: {e}", exc_info=True)
    
    def _get_field_value(self, data_dict: dict, field_name: str):
        """
        Get field value, trying both snake_case and camelCase variants using BaseModel conversion.
        Enhanced version following InfluxDB writer pattern.
        """
        if not isinstance(data_dict, dict):
            return None
            
        # Try snake_case first (enriched field names)
        snake_case = field_name.lower().replace(' ', '_')
        if snake_case in data_dict:
            value = data_dict[snake_case]
            # Convert to appropriate numeric type if possible
            if isinstance(value, (int, float)):
                return value
            elif isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit():
                try:
                    return float(value) if '.' in value else int(value)
                except (ValueError, TypeError):
                    pass
            return value
        
        # Try camelCase equivalent using BaseModel conversion
        try:
            camel_case = BaseModel.snake_to_camel(snake_case)
            if camel_case in data_dict:
                value = data_dict[camel_case]
                # Same numeric conversion as above
                if isinstance(value, (int, float)):
                    return value
                elif isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit():
                    try:
                        return float(value) if '.' in value else int(value)
                    except (ValueError, TypeError):
                        pass
                return value
        except Exception as e:
            LOG.debug(f"Error in camelCase conversion for {field_name}: {e}")
            
        return None

    def _safe_numeric_operation(self, value1, value2, operation='subtract'):
        """Safely perform numeric operations, handling type conversion."""
        try:
            if value1 is None or value2 is None:
                return None
            
            # Convert to numbers
            num1 = float(value1) if isinstance(value1, (str, int, float)) else None
            num2 = float(value2) if isinstance(value2, (str, int, float)) else None
            
            if num1 is None or num2 is None:
                return None
                
            if operation == 'subtract':
                return num1 - num2
            elif operation == 'add':
                return num1 + num2
            elif operation == 'divide' and num2 != 0:
                return num1 / num2
            else:
                return None
        except (ValueError, TypeError, ZeroDivisionError):
            return None

    def _safe_float_conversion(self, value):
        """Safely convert value to float."""
        try:
            if value is None:
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    def _write_json_output(self, data: Dict[str, Any], filename_prefix: str = "prometheus_writer"):
        """
        Write processed data to JSON file for debugging/validation.
        Similar to InfluxDB writer's JSON output capability.
        """
        if not self.enable_json_output:
            return
            
        try:
            import json
            import os
            from datetime import datetime
            
            # Ensure output directory exists
            os.makedirs(self.json_output_dir, exist_ok=True)
            
            # Create timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.json"
            filepath = os.path.join(self.json_output_dir, filename)
            
            # Convert data to JSON-serializable format
            serializable_data = {}
            for measurement_name, measurement_data in data.items():
                if self._is_performance_measurement(measurement_name):
                    serializable_data[measurement_name] = []
                    if isinstance(measurement_data, list):
                        for item in measurement_data:
                            # Normalize to dict format
                            item_dict = self._normalize_data_item(item)
                            if item_dict:
                                serializable_data[measurement_name].append(item_dict)
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(serializable_data, f, indent=2, default=str)
                
            LOG.info(f"Prometheus writer JSON output saved to: {filepath}")
            
        except Exception as e:
            LOG.error(f"Failed to write JSON output: {e}")

    def _write_html_metrics_output(self, filename_prefix: str = "prometheus_metrics"):
        """
        Export current Prometheus metrics to HTML file for direct comparison with InfluxDB output.
        This captures the actual metrics that would be scraped by Prometheus.
        """
        if not self.enable_html_output:
            return
            
        try:
            import os
            from datetime import datetime
            from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
            
            # Ensure output directory exists
            os.makedirs(self.json_output_dir, exist_ok=True)
            
            # Create timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.txt"
            filepath = os.path.join(self.json_output_dir, filename)
            
            # Generate Prometheus metrics in text format (same as /metrics endpoint)
            metrics_text = generate_latest(self.prometheus_registry).decode('utf-8')
            
            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("# Prometheus Metrics Export\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n")
                f.write("# Format: Prometheus text exposition format\n")
                f.write("# This shows the actual metrics that would be scraped by Prometheus\n")
                f.write("\n")
                f.write(metrics_text)
                
            LOG.info(f"Prometheus metrics HTML output saved to: {filepath}")
            
        except Exception as e:
            LOG.error(f"Failed to write HTML metrics output: {e}")

    def _normalize_data_item(self, item):
        """
        Normalize data item to dictionary format, following InfluxDB writer pattern.
        """
        try:
            # Convert dataclass to dict if needed (same as InfluxDB writer)
            if hasattr(item, '__dict__'):
                return item.__dict__
            elif isinstance(item, dict):
                return item
            else:
                LOG.warning(f"Unexpected data type for Prometheus: {type(item)}")
                return None
        except Exception as e:
            LOG.error(f"Error normalizing data item: {e}")
            return None

    def _process_volume_metrics(self, volume_data: list):
        """Process volume performance data and update Prometheus metrics."""
        LOG.info(f"_process_volume_metrics called with {len(volume_data)} volumes")
        
        for i, volume in enumerate(volume_data):
            try:
                LOG.info(f"Processing volume {i+1}/{len(volume_data)}: type={type(volume)}")
                
                # Normalize data to dict format (following InfluxDB writer pattern)
                vol_dict = self._normalize_data_item(volume)
                if vol_dict is None:
                    LOG.warning(f"Could not normalize volume data item {i+1}")
                    continue
                    
                LOG.debug(f"Volume normalized keys: {list(vol_dict.keys())}")
                
                # Extract common labels from enriched volume data using snake_case
                labels = {
                    'volume_id': str(vol_dict.get('volume_id', vol_dict.get('volumeId', 'unknown'))),
                    'volume_name': str(vol_dict.get('volume_name', vol_dict.get('volumeName', 'unknown'))),
                    'host': str(vol_dict.get('host', 'unknown')),
                    'host_group': str(vol_dict.get('host_group', 'unknown')),
                    'storage_pool': str(vol_dict.get('storage_pool', 'unknown')),
                    'controller_id': str(vol_dict.get('controller_id', vol_dict.get('controllerId', 'unknown')))
                }
                
                LOG.info(f"Volume labels: {labels}")
                
                # Update IOPS metrics using snake_case field names
                combined_iops = self._get_field_value(vol_dict, 'combined_iops')
                if combined_iops is not None:
                    self.prometheus_metrics['volumes']['iops'].labels(
                        operation='total', **labels
                    ).set(float(combined_iops))
                    LOG.info(f"Set combined IOPS: {combined_iops} for volume {labels['volume_name']}")
                
                read_iops = self._get_field_value(vol_dict, 'read_iops')
                if read_iops is not None:
                    self.prometheus_metrics['volumes']['iops'].labels(
                        operation='read', **labels
                    ).set(float(read_iops))
                
                # Calculate write IOPS if not directly available
                write_iops = self._get_field_value(vol_dict, 'write_iops')
                if write_iops is None:
                    # Try alternate field names
                    other_iops = self._get_field_value(vol_dict, 'other_iops')
                    if combined_iops is not None and read_iops is not None:
                        write_iops = self._safe_numeric_operation(combined_iops, read_iops, 'subtract')
                    elif other_iops is not None:
                        write_iops = other_iops
                        
                if write_iops is not None:
                    self.prometheus_metrics['volumes']['iops'].labels(
                        operation='write', **labels
                    ).set(float(write_iops))
                
                # Update throughput metrics using snake_case field names
                read_throughput = self._get_field_value(vol_dict, 'read_throughput')
                if read_throughput is not None:
                    self.prometheus_metrics['volumes']['throughput'].labels(
                        direction='read', **labels
                    ).set(float(read_throughput))
                
                write_throughput = self._get_field_value(vol_dict, 'write_throughput')
                if write_throughput is not None:
                    self.prometheus_metrics['volumes']['throughput'].labels(
                        direction='write', **labels
                    ).set(float(write_throughput))
                
                # Update response time metrics using snake_case field names
                combined_response_time = self._get_field_value(vol_dict, 'combined_response_time')
                if combined_response_time is not None:
                    # Convert ms to seconds if needed (safe conversion)
                    combined_rt_float = self._safe_float_conversion(combined_response_time)
                    if combined_rt_float is not None:
                        response_time_seconds = combined_rt_float / 1000.0 if combined_rt_float > 1 else combined_rt_float
                        self.prometheus_metrics['volumes']['response_time'].labels(
                            operation='total', **labels
                        ).set(response_time_seconds)
                        LOG.info(f"Set combined response time: {combined_response_time}ms for volume {labels['volume_name']}")
                    self.prometheus_metrics['volumes']['response_time'].labels(
                        operation='total', **labels
                    ).set(float(combined_response_time) / 1000.0)  # Convert to seconds
                    LOG.info(f"Set combined response time: {combined_response_time}ms for volume {labels['volume_name']}")
                
            except Exception as e:
                LOG.error(f"Error processing volume metric: {e}")
    
    def _process_drive_metrics(self, drive_data: list):
        """Process drive performance data and update Prometheus metrics."""
        # TODO: Implement drive metrics processing
        LOG.debug(f"Processing {len(drive_data)} drive metrics (TODO)")
    
    def _process_controller_metrics(self, controller_data: list):
        """Process controller performance data and update Prometheus metrics."""
        # TODO: Implement controller metrics processing
        LOG.debug(f"Processing {len(controller_data)} controller metrics (TODO)")
    
    def _process_interface_metrics(self, interface_data: list):
        """Process interface performance data and update Prometheus metrics."""
        # TODO: Implement interface metrics processing
        LOG.debug(f"Processing {len(interface_data)} interface metrics (TODO)")
    
    def _process_system_metrics(self, system_data: list):
        """Process system performance data and update Prometheus metrics."""
        # TODO: Implement system metrics processing
        LOG.debug(f"Processing {len(system_data)} system metrics (TODO)")