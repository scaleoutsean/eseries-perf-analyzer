#!/usr/bin/env python3

# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

"""
Retrieves and collects data from the NetApp E-Series API server
and sends it to InfluxDB 3


"""
import argparse
import concurrent.futures
from datetime import datetime
import glob
from itertools import groupby
import json
import logging
import os
import sys
import time
import traceback
from urllib.parse import urlparse  # for parsing InfluxDB URL

import requests

from app.config import INFLUXDB_WRITE_PRECISION

# Import application modules
from app.config import Settings  # pydantic-based config
from app.connection import get_session
from app.controllers import get_controller
from app.diag import get_santricity, test_reachability
from app.events_collector import collect_major_event_log
from app.metrics_schemas import MEASUREMENT_SCHEMAS
from app.storage_collector import collect_storage_metrics
from app.symbols_collector import collect_symbol_stats
from app.system_state_collector import collect_system_state
from app.drives_collector import collect_drives_data
from app.controller_collector import collect_controller_data
from app.database_client import create_database_client
from app.database import create_measurement_tables, validate_measurement_schemas

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Collect E-Series metrics")

parser.add_argument('--config', type=str, default=None,
    help='Path to YAML or JSON config file. Overrides CLI and .env args if used.')
parser.add_argument('--api', '-u', '-p', nargs='+', default=[],
    help='List of E-Series API endpoints (IPv4 or IPv6 addresses or hostnames) to collect from. Use -u for username and -p for password inline, e.g., --api 10.0.0.1 -u admin -p secret. Overrides config file.')
parser.add_argument('--intervalTime', type=int, default=60,
    help='Collection interval in seconds (minimum 60). Determines how often metrics are collected or replayed.')
parser.add_argument('--influxdbUrl', type=str, default=None,
    help='InfluxDB server URL (overrides config file and .env if set). Example: https://db.example.com:8181')
parser.add_argument('--influxdbDatabase', type=str, default=None,
    help='InfluxDB database name (overrides config file and .env if set).')
parser.add_argument('--influxdbToken', type=str, default=None,
    help='InfluxDB authentication token (overrides config file and .env if set).')
parser.add_argument('--toJson', type=str, default=None,
    help='Directory to write collected metrics as JSON files (for offline replay or debugging).')
parser.add_argument('--fromJson', type=str, default=None,
    help='Directory to replay previously collected JSON metrics instead of live collection.')
parser.add_argument('--showReachability', action='store_true',
    help='Test reachability of SANtricity API endpoints and InfluxDB before collecting metrics.')
parser.add_argument('--tlsCa', type=str, default=None,
    help='Path to CA certificate for verifying API/InfluxDB TLS connections (if not in system trust store).')
parser.add_argument('--threads', type=int, default=4,
    help='Number of concurrent threads for metric collection. Default: 4. 4 or 8 is typical.')
parser.add_argument('--tlsValidation', type=str, choices=['strict', 'normal', 'none'], default='strict',
    help='TLS validation mode for SANtricity API: strict (require valid CA and SKI/AKI), normal (default Python validation), none (disable all TLS validation, INSECURE, for testing only). Default: strict.')
parser.add_argument('--showSantricity', action='store_true',
    help='Test SANtricity API endpoints independently of session creation and InfluxDB logic.')
parser.add_argument('--logfile', type=str, default=None,
    help='Path to log file. If not provided, logs to console only.')
parser.add_argument('--loglevel', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO',
    help='Log level for both console and file output. Default: INFO')
parser.add_argument('--maxIterations', type=int, default=0,
    help='Maximum number of collection iterations to run before exiting. Default: 0 (run indefinitely). Set to a positive integer to exit after that many iterations.')
parser.add_argument('--bootstrapInfluxDB', action='store_true',
    help='Bootstrap InfluxDB: create database if needed, create all measurement tables with proper schemas, validate, and report structure. Exits after completion.')

CMD = parser.parse_args()

# Configure logging with your preferred format
FORMAT = '%(asctime)s - %(levelname)s - %(funcName)s - %(lineno)d - %(message)s'
log_level = getattr(logging, CMD.loglevel.upper())

if CMD.logfile:
    # Configure file logging
    logging.basicConfig(filename=CMD.logfile, level=log_level,
                        format=FORMAT, datefmt='%Y-%m-%dT%H:%M:%SZ')
    logging.info('Logging to file: ' + CMD.logfile)
else:
    logging.basicConfig(level=log_level, format=FORMAT,
                        datefmt='%Y-%m-%dT%H:%M:%SZ')

# Configure external module log levels to match our log level
logging.getLogger("requests").setLevel(level=log_level)
logging.getLogger("urllib3").setLevel(level=log_level)
logging.getLogger("influxdb_client").setLevel(level=log_level)

# Initialize main logger after configuration
LOG = logging.getLogger(__name__)

if CMD.intervalTime < 60:
    print("Error: --intervalTime must be an integer set to at least 60 seconds.", file=sys.stderr)
    sys.exit(1)
if CMD.threads > 16:
    print(f"Warning: --threads is set to {CMD.threads}, which may be too high for a collector. 4 or 8 is typical for most environments. If your collection loops take more than 10 seconds, you may need more threads than that.", file=sys.stderr)
if CMD.maxIterations < 0:
    print("Error: --maxIterations must be a non-negative integer.", file=sys.stderr)
    sys.exit(1)
elif CMD.maxIterations > 0:
    LOG.info(f"Will run for {CMD.maxIterations} iterations and then exit")

NUMBER_OF_THREADS = CMD.threads


# Extract username and password from sys.argv if present
username = None
password = None
api_list = list(CMD.api) if CMD.api else []
if '-u' in sys.argv:
    try:
        idx = sys.argv.index('-u')
        username = sys.argv[idx + 1]
        if username in api_list:
            api_list.remove(username)
    except Exception:
        pass
if '-p' in sys.argv:
    try:
        idx = sys.argv.index('-p')
        password = sys.argv[idx + 1]
        if password in api_list:
            api_list.remove(password)
    except Exception:
        pass
if '-u' in api_list:
    api_list.remove('-u')
if '-p' in api_list:
    api_list.remove('-p')
CMD.api = api_list

# API endpoints precedence: CLI > config file
API_ENDPOINTS = api_list if api_list else []


# Always define InfluxDB variables, even if not used in --toJson mode
influxdb_url = None
influxdb_database = None
influxdb_auth_token = None
# Skip InfluxDB initialization if --showSantricity is provided
if CMD.showSantricity:
    LOG.info("Skipping InfluxDB initialization due to --showSantricity flag")
    influxdb_url = None
    influxdb_database = None
    influxdb_auth_token = None
    # Execute SANtricity diagnostic and exit
    # Using get_santricity imported at the top of the file
    get_santricity(CMD.api, username=username, password=password, tls_ca=CMD.tlsCa, tls_validation=CMD.tlsValidation)
    sys.exit(0)
else:
    # Only load InfluxDB config if needed:
    # - toJson: NO (API -> JSON files only)
    # - fromJson: YES (JSON files -> InfluxDB)
    # - regular collection: YES (API -> InfluxDB)
    # - diagnostic tests: NO (unless specific InfluxDB tests)
    need_influx = not (CMD.toJson or (CMD.showReachability and not CMD.influxdbUrl and not CMD.influxdbDatabase and not CMD.influxdbToken))
    # Using Settings imported at the top of the file
    settings = None
    if need_influx or not CMD.api:  # Load settings if we need config for API endpoints or InfluxDB
        settings = Settings(config_file=CMD.config, from_env=False)

    # Override CLI defaults only when not provided
    if not CMD.api and not CMD.fromJson:  # Don't require API endpoints when reading from JSON
        CMD.api = settings.api_endpoints or [] if settings else []
    if CMD.intervalTime == parser.get_default('intervalTime') and settings:
        CMD.intervalTime = settings.interval_time
    if CMD.intervalTime < 60:
        print("Error: interval_time in config must be at least 60 seconds.", file=sys.stderr)
        sys.exit(1)
    if CMD.tlsCa is None and settings:
        CMD.tlsCa = settings.tls_ca_path

    # Credentials precedence: CLI > config > env > prompt
    if not username and settings:
        username = settings.username
    if not password and settings:
        password = settings.password

    # Add password prompting as the FINAL fallback before Game Over
    # controller Docker service configuration would require `tty: true` to enable password prompting
    # We assume SANtricity administraor has set the password for, and uses built-in "monitor" account
    if not password:
        import getpass
        try:
            password = getpass.getpass(f"Enter password for SANtricity user '{username or 'monitor'}': ")
        except KeyboardInterrupt:
            print("\nPassword input cancelled.")
            sys.exit(1)
        if not password:
            print("Error: Password cannot be empty.")
            sys.exit(1)

    # InfluxDB configuration precedence: CLI > config > env > prompt
    influxdb_url = CMD.influxdbUrl if CMD.influxdbUrl else (settings.influxdb_url if settings else None)
    influxdb_database = CMD.influxdbDatabase if CMD.influxdbDatabase else (settings.influxdb_database if settings else None)
    influxdb_auth_token = CMD.influxdbToken if CMD.influxdbToken else (settings.influxdb_token if settings else None)

    # Prompt for InfluxDB token if needed and running interactively
    if not influxdb_auth_token and need_influx and sys.stdin.isatty():
        import getpass
        try:
            influxdb_auth_token = getpass.getpass("Enter InfluxDB authentication token: ")
        except KeyboardInterrupt:
            print("\nInfluxDB token input cancelled.")
            sys.exit(1)
        if not influxdb_auth_token:
            print("Error: InfluxDB token cannot be empty.")
            sys.exit(1)


#######################
# HELPER FUNCTIONS ####
#######################
# All imports have been moved to the top of the file
# Keeping diagnostic print statements for debugging purposes
print(f"[COLLECTOR DIAG] sys.path: {sys.path}")
print(f"[COLLECTOR DIAG] collect_storage_metrics.__module__ = {collect_storage_metrics.__module__}")

#######################
# MAIN FUNCTIONS ######
#######################


if __name__ == "__main__":
    # Check for bootstrap mode first
    if CMD.bootstrapInfluxDB:
        print("InfluxDB Bootstrap Mode")
        print("=" * 60)
        
        # Create centralized database client
        database_client = create_database_client(influxdb_url, influxdb_auth_token, influxdb_database, 
                                                CMD.tlsCa, CMD.tlsValidation)
        
        # Test InfluxDB connectivity
        print("Testing InfluxDB connectivity...")
        if not database_client.is_available():
            print("ERROR: Cannot connect to InfluxDB")
            sys.exit(1)
        print("InfluxDB connection successful")
        
        # Create measurement tables with proper field type schemas
        print("Creating measurement tables with proper field type schemas...")
        try:
            tables_success = create_measurement_tables(influxdb_url, influxdb_auth_token, influxdb_database)
            if tables_success:
                print("All measurement tables created successfully")
            else:
                print("Some measurement tables may not have been created")
        except Exception as e:
            print(f"ERROR: Failed to create tables: {e}")
            sys.exit(1)
        
        # Validate measurement schemas
        print("Validating measurement schemas...")
        try:
            validation_results = validate_measurement_schemas(influxdb_url, influxdb_auth_token, influxdb_database)
            if not validation_results:
                print("ERROR: Schema validation failed - could not query measurements")
                sys.exit(1)
            
            critical_measurements = ['drives', 'controllers', 'temp', 'power']
            validation_passed = True
            
            for measurement in critical_measurements:
                if measurement in validation_results:
                    result = validation_results[measurement]
                    if result['exists'] and not result['validation_errors']:
                        print(f"{measurement}: validated successfully")
                    else:
                        print(f"{measurement}: validation issues found")
                        for error in result['validation_errors']:
                            print(f"   - {error}")
                        validation_passed = False
                else:
                    print(f"{measurement}: not found in validation results")
                    validation_passed = False
            
            if validation_passed:
                print("All measurements validated successfully")
            else:
                print("Some measurements failed validation")

        except Exception as e:
            print(f"ERROR: Schema validation failed: {e}")
            sys.exit(1)
        
        # Report database structure
        print("Database Structure Report")
        print("-" * 40)
        
        try:
            # Show measurements
            print("MEASUREMENTS:")
            show_measurements_cmd = f'INFLUXDB3_HOST_URL="{influxdb_url}" INFLUXDB3_DATABASE_NAME="{influxdb_database}" INFLUXDB3_AUTH_TOKEN="{influxdb_auth_token}" /root/influxdb3-core-3.3.0/influxdb3 query --language influxql "SHOW MEASUREMENTS"'
            print(f"Command: {show_measurements_cmd}")
            
            # Show field keys for critical measurements
            for measurement in ['drives', 'controllers', 'temp', 'power']:
                print(f"\nFIELD KEYS for {measurement}:")
                show_fields_cmd = f'INFLUXDB3_HOST_URL="{influxdb_url}" INFLUXDB3_DATABASE_NAME="{influxdb_database}" INFLUXDB3_AUTH_TOKEN="{influxdb_auth_token}" /root/influxdb3-core-3.3.0/influxdb3 query --language influxql "SHOW FIELD KEYS FROM {measurement}"'
                print(f"Command: {show_fields_cmd}")
                
        except Exception as e:
            print(f"Could not generate structure report commands: {e}")

        print("Bootstrap completed successfully!")
        print("You can now run the collector normally to write data.")
        sys.exit(0)
    
    # Helper to ensure all collector results are lists of dicts
    def ensure_list_of_dicts(data):
        if not data:
            return []
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []
    
    # Create centralized database client for replay mode (if needed)
    database_client = create_database_client(influxdb_url, influxdb_auth_token, influxdb_database, 
                                            CMD.tlsCa, CMD.tlsValidation)
    
    # If --fromJson flag is provided, run replay logic and exit immediately
    if '--fromJson' in sys.argv:
        import glob
        import re
        # Helper to extract minute from filename
        def extract_minute_from_filename(filename):
            match = re.search(r'_(\d{8,})', filename)
            if match:
                try:
                    val = match.group(1)
                    if len(val) == 10:
                        return int(val) // 60
                    elif len(val) == 12:
                        dt = datetime.strptime(val, '%Y%m%d%H%M')
                        return int(dt.timestamp()) // 60
                except Exception:
                    pass
            return int(os.path.getmtime(filename)) // 60

        # Helper to extract timestamp from filename for InfluxDB (second precision)
        def extract_timestamp_from_filename(filename):
            match = re.search(r'_(\d{8,})', filename)
            if match:
                try:
                    val = match.group(1)
                    if len(val) == 10:
                        # Unix timestamp - already in seconds
                        return val
                    elif len(val) == 12:
                        # YYYYMMDDHHMM format - convert to unix timestamp
                        dt = datetime.strptime(val, '%Y%m%d%H%M')
                        return str(int(dt.timestamp()))
                except Exception:
                    pass
            # Fall back to file modification time (seconds)
            return str(int(os.path.getmtime(filename)))

        # Function to replay JSON files
        def replay_json_dir(json_dir):

            # Collect matching JSON files for all data types
            file_patterns = [
                os.path.join(json_dir, 'system_*.json'),
                os.path.join(json_dir, 'drive_*.json'),
                os.path.join(json_dir, 'drives_*.json'),
                os.path.join(json_dir, 'volume_*.json'),
                os.path.join(json_dir, 'interface_*.json'),
                os.path.join(json_dir, 'power_*.json'),
                os.path.join(json_dir, 'temp_*.json'),
                os.path.join(json_dir, 'mel_*.json'),
                os.path.join(json_dir, 'controller_*.json'),
                os.path.join(json_dir, 'storage_*.json'),  # Keep legacy patterns
            ]
            files = []
            for pat in file_patterns:
                found_files = glob.glob(pat)
                LOG.info(f"DEBUG: Pattern '{pat}' found {len(found_files)} files")
                if found_files:
                    LOG.info(f"DEBUG: First few files: {found_files[:3]}")
                files.extend(found_files)

            LOG.info(f"DEBUG: Total files found: {len(files)}")
            if not files:
                LOG.error(f"No JSON files found in {json_dir}")
                return

            files.sort(key=lambda f: (extract_minute_from_filename(f), f))

            LOG.info(f"DEBUG: First 5 sorted files: {files[:5]}")
            # Fix: Consume the group iterators immediately to avoid them being exhausted
            batches = [(minute, list(group)) for minute, group in groupby(files, key=extract_minute_from_filename)]
            total_batches = len(batches)
            LOG.info(f"DEBUG: Created {total_batches} batches from groupby")

            previous_minute = None

            for batch_num, (minute, batch) in enumerate(batches, 1):
                # batch is already a list of files
                # Convert minute back to readable timestamp
                readable_time = datetime.fromtimestamp(minute * 60).strftime('%Y-%m-%d %H:%M:%S')
                LOG.info(f"DEBUG-START: Processing batch {batch_num}, minute {minute}, previous_minute={previous_minute}")
                LOG.info(f"DEBUG-BATCH: Batch {batch_num} contains {len(batch)} files: {[os.path.basename(f) for f in batch[:3]]}")
                LOG.info(f"Replaying {len(batch)} records in batch {batch_num}/{total_batches} for minute {minute} ({readable_time}): {[os.path.basename(f) for f in batch]}")

                # Sleep if there's a time gap from the previous batch (and this isn't the first batch)
                if previous_minute is not None:
                    minute_gap = minute - previous_minute
                    LOG.info(f"DEBUG: Previous minute: {previous_minute}, Current minute: {minute}, Gap: {minute_gap}")
                    if minute_gap > 1:  # More than 1 minute gap
                        hours = minute_gap // 60
                        minutes = minute_gap % 60
                        if hours > 0 and minutes > 0:
                            gap_desc = f"{hours}h {minutes}m"
                        elif hours > 0:
                            gap_desc = f"{hours}h"
                        else:
                            gap_desc = f"{minutes}m"
                        LOG.info(f"Time gap detected: {gap_desc} between batches. Sleeping for {CMD.intervalTime}s to respect --intervalTime...")
                        time.sleep(CMD.intervalTime)
                    elif batch_num > 1:  # Consecutive minutes but not the first batch
                        LOG.info(f"Processing consecutive batch. Sleeping for {CMD.intervalTime}s to respect --intervalTime...")
                        time.sleep(CMD.intervalTime)

                previous_minute = minute

                for fname in batch:
                    with open(fname) as f:
                        try:
                            data = json.load(f)
                            if isinstance(data, dict):
                                data = [data]

                            # Extract timestamp from filename (second precision)
                            file_timestamp = extract_timestamp_from_filename(fname)

                            # Convert JSON data to InfluxDB Point format for InfluxDB3 client
                            records = []
                            for point in data:
                                if 'measurement' in point and 'fields' in point:
                                    measurement = point['measurement']
                                    tags = point.get('tags', {})
                                    fields = point['fields']
                                    # Use filename timestamp (second precision) for all data points
                                    timestamp = int(file_timestamp)

                                    # Create record dictionary for InfluxDB3 client
                                    record = {
                                        'measurement': measurement,
                                        'tags': tags,
                                        'fields': fields,
                                        'time': timestamp
                                    }
                                    records.append(record)

                            if records:
                                # Group records by measurement to handle mixed measurement files (e.g., storage files)
                                from collections import defaultdict
                                records_by_measurement = defaultdict(list)
                                for record in records:
                                    measurement_name = record.get('measurement', 'unknown')
                                    records_by_measurement[measurement_name].append(record)
                                
                                # Process each measurement group separately
                                for measurement_name, measurement_records in records_by_measurement.items():
                                    LOG.debug(f"Processing {len(measurement_records)} records for measurement '{measurement_name}' from {fname}")
                                    
                                    if measurement_name in MEASUREMENT_SCHEMAS:
                                        int_fields = {k for k, v in MEASUREMENT_SCHEMAS[measurement_name].get('fields', {}).items() if v.startswith('int')}
                                        field_types = {k: "int" for k in int_fields}
                                    else:
                                        field_types = {}

                                    # Use centralized database client with proper field types and precision
                                    if database_client is None:
                                        LOG.error(f"Database client not available, cannot write {fname}")
                                        continue

                                    # Write to InfluxDB and check return value
                                    write_success = database_client.write(measurement_records, measurement_name)
                                    if not write_success:
                                        LOG.error(f"Failed to replay {fname} ({measurement_name} measurement) - InfluxDB write failed")
                                
                                LOG.info(f"Successfully replayed {fname} ({len(records)} records)")
                            else:
                                LOG.warning(f"No valid data points found in {fname}")

                        except Exception as e:
                            LOG.error(f"Failed to replay {fname}: {e}")
                            continue
        # Check InfluxDB reachability using /health endpoint and actual write test
        # Note that reference docker-compose.yaml removes auth from /health endpoint
        # so that even users without auth can access it
        try:
            # Respect user's TLS validation setting
            verify_ssl = CMD.tlsValidation != 'none'
            verify_cert = CMD.tlsCa if verify_ssl and CMD.tlsCa else verify_ssl
            
            health_url = f"{influxdb_url}/health"
            response = requests.get(
                health_url,
                headers={"Authorization": f"Bearer {influxdb_auth_token}"},
                timeout=10,
                verify=verify_cert
            )
            if response.status_code != 200:
                LOG.error(f"InfluxDB /health check failed: HTTP {response.status_code} - {response.text}")
                sys.exit(1)

            # Test actual write capability using InfluxDB 3.x API
            write_url = f"{influxdb_url}/api/v3/write_lp?db={influxdb_database}"
            test_response = requests.post(
                write_url,
                headers={
                    "Authorization": f"Bearer {influxdb_auth_token}",
                    "Content-Type": "text/plain"
                },
                data=f"health_check,source=collector,test=true value=1 {int(time.time() * 1000000000)}",
                timeout=10,
                verify=verify_cert
            )
            if test_response.status_code not in [204, 200]:
                LOG.error(f"InfluxDB write test failed: HTTP {test_response.status_code} - {test_response.text}")
                sys.exit(1)

            LOG.info("InfluxDB is healthy and accepting writes for replay mode.")

            # Create measurement tables with proper field types before data insertion
            try:
                LOG.info("Creating measurement tables with proper field type schemas...")
                tables_success = create_measurement_tables(influxdb_url, influxdb_auth_token, influxdb_database)
                if tables_success:
                    LOG.info("All measurement tables created successfully")
                else:
                    LOG.warning("Some measurement tables may not have been created - continuing with validation")

                # Immediately validate the schemas we just created
                LOG.info("Validating measurement schemas...")
                validation_results = validate_measurement_schemas(influxdb_url, influxdb_auth_token, influxdb_database)

                # Check if validation passed for critical measurements
                critical_measurements = ['drives']  # Add more as needed
                validation_passed = True
                
                # If validation_results is empty, validation failed
                if not validation_results:
                    validation_passed = False
                    LOG.error("Schema validation failed - could not query measurements")
                else:
                    for measurement in critical_measurements:
                        if measurement in validation_results:
                            result = validation_results[measurement]
                            if not result['exists'] or result['validation_errors']:
                                validation_passed = False
                                LOG.error(f"Critical measurement '{measurement}' failed validation")

                if validation_passed:
                    LOG.info("Schema validation passed for all critical measurements")
                else:
                    LOG.error("Schema validation failed - cannot continue with invalid schemas")
                    LOG.error("All write operations would fail - exiting to prevent wasted processing")
                    sys.exit(1)

            except ImportError as e:
                LOG.warning(f"Database module not available: {e} - skipping table creation")
            except Exception as e:
                LOG.warning(f"Error creating/validating tables: {e} - continuing with replay")

            LOG.info("Starting JSON replay from directory: " + CMD.fromJson)
            replay_json_dir(CMD.fromJson)
            LOG.info("JSON replay completed successfully.")
            sys.exit(0)
        except Exception as e:
            LOG.error(f"Failed during JSON replay health check: {e}")
            import traceback
            LOG.error(f"Traceback: {traceback.format_exc()}")
            sys.exit(1)

# Initialize loop counter - will be incremented at the end of each collection cycle
    loopIteration = 1
    executor = concurrent.futures.ThreadPoolExecutor(NUMBER_OF_THREADS)

    # Get session with dual-controller support
    SESSION, access_token, active_endpoint = get_session(username, password, CMD.api, tls_ca=CMD.tlsCa, tls_validation=CMD.tlsValidation)
    # --- SANtricity API authentication ---
    if not access_token:
        LOG.error("Failed to obtain any authentication method from SANtricity API. Aborting collection.")
        sys.exit(1)

    LOG.info(f"Active controller endpoint: {active_endpoint}")

    # Set up headers based on authentication type
    if access_token == "BASIC_AUTH":
        import base64
        userpass = f"{username}:{password}"
        b64 = base64.b64encode(userpass.encode()).decode()
        san_headers = {"Authorization": f"Basic {b64}"}
        LOG.info("Using Basic Authentication for API calls")
    else:
        san_headers = {"Authorization": f"Bearer {access_token}"}
        LOG.info("Using Bearer Token authentication for API calls")

    # Use the active endpoint for controller functions
    active_api_list = [active_endpoint.replace('https://', '').replace(':8443', '')]

    # Auto-detect system WWN and name via API (always use system ID '1' for single-system arrays)
    try:
        LOG.info("Auto-detecting system WWN and name via API")
        resp = SESSION.get(f"{get_controller('sys', active_api_list)}/1", headers=san_headers)
        resp.raise_for_status()
        data = resp.json()
        sys_id = data.get("wwn")
        sys_name = data.get("name")

        # Mandate WWN - it's essential for proper system identification
        if not sys_id:
            LOG.error("Unable to retrieve WWN from system - WWN is mandatory for proper metrics collection")
            sys.exit(1)

        LOG.info("Detected system: WWN=%s, Name=%s", sys_id, sys_name)
    except Exception as e:
        LOG.error("Failed to auto-detect system WWN: %s", e)
        sys.exit(1)

    # test reachability of SANtricity API and InfluxDB
    # API_ENDPOINTS should already be set from configuration above
    # API_ENDPOINTS = CMD.api if hasattr(CMD, 'api') else []
    if CMD.showReachability and not CMD.fromJson:
        # Only test InfluxDB if config is present, otherwise just test API
        if influxdb_url and influxdb_auth_token:
            test_reachability(API_ENDPOINTS, influxdb_url, influxdb_auth_token, CMD.tlsCa, CMD.tlsValidation, username, password)
        else:
            LOG.info("No InfluxDB config provided, only testing SANtricity API reachability...")
            test_reachability(API_ENDPOINTS, None, None, CMD.tlsCa, CMD.tlsValidation, username, password)

    if not CMD.toJson and not CMD.fromJson:
        # standard mode: check reachability
        try:
            if influxdb_url and influxdb_auth_token:
                test_reachability(API_ENDPOINTS, influxdb_url, influxdb_auth_token, CMD.tlsCa, CMD.tlsValidation, username, password)
            else:
                LOG.info("No InfluxDB config provided, only testing SANtricity API reachability...")
                test_reachability(API_ENDPOINTS, None, None, CMD.tlsCa, CMD.tlsValidation, username, password)
        except Exception as e:
            LOG.error(
                "Failed to connect to InfluxDB (host %s, database %s): %s",
                influxdb_url, influxdb_database, e
            )
            sys.exit(1)
    elif CMD.toJson and not CMD.fromJson:
        # JSON output mode: test write permissions to output directory
        LOG.info("JSON output mode - testing write permissions to %s", CMD.toJson)
        outdir = CMD.toJson
        if not os.access(outdir, os.W_OK):
            LOG.error("No write permissions to directory %s", outdir)
            sys.exit(1)
        try:
            os.makedirs(outdir, exist_ok=True)
            os.chmod(outdir, 0o777)
            LOG.info("Write permissions to directory OK")
        except OSError as e:
            LOG.error("Error creating directory %s: %s", outdir, e)
            sys.exit(1)
    # else: replay mode (fromJson) skips both reachability and write tests

    # Ensure toJson is always present as an attribute for all collector functions
    if not hasattr(CMD, 'toJson'):
        CMD.toJson = None
    checksums = {}
    # Parse influxdb_url into host and port for collect_storage_metrics
    from urllib.parse import urlparse
    parsed = urlparse(influxdb_url) if influxdb_url else None
    influx_host = parsed.hostname if parsed else None
    influx_port = parsed.port if parsed and parsed.port else (443 if parsed and parsed.scheme == 'https' else 80)

    # Create centralized database client
    database_client = create_database_client(influxdb_url, influxdb_auth_token, influxdb_database,
                                            CMD.tlsCa, CMD.tlsValidation)
    if database_client:
        LOG.info(f"Created centralized database client")

        # For regular collection mode (not toJson), ensure database exists
        if not CMD.toJson:
            try:
                # Check if database exists using InfluxDB 3.x API
                headers = {
                    'Authorization': f'Bearer {influxdb_auth_token}',
                    'Accept': 'application/json'
                }

                # GET existing databases
                get_url = f"{influxdb_url}/api/v3/configure/database?format=json"
                response = requests.get(get_url, headers=headers, timeout=10)

                if response.status_code == 200:
                    databases_data = response.json()
                    databases = databases_data.get('databases', [])

                    if influxdb_database not in databases:
                        LOG.info(f"Database '{influxdb_database}' does not exist, creating it")

                        # POST to create database
                        create_url = f"{influxdb_url}/api/v3/configure/database"
                        create_data = {"db": influxdb_database}
                        create_response = requests.post(create_url, json=create_data, headers=headers, timeout=10)

                        if create_response.status_code in [200, 201, 204]:
                            LOG.info(f"Successfully created database '{influxdb_database}'")
                        else:
                            LOG.error(f"Failed to create database '{influxdb_database}': HTTP {create_response.status_code}")
                            LOG.error(f"Response: {create_response.text}")
                    else:
                        LOG.info(f"Database '{influxdb_database}' already exists")
                else:
                    LOG.error(f"Failed to check database existence: HTTP {response.status_code}")
                    LOG.error(f"Response: {response.text}")

            except Exception as db_check_error:
                # If database check fails, still proceed - InfluxDB 3.x will create on first write
                LOG.info(f"Could not verify database existence (will be created on first write): {db_check_error}")

    # Helper to robustly write JSON output, even if data is empty
    def write_json_output(data, fname):
        try:
            with open(fname, 'w') as f:
                json.dump(data if data else [], f, indent=2)
            LOG.info(f"Wrote {len(data) if data else 0} points to {fname}")
        except Exception as e:
            LOG.error(f"Failed to write {fname}: {e}")

    # Helper to execute collector functions with resilient error handling
    def execute_collector_safely(executor, collector_name, collector_func, *args):
        """
        Execute a collector function with error handling for older arrays.
        Returns empty list if collector fails, allowing the loop to continue.
        """
        try:
            LOG.info(f"Starting {collector_name} collector...")
            future = executor.submit(collector_func, *args)
            result = future.result()
            LOG.info(f"DEBUG: {collector_name} task finished successfully")
            return ensure_list_of_dicts(result)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                LOG.warning(f"[{collector_name}] API endpoint not found (HTTP 404) - likely unsupported on this array version. Skipping.")
            else:
                LOG.warning(f"[{collector_name}] HTTP error {e.response.status_code}: {e}. Continuing with next collector.")
            return []
        except requests.exceptions.ConnectionError as e:
            LOG.warning(f"[{collector_name}] Connection error: {e}. Continuing with next collector.")
            return []
        except Exception as e:
            LOG.warning(f"[{collector_name}] Unexpected error: {e}. Continuing with next collector.")
            return []

    while True:
        time_start = round(time.time(), 4)
        LOG.info(f"Starting collection iteration {loopIteration} of {CMD.maxIterations if CMD.maxIterations > 0 else 'unlimited'}")

        # First check API connectivity and get system info
        sys_info = None
        try:
            response = SESSION.get(get_controller("sys", active_api_list), headers=san_headers)
            if response.status_code != 200:
                LOG.warning(
                    f"Unable to connect to storage-system API endpoint! Status-code={response.status_code}")
                # Don't continue this iteration if we can't connect to the API
                raise Exception(f"Unable to connect to storage-system API endpoint! Status-code={response.status_code}")

            # Re-fetch the system WWN with each loop iteration to ensure consistency
            # This is critical for proper file naming across multiple collections
            resp = SESSION.get(f"{get_controller('sys', active_api_list)}/1", headers=san_headers)
            resp.raise_for_status()
            data = resp.json()
            current_wwn = data.get("wwn")
            current_name = data.get("name")

            # Validate that we have a WWN for this iteration
            if not current_wwn:
                LOG.error(f"Unable to retrieve WWN in loop {loopIteration} - WWN is mandatory for proper metrics collection")
                raise Exception(f"Failed to retrieve WWN for system")

            # Update sys_id with the freshly retrieved WWN for this iteration
            LOG.info(f"Loop {loopIteration}: Using WWN={current_wwn}, Name={current_name}")
            sys_id = current_wwn
            sys_name = current_name

            sys_info = {'name': current_name, 'wwn': current_wwn}

            # Now do the actual collection
            try:
                # Dispatch storage metrics collector
                result = execute_collector_safely(
                    executor,
                    "collect_storage_metrics",
                    collect_storage_metrics,
                    sys_info,
                    SESSION,
                    san_headers,
                    active_api_list,
                    influx_host,
                    influx_port,
                    influxdb_database,
                    influxdb_auth_token,
                    CMD,
                    loopIteration)
                # No need to write here - collect_storage_metrics already writes to file when CMD.toJson is set

                # Dispatch system state collector
                result = execute_collector_safely(
                    executor,
                    "collect_system_state",
                    collect_system_state,
                    sys_info,
                    checksums,
                    SESSION,
                    san_headers,
                    active_api_list,
                    influx_host,
                    influx_port,
                    influxdb_database,
                    influxdb_auth_token,
                    CMD,
                    database_client)
                # No need to write here - collect_system_state already writes to file when CMD.toJson is set

                # Dispatch major event log collector
                result = execute_collector_safely(
                    executor,
                    "collect_major_event_log",
                    collect_major_event_log,
                    sys_info,
                    SESSION,
                    san_headers,
                    active_api_list,
                    influx_host,
                    influx_port,
                    influxdb_database,
                    influxdb_auth_token,
                    CMD,
                    checksums,
                    database_client)
                # No need to write here - collect_major_event_log already writes to file when CMD.toJson is set

                # Dispatch symbol stats collector
                result = execute_collector_safely(
                    executor,
                    "collect_symbol_stats",
                    collect_symbol_stats,
                    sys_info,
                    SESSION,
                    san_headers,
                    active_api_list,
                    database_client,
                    influxdb_database,
                    CMD,
                    loopIteration)
                # No need to write here - collect_symbol_stats already writes to file when CMD.toJson is set

                # Dispatch drives collector (runs at a lower frequency)
                result = execute_collector_safely(
                    executor,
                    "collect_drives_data",
                    collect_drives_data,
                    sys_info,
                    SESSION,
                    san_headers,
                    active_api_list,
                    database_client,
                    influxdb_database,
                    CMD,
                    loopIteration,
                    influxdb_url,
                    influxdb_auth_token)
                # No need to write here - collect_drives_data already writes to file when CMD.toJson is set

                # Dispatch controller collector (runs at a lower frequency, only if multiple controllers)
                result = execute_collector_safely(
                    executor,
                    "collect_controller_data",
                    collect_controller_data,
                    sys_info,
                    SESSION,
                    san_headers,
                    API_ENDPOINTS,      # Pass ALL endpoints, not just active one
                    database_client,
                    influxdb_database,
                    CMD,
                    loopIteration,
                    influxdb_url,
                    influxdb_auth_token,
                    username,
                    password,
                    CMD.tlsValidation,
                    CMD.tlsCa,
                    active_endpoint,    # main_controller_endpoint
                    access_token)       # main_controller_token
                # No need to write here - collect_controller_data already writes to file when CMD.toJson is set

            except Exception as coll_e:
                LOG.error(f"Exception during metrics collection: {coll_e}")

        except requests.exceptions.HTTPError as e:
            LOG.warning(f"Unable to connect to the API! {e}")
        except requests.exceptions.ConnectionError as e:
            LOG.warning(f"Unable to connect to the API! {e}")
        except Exception as e:
            LOG.warning(f"Unexpected exception! {e}")

        # Start of collection loop

        # Dispatch storage metrics collector
        result = execute_collector_safely(
            executor,
            "collect_storage_metrics",
            collect_storage_metrics,
            sys_info,
            SESSION,
            san_headers,
            active_api_list,
            influx_host,
            influx_port,
            influxdb_database,
            influxdb_auth_token,
            CMD,
            loopIteration)
        # No need to write here - collect_storage_metrics already writes to file when CMD.toJson is set

        # Dispatch system state collector
        result = execute_collector_safely(
            executor,
            "collect_system_state",
            collect_system_state,
            sys_info,
            checksums,
            SESSION,
            san_headers,
            active_api_list,
            influx_host,
            influx_port,
            influxdb_database,
            influxdb_auth_token,
            CMD,
            database_client)
        # No need to write here - collect_system_state already writes to file when CMD.toJson is set

        # Dispatch major event log collector
        result = execute_collector_safely(
            executor,
                "collect_major_event_log",
                collect_major_event_log,
                sys_info,
                SESSION,
                san_headers,
                active_api_list,
                influx_host,
                influx_port,
                influxdb_database,
                influxdb_auth_token,
                CMD,
                checksums)
        # No need to write here - collect_major_event_log already writes to file when CMD.toJson is set

        # Dispatch symbol stats collector
        result = execute_collector_safely(
            executor,
            "collect_symbol_stats",
            collect_symbol_stats,
            sys_info,
            SESSION,
            san_headers,
            active_api_list,
            influx_host,
            influx_port,
            influxdb_database,
            influxdb_auth_token,
            CMD,
            loopIteration)
        # No need to write here - collect_symbol_stats already writes to file when CMD.toJson is set

        # If in toJson mode and this is the first iteration, collect firmware information
        if CMD.toJson and loopIteration == 1:
            LOG.info(f"First iteration in toJson mode - collecting firmware information to directory: {CMD.toJson}")
            LOG.info(f"toJson directory exists: {os.path.exists(CMD.toJson)}")
            LOG.info(f"toJson directory is writable: {os.access(CMD.toJson, os.W_OK)}")
            LOG.info(f"API_ENDPOINTS: {API_ENDPOINTS}")

            try:
                # Use get_santricity imported at the top of the file
                LOG.info("Using get_santricity imported at the top of the file")

                # For each API endpoint (array), get firmware information and save to JSON
                for api in API_ENDPOINTS:
                    try:
                        LOG.info(f"Collecting firmware information for {api}")
                        LOG.info(f"Parameters: username={username}, tls_validation={CMD.tlsValidation}, tls_ca={CMD.tlsCa}, to_json=True, json_dir={CMD.toJson}")

                        # Call get_santricity with toJson=True to save config files
                        fw_info = get_santricity([api], username=username, password=password,
                                      tls_validation=CMD.tlsValidation, tls_ca=CMD.tlsCa,
                                      to_json=True, json_dir=CMD.toJson)

                        LOG.info(f"get_santricity returned: {len(fw_info) if fw_info else 'None'} system entries")

                        # Check if config files were created
                        for sys_id in fw_info:
                            config_path = os.path.join(CMD.toJson, f"config_{sys_id}.json")
                            if os.path.exists(config_path):
                                LOG.info(f"Verified config file exists: {config_path}")
                            else:
                                LOG.warning(f"Config file was not created: {config_path}")
                    except Exception as e:
                        LOG.warning(f"Error collecting firmware information for {api}: {e}")
                        LOG.warning(f"Exception details: {type(e).__name__}: {str(e)}")
                        import traceback
                        LOG.warning(f"Traceback: {traceback.format_exc()}")
            except Exception as e:
                LOG.warning(f"Failed to collect firmware information: {e}")
                LOG.warning(f"Exception details: {type(e).__name__}: {str(e)}")
                import traceback
                LOG.warning(f"Traceback: {traceback.format_exc()}")

        # Complete the iteration
        time_end = round(time.time(), 4)
        elapsed = time_end - time_start

        # Increment loop counter
        loopIteration += 1
        LOG.info(f"Completed collection iteration {loopIteration-1}")

        # Check if we've reached the maximum number of iterations
        if CMD.maxIterations > 0 and loopIteration > CMD.maxIterations:
            LOG.info(f"Reached maximum number of iterations ({CMD.maxIterations}). Exiting gracefully.")
            break

        # Sleep for the remaining interval time
        if elapsed < CMD.intervalTime:
            LOG.info(f"Sleeping for {CMD.intervalTime - elapsed:.2f} seconds until next collection")
            time.sleep(CMD.intervalTime - elapsed)
