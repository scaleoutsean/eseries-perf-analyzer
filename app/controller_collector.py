# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import json
import logging
import os
import time
from datetime import datetime, timezone
from app.utils import get_json_output_path
from app.metrics_config import CONTROLLER_FIELDS_EXCLUDED

LOG = logging.getLogger(__name__)

# Get configuration
try:
    from app.config import EnvConfig
    CONTROLLER_COLLECTION_INTERVAL = EnvConfig().CONTROLLER_COLLECTION_INTERVAL
    DEFAULT_TLS_VALIDATION = EnvConfig().TLS_VALIDATION
except Exception:
    # Fallback to default if config import fails
    CONTROLLER_COLLECTION_INTERVAL = 3600  # 1 hour in seconds
    DEFAULT_TLS_VALIDATION = "strict"  # Match config.py default

# Track last collection time globally
LAST_COLLECTION_TIME = 0

def get_controller_token(controller_ip, username, password, tls_validation=None, tls_ca=None):
    """
    Get a fresh Bearer token specifically for a controller.
    
    :param controller_ip: IP address of the controller
    :param username: SANtricity username
    :param password: SANtricity password
    :param tls_validation: TLS validation mode (None to use config default)
    :param tls_ca: TLS CA certificate path
    :return: Bearer token string or None if failed
    """
    # Use config default if not specified
    if tls_validation is None:
        tls_validation = DEFAULT_TLS_VALIDATION
        
    print(f"[CONTROLLER_COLLECTOR DIAG] get_controller_token called with tls_validation='{tls_validation}', tls_ca='{tls_ca}'")
    LOG.info(f"[CONTROLLER_COLLECTOR] get_controller_token called with tls_validation='{tls_validation}', tls_ca='{tls_ca}'")
    
    try:
        import requests
        from requests.auth import HTTPBasicAuth
        
        # Set up SSL verification
        verify_ssl = True
        if tls_validation == 'none':
            verify_ssl = False
            print(f"[CONTROLLER_COLLECTOR DIAG] TLS validation disabled, verify_ssl={verify_ssl}")
        elif tls_ca and os.path.exists(tls_ca):
            verify_ssl = tls_ca
            print(f"[CONTROLLER_COLLECTOR DIAG] Using custom CA: {tls_ca}")
        else:
            print(f"[CONTROLLER_COLLECTOR DIAG] Using strict TLS validation")
            
        url = f"https://{controller_ip}:8443/devmgr/v2/access-token"
        payload = {"duration": 3600}  # Request 1 hour token
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            auth=HTTPBasicAuth(username, password),
            verify=verify_ssl,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("accessToken")
            if token:
                LOG.info(f"[CONTROLLER_COLLECTOR] Got fresh token for controller {controller_ip}")
                return token
                
        LOG.warning(f"[CONTROLLER_COLLECTOR] Failed to get token from {controller_ip}: {response.status_code}")
        return None
        
    except Exception as e:
        LOG.warning(f"[CONTROLLER_COLLECTOR] Exception getting token from {controller_ip}: {e}")
        return None

def collect_controller_data(sys_info, session, san_headers, api_endpoints, 
                           database_client, db_name, flags, loop_iteration, 
                           influxdb_url=None, auth_token=None, username=None, 
                           password=None, tls_validation=None, tls_ca=None, 
                           main_controller_endpoint=None, main_controller_token=None):
    """
    Collects controller-specific performance metrics from E-Series controllers.
    This function runs at a lower frequency than normal metric collection.
    Uses just-in-time authentication to get fresh tokens for each controller.
    
    :param sys_info: dict with 'wwn' and 'name'
    :param session: HTTP session for API calls (used for SSL settings)
    :param san_headers: Headers for SANtricity API requests (not used for controller-specific calls)
    :param api_endpoints: list of SANtricity API endpoints
    :param database_client: DatabaseClient instance for writing to InfluxDB
    :param db_name: InfluxDB database name
    :param flags: command flags
    :param loop_iteration: current iteration count
    :param influxdb_url: InfluxDB URL for HTTP API
    :param auth_token: InfluxDB auth token
    :param username: SANtricity username for authentication
    :param password: SANtricity password for authentication  
    :param tls_validation: TLS validation mode (None to use config default)
    :param tls_ca: TLS CA certificate path
    :param main_controller_endpoint: IP/FQDN of controller used by main collector (to reuse token)
    :param main_controller_token: Bearer token from main collector session (to avoid re-auth)
    """
    global LAST_COLLECTION_TIME
    
    # Use config default if not specified
    if tls_validation is None:
        tls_validation = DEFAULT_TLS_VALIDATION
    
    print(f"[CONTROLLER_COLLECTOR DIAG] Entered collect_controller_data, iteration {loop_iteration}")
    LOG.info(f"[CONTROLLER_COLLECTOR] Entered collect_controller_data, iteration {loop_iteration}")
    
    # Strict output mode: either JSON or InfluxDB, never both
    to_json = getattr(flags, 'toJson', None)
    
    # Mandate WWN - it's essential for proper system identification
    if 'wwn' not in sys_info or not sys_info['wwn']:
        print("[CONTROLLER_COLLECTOR DIAG] ERROR: Missing or empty WWN in system info")
        LOG.error("[CONTROLLER_COLLECTOR] Missing or empty WWN in system info. WWN is mandatory for proper metrics collection.")
        return []
        
    # Get system identifiers
    sys_id = sys_info['wwn']
    sys_name = sys_info.get('name', 'unknown')
    print(f"[CONTROLLER_COLLECTOR DIAG] Processing system {sys_name} (WWN: {sys_id})")
    LOG.info(f"[CONTROLLER_COLLECTOR] Processing system {sys_name} (WWN: {sys_id})")
    
    # Check if we should collect based on iteration timing
    # Controller collection should happen much less frequently than regular metrics
    current_time = int(time.time())
    
    print(f"[CONTROLLER_COLLECTOR DIAG] Time check: current={current_time}, interval={CONTROLLER_COLLECTION_INTERVAL}, iteration={loop_iteration}")
    print(f"[CONTROLLER_COLLECTOR DIAG] Flags available: intervalTime={getattr(flags, 'intervalTime', 'NOT_FOUND')}, maxIterations={getattr(flags, 'maxIterations', 'NOT_FOUND')}")
    
    # Handle None loop_iteration gracefully (treat as first iteration)
    iteration_num = loop_iteration if loop_iteration is not None else 1
    
    # Simple logic: collect controllers on first iteration, then based on time intervals
    # If CONTROLLER_COLLECTION_INTERVAL <= intervalTime, collect every iteration
    # Otherwise, collect every N iterations where N = CONTROLLER_COLLECTION_INTERVAL / intervalTime
    if iteration_num == 1:
        print(f"[CONTROLLER_COLLECTOR DIAG] PROCEEDING: First iteration - collecting controllers")
    else:
        # For subsequent iterations, check if enough iterations have passed
        # Get actual intervalTime from flags instead of hardcoding
        interval_time = getattr(flags, 'intervalTime', 60)  # Use actual interval or 60 as fallback
        iterations_per_controller_collection = max(1, CONTROLLER_COLLECTION_INTERVAL // interval_time)
        
        if (iteration_num - 1) % iterations_per_controller_collection == 0:
            print(f"[CONTROLLER_COLLECTOR DIAG] PROCEEDING: Time interval reached - "
                  f"iteration {iteration_num}, collecting every {iterations_per_controller_collection} "
                  f"iterations (interval_time={interval_time})")
        else:
            print(f"[CONTROLLER_COLLECTOR DIAG] SKIPPING: Not time yet - "
                  f"iteration {iteration_num}, collecting every {iterations_per_controller_collection} "
                  f"iterations (interval_time={interval_time})")
            LOG.info(f"[CONTROLLER_COLLECTOR] Skipping controller collection. "
                     f"Will collect every {iterations_per_controller_collection} iterations")
            return []
    
    LOG.info(f"[CONTROLLER_COLLECTOR] Starting controller collection (interval: {CONTROLLER_COLLECTION_INTERVAL} seconds, iteration: {iteration_num})")
    
    # Check if we have any API endpoints available (modified from original 2+ requirement)
    if not api_endpoints or len(api_endpoints) < 1:
        print(f"[CONTROLLER_COLLECTOR DIAG] SKIPPING: No API endpoints available: {api_endpoints}")
        LOG.info("[CONTROLLER_COLLECTOR] No API endpoints available, skipping controller collection")
        return []
    
    print(f"[CONTROLLER_COLLECTOR DIAG] PROCEEDING: {len(api_endpoints)} API endpoints available: {api_endpoints}")
    print(f"[CONTROLLER_COLLECTOR DIAG] Main controller endpoint: {main_controller_endpoint}")
    print(f"[CONTROLLER_COLLECTOR DIAG] Main controller token available: {bool(main_controller_token)}")
    
    json_body = []
    controllers_collected = 0
    
    # Iterate through all available API endpoints to get controller-specific data
    print(f"[CONTROLLER_COLLECTOR DIAG] STARTING LOOP: Will iterate through {len(api_endpoints)} endpoints")
    for i, api_endpoint in enumerate(api_endpoints):
        print(f"[CONTROLLER_COLLECTOR DIAG] LOOP ITERATION {i+1}/{len(api_endpoints)}: Processing {api_endpoint}")
        try:
            LOG.info(f"[CONTROLLER_COLLECTOR] Collecting from controller at {api_endpoint}")
            
            # Check if this is the main controller (reuse existing token) or other controller (use JIT auth)
            if api_endpoint == main_controller_endpoint and main_controller_token and main_controller_token != "BASIC_AUTH":
                print(f"[CONTROLLER_COLLECTOR DIAG] REUSING TOKEN: {api_endpoint} is main controller, reusing existing Bearer token")
                LOG.info(f"[CONTROLLER_COLLECTOR] AUTH: Reusing main controller token for {api_endpoint}")
                controller_token = main_controller_token
                auth_method = "Bearer"
            else:
                if main_controller_token == "BASIC_AUTH":
                    print(f"[CONTROLLER_COLLECTOR DIAG] BASIC AUTH SYSTEM: {api_endpoint} - main collector uses Basic Auth, trying Basic Auth for controller stats")
                    LOG.info(f"[CONTROLLER_COLLECTOR] AUTH: Main collector uses Basic Auth, trying Basic Auth for {api_endpoint}")
                    controller_token = "BASIC_AUTH"
                    auth_method = "Basic"
                else:
                    print(f"[CONTROLLER_COLLECTOR DIAG] JIT AUTH: {api_endpoint} is other controller, performing just-in-time authentication")
                    LOG.info(f"[CONTROLLER_COLLECTOR] AUTH: Performing just-in-time auth for {api_endpoint}")
                    # Get fresh Bearer token specifically for this controller
                    controller_token = get_controller_token(api_endpoint, username, password, 
                                                          tls_validation, tls_ca)
                    if controller_token:
                        auth_method = "Bearer"
                    else:
                        print(f"[CONTROLLER_COLLECTOR DIAG] FALLBACK: Bearer token failed for {api_endpoint}, trying Basic Auth")
                        LOG.info(f"[CONTROLLER_COLLECTOR] FALLBACK: Bearer token failed for {api_endpoint}, trying Basic Auth")
                        controller_token = "BASIC_AUTH"
                        auth_method = "Basic"
            
            if not controller_token:
                print(f"[CONTROLLER_COLLECTOR DIAG] AUTH FAILED: {api_endpoint} authentication failed, skipping")
                LOG.warning(f"[CONTROLLER_COLLECTOR] AUTH FAILED: {api_endpoint} authentication failed, skipping")
                continue
            print(f"[CONTROLLER_COLLECTOR DIAG] AUTH SUCCESS: {api_endpoint} authenticated successfully using {auth_method} auth")
            
            # Create controller-specific headers based on auth method
            if auth_method == "Basic":
                import base64
                userpass = f"{username}:{password}"
                b64 = base64.b64encode(userpass.encode()).decode()
                controller_headers = {"Authorization": f"Basic {b64}"}
                print(f"[CONTROLLER_COLLECTOR DIAG] Using Basic Auth headers for {api_endpoint}")
            else:
                controller_headers = {"Authorization": f"Bearer {controller_token}"}
                print(f"[CONTROLLER_COLLECTOR DIAG] Using Bearer token headers for {api_endpoint}")
            
            # Create a new session for this controller, copying SSL settings from main session
            controller_session = session.__class__()
            controller_session.headers.update(controller_headers)
            # Copy SSL verification settings from the main session
            controller_session.verify = session.verify
            if hasattr(session, 'cert') and session.cert:
                controller_session.cert = session.cert
            
            # Build controller-specific base URL
            controller_base = f"https://{api_endpoint}:8443/devmgr/v2/storage-systems"
            
            # Get controller statistics using the new analyzed API endpoint
            # Use statisticsFetchTime as required by the API method, 600 seconds should get us 2-3 samples
            controller_url = f"{controller_base}/{sys_id}/analyzed/controller-statistics?statisticsFetchTime=600"
            LOG.debug(f"[CONTROLLER_COLLECTOR] GET {controller_url}")
            
            response = controller_session.get(controller_url, timeout=30)
            
            if response.status_code != 200:
                LOG.warning(f"[CONTROLLER_COLLECTOR] Failed to get controller stats from {api_endpoint}: {response.status_code}")
                continue
                
            controller_data = response.json()
            
            # Extract statistics array from the new API response structure
            if not controller_data or 'statistics' not in controller_data:
                LOG.warning(f"[CONTROLLER_COLLECTOR] No statistics data in controller response from {api_endpoint}")
                continue
                
            statistics = controller_data['statistics']
            if not statistics:
                LOG.warning(f"[CONTROLLER_COLLECTOR] Empty statistics array from controller {api_endpoint}")
                continue
            
            # Take the first statistic entry (and discard others if any)
            controller_stat = statistics[0]
            LOG.info(f"[CONTROLLER_COLLECTOR] Got controller statistics from {api_endpoint}, using first of {len(statistics)} entries")
            
            # Create point for this controller
            timestamp = datetime.now(timezone.utc)
            
            # Build tags for this controller
            tags = {
                "system_id": sys_id,
                "system_name": sys_name,
                "controller_endpoint": api_endpoint,
            }
            
            # Add controller ID fields as tags if available
            for id_field in ['controllerId', 'sourceController']:
                if id_field in controller_stat:
                    tags[id_field] = controller_stat[id_field]
            
            # Extract fields from CONTROLLER_PARAMS or all numeric fields
            fields = {}
            for key, value in controller_stat.items():
                if key in ['controllerId', 'sourceController', 'observedTime', 'observedTimeInMS']:
                    continue  # Skip ID fields and timestamps (already in tags or metadata)
                if isinstance(value, (int, float)) and value is not None:
                    fields[key] = value
                elif isinstance(value, list) and all(isinstance(x, (int, float)) for x in value):
                    # Handle array fields like maxCpuUtilizationPerCore
                    json_field_name = f"{key}_json"
                    if json_field_name not in CONTROLLER_FIELDS_EXCLUDED:
                        fields[json_field_name] = json.dumps(value)
            
            point = {
                'measurement': 'controllers',
                'tags': tags,
                'fields': fields,
                'time': timestamp
            }
            
            json_body.append(point)
            controllers_collected += 1
            
            print(f"[CONTROLLER_COLLECTOR DIAG] SUCCESS: Controller {api_endpoint} completed successfully")
            
        except Exception as e:
            print(f"[CONTROLLER_COLLECTOR DIAG] COLLECTION FAILED: {api_endpoint} - {e}")
            LOG.error(f"[CONTROLLER_COLLECTOR] Error collecting from controller {api_endpoint}: {e}")
            continue

    print(f"[CONTROLLER_COLLECTOR DIAG] LOOP COMPLETED: Processed {controllers_collected} controllers out of {len(api_endpoints)} endpoints")
    LOG.info(f"[CONTROLLER_COLLECTOR] Collected data from {controllers_collected} controllers")
    
    if controllers_collected == 0:
        LOG.warning("[CONTROLLER_COLLECTOR] No controller data collected")
        return []
    
    # Don't update last_collection_time here - let each system decide independently
    # based on CONTROLLER_COLLECTION_INTERVAL vs intervalTime and iteration count
    print(f"[CONTROLLER_COLLECTOR DIAG] Collected from {controllers_collected} controllers, not updating last_collection_time")
    
    # Strict output: JSON or InfluxDB, never both
    if to_json:
        # Write separate JSON files for each controller to avoid mutual overwriting
        for i, point in enumerate(json_body):
            controller_endpoint = point['tags'].get('controller_endpoint', 'unknown')
            controller_id = point['tags'].get('controllerId', 'unknown')
            
            # Create unique filename per controller: controller_SYSTEM_CONTROLLER_timestamp.json
            clean_endpoint = controller_endpoint.replace('.', '_').replace(':', '_')
            filename = get_json_output_path(f'controller_{clean_endpoint}_{controller_id}', sys_id, to_json)
            
            try:
                with open(filename, 'w') as f:
                    json.dump([point], f, indent=2, default=str)  # Write single controller data
                LOG.info(f"[CONTROLLER_COLLECTOR] Controller JSON written to {filename}")
                print(f"[CONTROLLER_COLLECTOR DIAG] JSON SAVED: {filename}")
                
            except Exception as e:
                LOG.error(f"[CONTROLLER_COLLECTOR] Failed to write controller JSON for {controller_endpoint}: {e}")
                print(f"[CONTROLLER_COLLECTOR DIAG] JSON SAVE FAILED: {controller_endpoint} - {e}")
        
        return json_body
        
    else:
        print(f"[CONTROLLER_COLLECTOR DIAG] Writing {len(json_body)} points to InfluxDB")
        # Write to InfluxDB
        if not to_json:
            # Convert points for InfluxDB client/HTTP API
            records = []
            for p in json_body:
                tags = p["tags"]
                fields = p["fields"]
                timestamp = p.get("time")  # Get the actual time from JSON/API
                if timestamp is None:
                    timestamp = datetime.now(timezone.utc)  # Only fallback if missing
                # If timestamp is a string (from JSON replay), parse it
                elif isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp.replace(" ", "T"))
                    except Exception:
                        timestamp = datetime.now(timezone.utc)
                record = {**tags, **fields, "time": timestamp}   
                records.append(record)
            
            # Write to InfluxDB if we have points
            if records:
                LOG.info(f"[CONTROLLER_COLLECTOR] Sample record: {records[0]}")
                LOG.info(f"[CONTROLLER_COLLECTOR] Total controller records to write: {len(records)}")
                
                # Write to InfluxDB using database_client
                if database_client:
                    database_client.write(database=db_name, 
                                        record=records,
                                        data_frame_measurement_name="controllers",
                                        data_frame_timestamp_column="time")
                    LOG.info(f"[CONTROLLER_COLLECTOR] Successfully wrote {len(records)} controller records to InfluxDB")
                else:
                    LOG.warning("[CONTROLLER_COLLECTOR] No database_client available for writing to InfluxDB")
            else:
                LOG.warning("[CONTROLLER_COLLECTOR] No controller records to write to InfluxDB")
            
        return json_body
