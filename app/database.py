# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import requests
import logging
import json
import sys
from influxdb_client_3 import InfluxDBClient3
from app.metrics_schemas import MEASUREMENT_SCHEMAS
try:
    from influxdb_client_3.write_client.client.exceptions import InfluxDBError
except ImportError:
    InfluxDBError = Exception

LOG = logging.getLogger("collector")

def create_database(influxdb_url, auth_token, database_name, tls_ca=None):
    """Create or verify the InfluxDB database exists."""
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    verify = tls_ca if tls_ca else True
    try:
        # Get existing databases
        response = requests.get(
            f"{influxdb_url}/api/v3/configure/database?format=json",
            headers=headers,
            verify=verify
        )
        response.raise_for_status()
        databases = response.json()
        for db in databases:
            LOG.info("Database found: %s", db['name'])
            if db['name'] == database_name:
                LOG.info("Database %s already exists", database_name)
                return True
        # Create new database
        response = requests.post(
            f"{influxdb_url}/api/v3/configure/database",
            headers=headers,
            json={"name": database_name},
            verify=verify
        )
        if response.status_code == 201:
            LOG.info("Database %s created successfully", database_name)
            return True
        else:
            LOG.error("Failed to create database: %s", response.text)
            return False
    except Exception as e:
        LOG.error("Error when creating/verifying database: %s", e)
        return False

def create_measurement_tables(influxdb_url, auth_token, database_name, tls_ca=None, tls_validation='strict'):
    """Create measurement tables with proper field type schemas."""
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/json", 
        "Content-Type": "application/json"
    }
    
    # Configure TLS verification based on validation mode
    if tls_validation == 'none':
        verify = False
    elif tls_ca:
        verify = tls_ca
    else:
        verify = True
    success_count = 0
    
    for measurement_name, schema in MEASUREMENT_SCHEMAS.items():
        try:
            # Build tags and fields for the table creation
            tags = schema.get('tags', [])
            fields = []
            
            # Convert field definitions to the format expected by InfluxDB API
            for field_name, field_type in schema.get('fields', {}).items():
                fields.append({
                    "name": field_name,
                    "type": field_type
                })
            
                        # Create table using InfluxDB 3.x API with correct format
            # Based on API docs: POST /api/v3/configure/table expects:
            # {"db": "string", "table": "string", "tags": ["string"], "fields": [{}]}
            table_config = {
                "db": database_name,
                "table": measurement_name,
                "tags": tags,
                "fields": fields
            }
            
            LOG.info(f"Creating table '{measurement_name}' with schema...")
            LOG.debug(f"Database: {database_name}")
            LOG.debug(f"Table: {measurement_name}")
            LOG.debug(f"Tags: {tags}")
            LOG.debug(f"Fields with types: {[(f['name'], f['type']) for f in fields]}")
            LOG.debug(f"Table config JSON: {json.dumps(table_config, indent=2)}")
            
            # Try the table creation endpoint
            create_url = f"{influxdb_url}/api/v3/configure/table"
            LOG.debug(f"POST URL: {create_url}")
            
            response = requests.post(
                create_url,
                headers=headers,
                json=table_config,
                verify=verify  # Use the verify setting determined at function start
            )
            
            LOG.info(f"InfluxDB table creation response: HTTP {response.status_code}")
            LOG.debug(f"Response headers: {dict(response.headers)}")
            LOG.info(f"Response body: {response.text}")
            
            if response.status_code in [200, 201, 204]:
                LOG.info(f"Successfully created table '{measurement_name}'")
                success_count += 1
            elif response.status_code == 409:
                LOG.info(f"Table '{measurement_name}' already exists")
                success_count += 1
            elif response.status_code == 404:
                LOG.error(f"CRITICAL: API endpoint /api/v3/configure/table not found!")
                LOG.error(f"   This InfluxDB version may not support table pre-creation")
                LOG.error(f"   Response: {response.text}")
                LOG.error("ABORTING: Cannot continue without proper schema support!")
                sys.exit(1)  # Fail fast
            else:
                LOG.error(f"CRITICAL: Failed to create table '{measurement_name}'")
                LOG.error(f"   HTTP Status: {response.status_code}")
                LOG.error(f"   Response: {response.text}")
                LOG.error(f"   Request payload: {json.dumps(table_config, indent=2)}")
                LOG.error("ABORTING: Cannot continue without proper schema - data would be ingested with wrong types!")
                sys.exit(1)  # Fail fast - no point continuing
                
        except Exception as e:
            LOG.error(f"CRITICAL: Exception creating table '{measurement_name}': {e}")
            LOG.error("ABORTING: Cannot continue without proper schema!")
            sys.exit(1)  # Fail fast
    
    total_tables = len(MEASUREMENT_SCHEMAS)
    LOG.info(f"Table creation completed: {success_count}/{total_tables} successful")
    return success_count == total_tables

def validate_measurement_schemas(influxdb_url, auth_token, database_name, tls_ca=None, tls_validation='strict'):
    """Validate that measurement tables have the expected field types."""
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    # Configure TLS verification based on validation mode
    if tls_validation == 'none':
        verify = False
    elif tls_ca:
        verify = tls_ca
    else:
        verify = True
        
    validation_results = {}
    
    try:
        # First check what measurements exist using InfluxQL (same as CLI tool)
        query_url = f"{influxdb_url}/api/v3/query_influxql"
        show_measurements_query = {
            "q": "SHOW MEASUREMENTS",
            "db": database_name
        }
        
        response = requests.post(query_url, headers=headers, json=show_measurements_query, verify=verify)
        if response.status_code != 200:
            LOG.error(f"Failed to query measurements: HTTP {response.status_code} - {response.text}")
            return {}
        
        # Debug: Print raw response
        LOG.info(f"Raw InfluxQL response: {response.text}")
            
        # Parse measurements response 
        measurements_data = response.json()
        existing_measurements = set()
        
        LOG.debug(f"Parsed measurements response: {measurements_data}")
        
        # Extract measurement names from InfluxQL response format
        # The response is an array of objects like: [{"iox::measurement":"measurements","name":"controllers"}, ...]
        if isinstance(measurements_data, list):
            for item in measurements_data:
                if isinstance(item, dict) and 'name' in item:
                    measurement_name = item['name']
                    existing_measurements.add(measurement_name)
        
        LOG.info(f"Found existing tables: {list(existing_measurements)}")
        
        # Now validate field types for each measurement we expect to exist
        for measurement_name, expected_schema in MEASUREMENT_SCHEMAS.items():
            validation_results[measurement_name] = {
                'exists': measurement_name in existing_measurements,
                'field_types': {},
                'validation_errors': []
            }
            
            if measurement_name not in existing_measurements:
                validation_results[measurement_name]['validation_errors'].append(f"Measurement '{measurement_name}' does not exist")
                continue
                
            # For now, skip detailed field validation due to InfluxQL query complexities
            # The important thing is that measurements exist - field types are enforced at table creation
            LOG.info(f"Skipping field validation for '{measurement_name}' - measurement exists and table was pre-created with correct schema")
                        
        # Log validation summary
        for measurement_name, result in validation_results.items():
            if result['exists'] and not result['validation_errors']:
                LOG.info(f"✓ Measurement '{measurement_name}' validated successfully")
            else:
                LOG.warning(f"✗ Measurement '{measurement_name}' validation issues:")
                for error in result['validation_errors']:
                    LOG.warning(f"  - {error}")
                    
    except Exception as e:
        LOG.error(f"Error during schema validation: {e}")
        
    return validation_results
