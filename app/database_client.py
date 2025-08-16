# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

"""
Centralized InfluxDB 3.x DB client management for E-Series Performance Analyzer.

Provides a unified interface for all collectors to write data to InfluxDB with
proper field type enforcement and error handling.
"""

import logging
import certifi
from urllib.parse import urlparse
from influxdb_client_3 import InfluxDBClient3
from influxdb_client_3 import flight_client_options
from app.config import INFLUXDB_WRITE_PRECISION
from app.metrics_schemas import MEASUREMENT_SCHEMAS, get_integer_fields_for_measurement

LOG = logging.getLogger(__name__)

class DatabaseClient:
    """
    Centralized InfluxDB 3.x client wrapper that handles:
    - Client creation and connection management
    - Automatic field type enforcement based on schemas
    - Consistent write operations across all collectors
    - Error handling and logging
    """
    
    def __init__(self, influxdb_url, auth_token, database_name, tls_ca=None, tls_validation='strict'):
        """
        Initialize the database client.
        
        Args:
            influxdb_url: Full InfluxDB URL (e.g., https://influxdb:8181)
            auth_token: InfluxDB authentication token
            database_name: Database name to write to
            tls_ca: Path to CA certificate file (optional)
            tls_validation: TLS validation mode ('normal', 'strict', 'none')
        """
        self.database_name = database_name
        self.client = None
        
        # Debug TLS parameters
        LOG.info(f"DatabaseClient init: tls_ca='{tls_ca}', tls_validation='{tls_validation}'")
        
        try:
            # Configure TLS settings based on validation mode
            client_kwargs = {
                'host': influxdb_url,  # Use full URL with scheme (https://influxdb:8181)
                'database': database_name, 
                'token': auth_token
            }
            
            if tls_validation == 'none':
                client_kwargs['verify_ssl'] = False
            else:
                # Create a temporary certificate bundle combining system CAs with custom CA
                import tempfile
                import os
                
                # Use certifi to get system CA bundle
                with open(certifi.where(), "r") as f:
                    cert_bundle = f.read()
                
                LOG.debug(f"Certifi bundle loaded from {certifi.where()}, size: {len(cert_bundle)} chars")
                
                # If custom CA is provided, append it to the certifi bundle
                if tls_ca:
                    try:
                        with open(tls_ca, 'r') as f:
                            custom_ca = f.read()
                        cert_bundle += "\n" + custom_ca
                        LOG.info(f"Added custom CA certificate from {tls_ca} to certifi bundle")
                        LOG.debug(f"Combined certificate bundle size: {len(cert_bundle)} chars")
                    except Exception as ca_error:
                        LOG.warning(f"Failed to load CA certificate from {tls_ca}: {ca_error}")
                
                # Create temporary file with combined certificate bundle
                temp_ca_file = tempfile.NamedTemporaryFile(mode='w', suffix='.crt', delete=False)
                temp_ca_file.write(cert_bundle)
                temp_ca_file.close()
                
                # Store the temp file path for cleanup later
                self.temp_ca_file = temp_ca_file.name
                LOG.debug(f"Created temporary CA bundle file: {self.temp_ca_file}")
                
                client_kwargs['flight_client_options'] = flight_client_options(
                    tls_root_certs=cert_bundle
                )
                LOG.debug("Applied flight_client_options with custom TLS root certificates")
            
            self.client = InfluxDBClient3(**client_kwargs)
            LOG.info(f"Created InfluxDB client: {influxdb_url} -> {database_name} (TLS: {tls_validation})")
            
        except Exception as e:
            LOG.error(f"Failed to create InfluxDB client: {e}")
            raise
    
    def write(self, records, measurement_name=None):
        """
        Write records to InfluxDB with automatic field type enforcement.
        
        Args:
            records: List of record dictionaries or single record
            measurement_name: Optional measurement name for field type lookup
                            (if not provided, will try to extract from first record)
        
        Returns:
            bool: True if write succeeded, False otherwise
        """
        if not self.client:
            LOG.error("InfluxDB client not available")
            return False
            
        if not records:
            LOG.warning("No records to write")
            return True
            
        # Ensure records is a list
        if isinstance(records, dict):
            records = [records]
        elif not isinstance(records, list):
            LOG.error(f"Invalid records type: {type(records)}")
            return False
        
        # Determine measurement name if not provided
        if not measurement_name and records:
            measurement_name = records[0].get('measurement')
        
        # Get integer fields for this measurement and convert data types
        if measurement_name:
            integer_fields = get_integer_fields_for_measurement(measurement_name)
            if integer_fields:
                records = self._convert_field_types(records, integer_fields)
                LOG.debug(f"Converted field types for {measurement_name}: {integer_fields}")
            else:
                LOG.debug(f"No integer field conversions needed for {measurement_name}")
        
        # Get field type mappings for this measurement
        field_types = {}
        if measurement_name and measurement_name in MEASUREMENT_SCHEMAS:
            schema = MEASUREMENT_SCHEMAS[measurement_name]
            # Map field types for InfluxDB client
            for field_name, field_type in schema.get('fields', {}).items():
                if field_type.startswith('int'):
                    field_types[field_name] = "int"
                elif field_type == 'bool':
                    field_types[field_name] = "boolean"
                # Add other types as needed
            
            if field_types:
                LOG.debug(f"Applying field types for {measurement_name}: {field_types}")
        
        try:
            self.client.write(
                records,
                database=self.database_name,
                field_types=field_types,
                time_precision=INFLUXDB_WRITE_PRECISION
            )
            LOG.info(f"Successfully wrote {len(records)} records to {measurement_name or 'unknown'}")
            return True
            
        except Exception as e:
            # Log detailed error information including sample record for debugging
            sample_record = ""
            if records and len(records) > 0:
                # Get first record and truncate to 128 characters for logging
                sample_str = str(records[0])
                sample_record = f" | Sample record (first 128 chars): {sample_str[:128]}{'...' if len(sample_str) > 128 else ''}"
            
            LOG.error(f"Failed to write {len(records)} records to {measurement_name or 'unknown'}: {e}{sample_record}")
            
            # Write failed records to /data/failed/ for debugging
            self._write_failed_records(records, measurement_name, str(e))
            
            return False
    
    def _convert_field_types(self, records, integer_fields):
        """
        Convert field types in records according to schema requirements from metrics_schemas.py
        Only converts fields that need to be integers (e.g., float→int for error counts, bool→int for flags).
        Converts booleans to integers (0/1) for fields defined as int64 in schemas.
        
        Args:
            records: List of record dictionaries 
            integer_fields: List of field names that should be converted to integers
            
        Returns:
            List of records with converted field types
        """
        converted_records = []
        
        for record in records:
            converted_record = record.copy()
            
            # Convert fields within the 'fields' dict if it exists
            if 'fields' in converted_record and isinstance(converted_record['fields'], dict):
                converted_fields = converted_record['fields'].copy()
                
                for field_name in integer_fields:
                    if field_name in converted_fields:
                        value = converted_fields[field_name]
                        
                        # Convert float to integer (for fields like channelErrorCounts that come as 0.0)
                        if isinstance(value, float):
                            converted_fields[field_name] = int(value)
                            LOG.debug(f"Converted float field {field_name}: {value} -> {int(value)}")
                        
                        # Convert boolean to integer (for fields like ssdWearLife_isWearLifeMonitoringSupported)
                        elif isinstance(value, bool):
                            converted_fields[field_name] = 1 if value else 0
                            LOG.debug(f"Converted boolean field {field_name}: {value} -> {1 if value else 0}")
                        
                        # Convert string numbers that should be integers
                        elif isinstance(value, str) and value.replace('-','').replace('.','').isdigit():
                            try:
                                converted_fields[field_name] = int(float(value))
                                LOG.debug(f"Converted string field {field_name}: {value} -> {int(float(value))}")
                            except (ValueError, TypeError):
                                # Leave as-is if conversion fails
                                pass
                        
                        # Leave integers as-is (no conversion needed)
                
                converted_record['fields'] = converted_fields
            
            converted_records.append(converted_record)
        
        return converted_records
    
    def _write_failed_records(self, records, measurement_name, error_message):
        """
        Write failed records to /data/failed/ directory for debugging
        
        Args:
            records: List of failed records
            measurement_name: Name of the measurement that failed
            error_message: Error message from the write failure
        """
        try:
            import os
            import json
            from datetime import datetime
            
            # Create failed directory if it doesn't exist
            # In theory we could make this configurable, but it's rarely going to be used
            # and this directory was documented since v4.0.0 beta.
            # Even if the user uses `--toJson /data/failed` (silly choice), that is unlikely to cause
            # problems unless extreme incompetence is involved.
            failed_dir = '/data/failed'
            os.makedirs(failed_dir, exist_ok=True)
            
            # Create filename with timestamp and measurement name (ms ought to be enough for everyone)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # microseconds to milliseconds
            filename = f"{measurement_name}_{timestamp}_failed.json"
            filepath = os.path.join(failed_dir, filename)
            
            # Create failure report
            failure_data = {
                'timestamp': datetime.now().isoformat(),
                'measurement': measurement_name,
                'error_message': error_message,
                'record_count': len(records),
                'failed_records': records[:10],  # Only save first 10 records to avoid creating huge JSON files
                'sample_record_full': records[0] if records else None
            }
            
            # Write to file
            with open(filepath, 'w') as f:
                json.dump(failure_data, f, indent=2, default=str)
            
            LOG.info(f"Wrote failure log to {filepath} ({len(records)} records)")
            
        except Exception as log_error:
            LOG.warning(f"Failed to write failure log: {log_error}")
    
    def is_available(self):
        """Check if the InfluxDB client is available."""
        return self.client is not None


def create_database_client(influxdb_url, auth_token, database_name, tls_ca=None, tls_validation='strict'):
    """
    Factory function to create a DatabaseClient instance.
    
    Args:
        influxdb_url: InfluxDB server URL
        auth_token: Authentication token
        database_name: Database name
        tls_ca: Path to CA certificate file (optional)
        tls_validation: TLS validation mode ('strict', 'normal', 'none')
    
    Returns:
        DatabaseClient: Configured client instance, or None if creation failed
    """
    if not all([influxdb_url, auth_token, database_name]):
        LOG.warning("Missing InfluxDB configuration - client not created")
        return None
        
    try:
        return DatabaseClient(influxdb_url, auth_token, database_name, tls_ca, tls_validation)
    except Exception as e:
        LOG.error(f"Failed to create database client: {e}")
        return None
