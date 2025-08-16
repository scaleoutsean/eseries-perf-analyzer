# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import requests
import logging
import base64
import json
import os
from requests.auth import HTTPBasicAuth

# Logger for diagnostic functions
LOG = logging.getLogger("collector")

def _check_lockdown_status(santricity_ip, verify_ssl):
    """
    Check if the SANtricity system is in lockdown mode. Returns True if locked down.
    Lockdown may be enabled by SANtricity administrator in which case repeated "trying" makes things worse.
    Lockdown feature parameters decide how lockdown is enforced. Check with SANtricity documentation and RTFM for details.
    """
    try:
        # `1` is a catch-all system identifier (WWN) in SANtricity API paths
        lockdown_url = f"https://{santricity_ip}:8443/devmgr/v2/storage-systems/1/lockdownstatus"
        headers = {"accept": "application/json"}
        LOG.info("[DIAG] Checking lockdown status: GET %s", lockdown_url)
        
        response = requests.get(
            lockdown_url,
            headers=headers,
            verify=verify_ssl,
            timeout=30
        )
        
        if response.status_code == 200:
            try:
                lockdown_status = response.json()
                is_lockdown = lockdown_status.get("isLockdown", False)
                system_label = lockdown_status.get("storageSystemLabel", "Unknown")
                lockdown_type = lockdown_status.get("lockdownType", "unknown")
                
                if is_lockdown:
                    LOG.warning("[DIAG] System %s (%s) is in LOCKDOWN mode (type: %s)", 
                               santricity_ip, system_label, lockdown_type)
                    return True
                else:
                    LOG.info("[DIAG] System %s (%s) is not in lockdown mode", santricity_ip, system_label)
                    return False
            except Exception as e:
                LOG.warning("[DIAG] Could not parse lockdown status response: %s", e)
                return False
        else:
            LOG.warning("[DIAG] Lockdown status check failed: HTTP %s", response.status_code)
            return False
            
    except Exception as e:
        LOG.warning("[DIAG] Exception checking lockdown status: %s", e)
        return False

def _test_controller_ping(santricity_ip, username, password, verify_ssl, access_token=None):
    """
    Test controller ping to identify controller slots and health status.
    This is a basic test of connectivity and responsiveness. A controller may be reachable, but not 
    accessible (if, say, TLS validation fails)
    """
    LOG.info("[DIAG] Testing controller ping for %s", santricity_ip)
    
    # Test both controllers and auto    
    for controller in ['auto', 'a', 'b']:
        try:
            # `1` is a catch-all system identifier (WWN) in SANtricity API paths
            ping_url = f"https://{santricity_ip}:8443/devmgr/v2/storage-systems/1/symbol/pingController"
            params = {"controller": controller, "verboseErrorResponse": "false"}
            headers = {"accept": "application/json"}
            
            # Use Bearer token if available, otherwise Basic auth. Not all systems have Bearer tokens enabled.
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"
            else:
                userpass = f'{username}:{password}'
                b64 = base64.b64encode(userpass.encode()).decode()
                headers["Authorization"] = f"Basic {b64}"
            
            # Use longer timeout for controller ping (35s) as it can take ~30s for requests to failed controllers to fail
            response = requests.post(
                ping_url,
                headers=headers,
                params=params,
                verify=verify_ssl,
                timeout=35
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result == "ok":
                        if controller == 'auto':
                            LOG.info("[DIAG] Controller ping %s->%s: OK (active controller)", santricity_ip, controller)
                        else:
                            LOG.info("[DIAG] Controller ping %s->%s: OK (controller operational)", santricity_ip, controller)
                    else:
                        LOG.warning("[DIAG] Controller ping %s->%s: Unexpected response: %s", santricity_ip, controller, result)
                except Exception:
                    # Response might be plain text "ok"
                    if response.text.strip() == '"ok"' or response.text.strip() == 'ok':
                        if controller == 'auto':
                            LOG.info("[DIAG] Controller ping %s->%s: OK (active controller)", santricity_ip, controller)
                        else:
                            LOG.info("[DIAG] Controller ping %s->%s: OK (controller operational)", santricity_ip, controller)
                    else:
                        LOG.warning("[DIAG] Controller ping %s->%s: Unexpected text response: %s", santricity_ip, controller, response.text)
            else:
                try:
                    error_json = response.json()
                    error_msg = error_json.get("errorMessage", "Unknown error")
                    retcode = error_json.get("retcode", "unknown")
                    if "could not be contacted" in error_msg and "slot" in error_msg:
                        LOG.warning("[DIAG] Controller ping %s->%s: %s (retcode: %s)", santricity_ip, controller, error_msg, retcode)
                    else:
                        LOG.warning("[DIAG] Controller ping %s->%s: HTTP %s - %s", santricity_ip, controller, response.status_code, error_msg)
                except Exception:
                    LOG.warning("[DIAG] Controller ping %s->%s: HTTP %s", santricity_ip, controller, response.status_code)
            
        except requests.exceptions.Timeout:
            LOG.warning("[DIAG] Controller ping %s->%s: Timeout (controller likely unreachable)", santricity_ip, controller)
        except Exception as e:
            LOG.warning("[DIAG] Controller ping %s->%s: Exception - %s", santricity_ip, controller, e)

def get_santricity(api_endpoints, username=None, password=None, tls_ca=None, tls_validation='strict', to_json=False, json_dir=None):
    """
    Test SANtricity API endpoints independently of session creation and (for environments without a DB) InfluxDB logic.
    
    Parameters:
    - api_endpoints: List of SANtricity API IP addresses
    - username: SANtricity username
    - password: SANtricity password
    - tls_ca: CA certificate file path
    - tls_validation: TLS validation mode (default is 'normal' (enabled, regular); other options 'strict', 'none')
    - to_json: If True, save firmware info to JSON file
    - json_dir: Directory to save JSON files (required if to_json=True)
    
    Returns:
    - Dictionary mapping system IDs to firmware information
    """
    LOG.info("[DIAG] Starting SANtricity API independent test")
    
    # Dictionary to store firmware info by system ID
    fw_info_by_system = {}
    
    # Determine SSL verification based on tls_validation mode
    if tls_validation == 'none':
        verify_ssl = False
        LOG.info("[DIAG] TLS validation disabled (--tlsValidation none)")
    elif tls_ca:
        verify_ssl = tls_ca
        LOG.info("[DIAG] Using custom CA certificate: %s", tls_ca)
    else:
        verify_ssl = True
        LOG.info("[DIAG] Using default TLS validation")
        
    # Validate json_dir if to_json is True
    if to_json:
        if not json_dir:
            LOG.warning("[DIAG] json_dir parameter is required when to_json=True")
            to_json = False
        else:
            if not os.path.isdir(json_dir):
                try:
                    os.makedirs(json_dir, exist_ok=True)
                    LOG.info(f"[DIAG] Created JSON directory: {json_dir}")
                except Exception as e:
                    LOG.warning(f"[DIAG] Failed to create JSON directory {json_dir}: {e}")
                    to_json = False
    
    for santricity_ip in api_endpoints:
        token_success = False
        basic_success = False
        resp_json = {}
        
        # Validate credentials are provided
        if not username or not password:
            LOG.error("[DIAG] Username and password must be provided for authentication")
            continue
            
        try:
            url = f"https://{santricity_ip}:8443/devmgr/v2/access-token"
            payload = {"duration": 60}
            headers = {"accept": "application/json", "Content-Type": "application/json"}
            LOG.info("[DIAG] SANtricity API request: POST %s", url)
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                auth=HTTPBasicAuth(username, password),
                verify=verify_ssl,
                timeout=60
            )
            LOG.info("[DIAG] SANtricity API response: %s %s", response.status_code, response.reason)
            try:
                resp_json = response.json()
            except Exception:
                resp_json = {}
            if response.status_code == 200 and resp_json.get("accessToken"):
                LOG.info("[DIAG] access-token endpoint: accessToken present and status 200 OK (Token Auth)")
                token_success = True
            else:
                LOG.warning("[DIAG] access-token endpoint: status %s, response: %s (Token Auth)", response.status_code, resp_json)
        except Exception as e:
            LOG.warning("[DIAG] Exception during Token Auth: %s", e)

        if not token_success:
            LOG.info("[DIAG] Token Auth failed, trying Basic Auth with actual API endpoint...")
            # Test Basic Auth against actual API endpoints like connection.py does
            userpass = f"{username}:{password}"
            b64 = base64.b64encode(userpass.encode()).decode()
            basic_headers = {"Accept": "application/json", "Authorization": f"Basic {b64}"}
            
            # Try firmware endpoint first (same as connection.py)
            try:
                firmware_url = f"https://{santricity_ip}:8443/devmgr/v2/firmware/embedded-firmware/1/versions"
                LOG.info("[DIAG] Testing Basic Auth with firmware endpoint: GET %s", firmware_url)
                fw_resp = requests.get(firmware_url, headers=basic_headers, verify=verify_ssl, timeout=30)
                LOG.info("[DIAG] Firmware endpoint response: HTTP %s", fw_resp.status_code)
                if fw_resp.status_code == 200:
                    LOG.info("[DIAG] Basic Auth succeeded with firmware endpoint")
                    basic_success = True
                else:
                    LOG.info("[DIAG] Firmware endpoint failed with HTTP %s", fw_resp.status_code)
            except Exception as e:
                LOG.info("[DIAG] Basic Auth firmware test failed: %s", e)
            
            # Fallback to system about endpoint if firmware fails
            if not basic_success:
                try:
                    about_url = f"https://{santricity_ip}:8443/devmgr/v2/storage-systems/1/about"
                    LOG.info("[DIAG] Testing Basic Auth with system about endpoint: GET %s", about_url)
                    about_resp = requests.get(about_url, headers=basic_headers, verify=verify_ssl, timeout=30)
                    LOG.info("[DIAG] System about endpoint response: HTTP %s", about_resp.status_code)
                    if about_resp.status_code == 200:
                        LOG.info("[DIAG] Basic Auth succeeded with system about endpoint")
                        basic_success = True
                    else:
                        LOG.info("[DIAG] System about endpoint failed with HTTP %s", about_resp.status_code)
                except Exception as e:
                    LOG.info("[DIAG] Basic Auth system about test failed: %s", e)
            
            if not basic_success:
                LOG.info("[DIAG] Basic Auth failed - avoiding multiple endpoint tests to prevent lockout")

        # Test controller ping to identify which controller slot this IP represents
        _test_controller_ping(santricity_ip, username, password, verify_ssl, resp_json.get("accessToken"))

        fw_json = None
        system_id = None
        system_name = None
        
        # First, try to get system ID and name
        try:
            # `1` is a catch-all system identifier (WWN) in SANtricity API paths
            sys_url = f"https://{santricity_ip}:8443/devmgr/v2/storage-systems/1"
            sys_headers = {"accept": "application/json"}
            if token_success and resp_json.get("accessToken"):
                sys_headers["Authorization"] = f"Bearer {resp_json.get('accessToken')}"
            else:
                userpass = f'{username}:{password}'
                b64 = base64.b64encode(userpass.encode()).decode()
                sys_headers["Authorization"] = f"Basic {b64}"
                
            LOG.info("[DIAG] Getting system info: GET %s", sys_url)
            sys_resp = requests.get(sys_url, headers=sys_headers, verify=verify_ssl, timeout=30)
            if sys_resp.status_code == 200:
                sys_json = sys_resp.json()
                system_id = sys_json.get("id", "unknown")
                system_name = sys_json.get("name", "unknown")
                system_wwn = sys_json.get("wwn", "unknown")
                LOG.info(f"[DIAG] Found system: ID={system_id}, Name={system_name}, WWN={system_wwn}")
                LOG.info(f"[DIAG] System ID type: {type(system_id).__name__}, value: '{system_id}'")
                LOG.info(f"[DIAG] System WWN type: {type(system_wwn).__name__}, value: '{system_wwn}'")
                
                # Check if we found a valid WWN
                if system_wwn and system_wwn != "unknown":
                    LOG.info(f"[DIAG] Found valid WWN: {system_wwn} (will be used for file naming)")
                else:
                    LOG.warning(f"[DIAG] No valid WWN found, will fall back to system ID or name for file naming")
                
                # If system_id or system_wwn is not a string, convert it
                if not isinstance(system_id, str):
                    system_id = str(system_id)
                    LOG.info(f"[DIAG] Converted system_id to string: '{system_id}'")
                if not isinstance(system_wwn, str):
                    system_wwn = str(system_wwn)
                    LOG.info(f"[DIAG] Converted system_wwn to string: '{system_wwn}'")
            else:
                LOG.warning(f"[DIAG] Could not retrieve system info: HTTP {sys_resp.status_code}")
        except Exception as se:
            LOG.warning(f"[DIAG] Exception retrieving system info: {se}")
        
        # Now get firmware info
        try:
            # `1` is a catch-all system identifier (WWN) in SANtricity API paths
            fw_url = f"https://{santricity_ip}:8443/devmgr/v2/firmware/embedded-firmware/1/versions"
            fw_headers = {"accept": "application/json"}
            if token_success and resp_json.get("accessToken"):
                # Use Bearer token if we got one successfully
                fw_headers["Authorization"] = f"Bearer {resp_json.get('accessToken')}"
                LOG.info("[DIAG] Using Bearer token for firmware request")
            elif not token_success:
                # Fallback to Basic auth if token auth failed
                userpass = f'{username}:{password}'
                b64 = base64.b64encode(userpass.encode()).decode()
                fw_headers["Authorization"] = f"Basic {b64}"
                LOG.info("[DIAG] Using Basic auth for firmware request")
            LOG.info("[DIAG] SANtricity firmware version request: GET %s", fw_url)
            fw_resp = requests.get(fw_url, headers=fw_headers, verify=verify_ssl, timeout=60)
            LOG.info("[DIAG] Firmware version response: %s %s", fw_resp.status_code, fw_resp.reason)
            if fw_resp.status_code == 200:
                fw_json = fw_resp.json()
                
                # Log firmware modules
                for mod in fw_json.get("codeVersions", []):
                    LOG.info("[DIAG] Firmware module: %s, version: %s", mod.get("codeModule"), mod.get("versionString"))
                
                # Add system info to firmware data for context
                if system_id and system_name:
                    fw_json["system_id"] = system_id
                    fw_json["system_name"] = system_name
                    fw_json["system_ip"] = santricity_ip
                    if system_wwn and system_wwn != "unknown":
                        fw_json["system_wwn"] = system_wwn
                    
                # Store in our dictionary
                if system_id:
                    fw_info_by_system[system_id] = fw_json
                else:
                    # If we couldn't get a system ID, use the IP as key
                    fw_info_by_system[santricity_ip] = fw_json
                    
                # Save to JSON file if requested
                if to_json and json_dir:
                    try:
                        # Try to use system_wwn first as it matches the naming convention used by other files
                        if fw_json.get("system_wwn") and fw_json.get("system_wwn") != "unknown":
                            file_id = fw_json.get("system_wwn")
                            LOG.info(f"[DIAG] Using WWN for file_id: {file_id}")
                        else:
                            # Fall back to system_id if available
                            actual_system_id = fw_json.get("system_id", system_id)
                            # If system_id is "1" (the default in the URL path) but we have a meaningful system name, use that instead
                            if actual_system_id == "1" and fw_json.get("system_name") and fw_json.get("system_name") != "unknown":
                                file_id = fw_json.get("system_name").replace(" ", "_")
                                LOG.info(f"[DIAG] Using system_name for file_id: {file_id}")
                            elif actual_system_id and actual_system_id != "1" and actual_system_id != "unknown":
                                file_id = actual_system_id
                                LOG.info(f"[DIAG] Using system_id for file_id: {file_id}")
                            else:
                                # Fallback to IP if we don't have a good system identifier
                                file_id = santricity_ip.replace(".", "_")
                                LOG.info(f"[DIAG] Using IP for file_id: {file_id}")
                            
                        config_file = os.path.join(json_dir, f"config_{file_id}.json")
                        LOG.info(f"[DIAG] Attempting to save firmware info to {config_file}")
                        LOG.info(f"[DIAG] json_dir path exists: {os.path.exists(json_dir)}")
                        LOG.info(f"[DIAG] json_dir is writable: {os.access(json_dir, os.W_OK)}")
                        
                        with open(config_file, 'w') as f:
                            json.dump(fw_json, f, indent=2)
                        
                        # Verify file was created
                        if os.path.exists(config_file):
                            LOG.info(f"[DIAG] Successfully saved firmware info to {config_file}")
                        else:
                            LOG.warning(f"[DIAG] File {config_file} was not created despite no exceptions")
                    except Exception as fe:
                        LOG.warning(f"[DIAG] Failed to save firmware info to file: {fe}")
                        LOG.warning(f"[DIAG] Exception details: {type(fe).__name__}: {str(fe)}")
            else:
                LOG.warning("[DIAG] Could not retrieve firmware versions: HTTP %s", fw_resp.status_code)
        except Exception as fe:
            LOG.warning("[DIAG] Exception retrieving firmware versions: %s", fe)

        if fw_json and not to_json:
            # Only print if not saving to file
            print(json.dumps(fw_json, indent=2))
            
    # Return the collected firmware information
    return fw_info_by_system



def test_reachability(api_endpoints, influxdb_url, auth_token, tls_ca=None, tls_validation='strict', username=None, password=None):
    """Test SANtricity API and InfluxDB reachability with proper TLS validation."""
    
    # Determine SSL verification based on tls_validation mode
    if tls_validation == 'none':
        verify_ssl = False
        LOG.info("[DIAG] TLS validation disabled")
    elif tls_ca:
        verify_ssl = tls_ca
        LOG.info("[DIAG] Using custom CA certificate: %s", tls_ca)
    else:
        verify_ssl = True
        LOG.info("[DIAG] Using default TLS validation")
    
    # Test SANtricity API access-token endpoint
    for santricity_ip in api_endpoints:
        # Check lockdown status first to avoid making lockout worse
        if _check_lockdown_status(santricity_ip, verify_ssl):
            LOG.warning("[DIAG] Skipping authentication test for %s due to controller-side API lockdown", santricity_ip)
            continue
            
        # Validate credentials are provided
        if not username or not password:
            LOG.error("[DIAG] Username and password must be provided for authentication")
            continue
            
        try:
            url = f"https://{santricity_ip}:8443/devmgr/v2/access-token"
            payload = {"duration": 60}
            headers = {"accept": "application/json", "Content-Type": "application/json"}
            LOG.info("[DIAG] Testing SANtricity API: POST %s", url)
            
            # Try Token Auth first
            token_success = False
            access_token = None
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                auth=HTTPBasicAuth(username, password),
                verify=verify_ssl,
                timeout=60
            )
            LOG.info("[DIAG] SANtricity API response: %s %s", response.status_code, response.reason)
            
            if response.status_code == 200:
                try:
                    resp_json = response.json()
                    if resp_json.get("accessToken"):
                        LOG.info("[DIAG] SANtricity API: OK (token auth available)")
                        access_token = resp_json.get("accessToken")
                        token_success = True
                    else:
                        LOG.info("[DIAG] SANtricity API: Token endpoint responded but no token (trying Basic Auth)")
                except Exception:
                    LOG.info("[DIAG] SANtricity API: Token endpoint responded but invalid JSON (trying Basic Auth)")
            elif response.status_code == 404:
                LOG.info("[DIAG] SANtricity API: Token endpoint not found (HTTP 404) - trying Basic Auth")
            else:
                LOG.info("[DIAG] SANtricity API: Token auth failed (HTTP %s) - trying Basic Auth", response.status_code)
            
            # If token auth failed, try Basic Auth with actual API endpoints
            if not token_success:
                LOG.info("[DIAG] Testing Basic Auth with actual API endpoints...")
                userpass = f"{username}:{password}"
                b64 = base64.b64encode(userpass.encode()).decode()
                basic_headers = {"Accept": "application/json", "Authorization": f"Basic {b64}"}
                
                basic_success = False
                # Try firmware endpoint first
                try:
                    firmware_url = f"https://{santricity_ip}:8443/devmgr/v2/firmware/embedded-firmware/1/versions"
                    LOG.info("[DIAG] Testing Basic Auth: GET %s", firmware_url)
                    fw_resp = requests.get(firmware_url, headers=basic_headers, verify=verify_ssl, timeout=30)
                    LOG.info("[DIAG] Basic Auth firmware response: HTTP %s", fw_resp.status_code)
                    if fw_resp.status_code == 200:
                        LOG.info("[DIAG] SANtricity API: OK (basic auth with firmware endpoint)")
                        basic_success = True
                except Exception as e:
                    LOG.info("[DIAG] Basic Auth firmware test failed: %s", e)
                
                # Try system about endpoint if firmware fails
                if not basic_success:
                    try:
                        about_url = f"https://{santricity_ip}:8443/devmgr/v2/storage-systems/1/about"
                        LOG.info("[DIAG] Testing Basic Auth: GET %s", about_url)
                        about_resp = requests.get(about_url, headers=basic_headers, verify=verify_ssl, timeout=30)
                        LOG.info("[DIAG] Basic Auth system about response: HTTP %s", about_resp.status_code)
                        if about_resp.status_code == 200:
                            LOG.info("[DIAG] SANtricity API: OK (basic auth with system about endpoint)")
                            basic_success = True
                    except Exception as e:
                        LOG.info("[DIAG] Basic Auth system about test failed: %s", e)
                
                if not basic_success:
                    LOG.warning("[DIAG] SANtricity API: NG (both token and basic auth failed) - avoiding multiple tests to prevent lockout")
                    continue
                
            # Test controller ping to identify controller slots
            _test_controller_ping(santricity_ip, username, password, verify_ssl, access_token)
            
        except Exception as e:
            LOG.warning("[DIAG] SANtricity API: NG (%s)", e)
    
    # Test InfluxDB health endpoint if credentials provided
    if influxdb_url and auth_token:
        try:
            # curl "http://localhost:8181/health" --header "Authorization: Bearer ADMIN_TOKEN"
            # Auth on health endpoint is by default enabled. EPA disables it in reference docker-compose.yaml
            # Still, the user may remove it and then we'd fail anyway.
            health_url = f"{influxdb_url}/health"            
            headers = {"Authorization": f"Bearer {auth_token}"}
            LOG.info("[DIAG] Testing InfluxDB: GET %s", health_url)
            response = requests.get(
                health_url,
                headers=headers,
                verify=verify_ssl
            )
            LOG.info("[DIAG] InfluxDB response: %s %s", response.status_code, response.reason)
            if response.status_code == 200:
                try:
                    health = response.json()
                    if health.get("status") == "pass":
                        LOG.info("[DIAG] InfluxDB: OK")
                        return True
                    else:
                        LOG.warning("[DIAG] InfluxDB: NG (status not 'pass')")
                except Exception:
                    LOG.warning("[DIAG] InfluxDB: NG (invalid JSON response)")
            else:
                LOG.warning("[DIAG] InfluxDB: NG (HTTP %s)", response.status_code)
        except Exception as e:
            LOG.warning("[DIAG] InfluxDB: NG (%s)", e)
    else:
        LOG.info("[DIAG] InfluxDB: Skipped (no URL or token provided)")
    
    return False
