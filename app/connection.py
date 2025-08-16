# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import logging
import random
import requests
import ssl
import urllib3
from urllib3.util.ssl_ import create_urllib3_context
from urllib3 import PoolManager
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
import base64

LOG = logging.getLogger("collector")
urllib3.disable_warnings()

class SSLAdapter(HTTPAdapter):
    """An HTTPS Transport Adapter that uses an explicit SSL context."""
    def __init__(self, verify_flags=ssl.VERIFY_X509_STRICT, **kwargs):
        self.verify_flags = verify_flags
        super().__init__(**kwargs)
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        context = create_urllib3_context(verify_flags=self.verify_flags)
        self.poolmanager = PoolManager(num_pools=connections, maxsize=maxsize,
                                       block=block, ssl_context=context, **pool_kwargs)


def get_session(username, password, api_endpoints, tls_ca=None, tls_validation='strict'):
    """
    Return a configured requests.Session and Bearer token for SANtricity API.
    Supports dual-controller failover by trying multiple endpoints.
    
    Args:
        api_endpoints: Single API host string or list of endpoints for failover
        tls_validation: 'strict', 'normal', or 'none'
    
    Returns:
        tuple: (session, access_token, active_endpoint)
    """
    # Ensure we have a list of endpoints
    if isinstance(api_endpoints, str):
        endpoints = [api_endpoints]
    else:
        endpoints = list(api_endpoints) if api_endpoints else []
    
    if not endpoints:
        LOG.error("No API endpoints provided")
        return None, None, None
        
    # For dual controllers, randomize the order as both ought to be usable anyway
    if len(endpoints) > 1:
        random.shuffle(endpoints)
        LOG.info(f"Multiple controllers detected. Trying endpoints in order: {endpoints}")
    
    last_exception = None
    
    for endpoint in endpoints:
        # Ensure endpoint is a full URL, and ignore attempts to use HTTP
        if not endpoint.startswith('http'):
            endpoint = f'https://{endpoint}'
        if ':' not in endpoint.split('//')[-1]:
            endpoint = f'{endpoint}:8443'
            
        LOG.info(f"Attempting connection to controller: {endpoint}")
        
        try:
            session, token = _try_single_endpoint(username, password, endpoint, tls_ca, tls_validation)
            if token:  # Success (either real token or "BASIC_AUTH")
                LOG.info(f"Successfully connected to controller: {endpoint}")
                return session, token, endpoint
            else:
                LOG.warning(f"Authentication failed for controller: {endpoint}")
        except Exception as e:
            LOG.warning(f"Controller {endpoint} failed: {e}")
            last_exception = e
            continue
    
    # All controllers failed
    LOG.error(f"All controllers failed. Last error: {last_exception}")
    return None, None, None


def _try_single_endpoint(username, password, api_host, tls_ca=None, tls_validation='strict'):
    """
    Try to establish a session with a single API endpoint.
    Returns (session, token) where token can be actual token, "BASIC_AUTH", or None
    """
    session = requests.Session()
    if tls_validation == 'none':
        session.verify = False
        LOG.warning("TLS validation is DISABLED (verify=False). This is insecure and should only be used for testing.")
    else:
        verify_flags = ssl.VERIFY_X509_STRICT if tls_validation == 'strict' else ssl.VERIFY_DEFAULT
        session.mount("https://", SSLAdapter(verify_flags=verify_flags))
        if tls_ca:
            session.verify = tls_ca
        else:
            session.verify = '/etc/ssl/certs'
    
    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json"
    })

    # Try Token Auth first. Some arrays may not have it, or not have it enabled
    access_token_url = f"{api_host}/devmgr/v2/access-token"
    payload = {"duration": 60}
    try:
        resp = session.post(
            access_token_url,
            json=payload,
            auth=HTTPBasicAuth(username, password),
            timeout=10
        )
        if resp.status_code == 200:
            token = resp.json().get('accessToken')
            if token:
                LOG.info("[get_session] Token Auth succeeded.")
                return session, token
        elif resp.status_code == 404:
            LOG.info("[get_session] Token endpoint not found (HTTP 404) - array doesn't support tokens")
        else:
            LOG.info(f"[get_session] Token Auth returned HTTP {resp.status_code}")
    except Exception as e:
        LOG.info(f"[get_session] Token Auth failed: {e}")

    # Try Basic Auth - test with actual API call like diag.py does
    LOG.info("[get_session] Trying Basic Auth with firmware endpoint...")
    userpass = f"{username}:{password}"
    b64 = base64.b64encode(userpass.encode()).decode()
    headers = {"Accept": "application/json", "Authorization": f"Basic {b64}"}
    
    try:
        # Use the same endpoint that works in diag.py
        firmware_url = f"{api_host}/devmgr/v2/firmware/embedded-firmware/1/versions"
        LOG.info(f"[get_session] Testing Basic Auth with: {firmware_url}")
        fw_resp = session.get(firmware_url, headers=headers, timeout=10)
        LOG.info(f"[get_session] Firmware endpoint response: HTTP {fw_resp.status_code}")
        if fw_resp.status_code == 200:
            LOG.info("[get_session] Basic Auth succeeded with firmware endpoint.")
            # Set up session for Basic Auth
            session.auth = (username, password)
            # Remove any token-based headers and set Basic Auth headers
            session.headers.update({"Authorization": f"Basic {b64}"})
            return session, "BASIC_AUTH"
        else:
            LOG.info(f"[get_session] Basic Auth firmware test failed: HTTP {fw_resp.status_code}")
            if fw_resp.status_code == 404:
                LOG.info("[get_session] Firmware endpoint returned 404 - trying alternative endpoints")
    except Exception as e:
        LOG.info(f"[get_session] Basic Auth firmware test failed: {e}")
    
    # Fallback to /about endpoint if firmware call fails
    try:
        version_url = f"{api_host}/devmgr/v2/storage-systems/1/about"
        LOG.info(f"[get_session] Testing Basic Auth with system about endpoint: {version_url}")
        vresp = session.get(version_url, headers=headers, timeout=10)
        LOG.info(f"[get_session] System about endpoint response: HTTP {vresp.status_code}")
        if vresp.status_code == 200:
            version_info = vresp.json()
            LOG.info(f"[get_session] Basic Auth succeeded with system about endpoint. SANtricity info: {version_info}")
            session.auth = (username, password)
            session.headers.update({"Authorization": f"Basic {b64}"})
            return session, "BASIC_AUTH"
        else:
            LOG.info(f"[get_session] System about endpoint failed: HTTP {vresp.status_code}")
    except Exception as e:
        LOG.info(f"[get_session] Basic Auth system about test failed: {e}")
    
    LOG.info("[get_session] Basic Auth failed - avoiding multiple endpoint tests to prevent possible lockout")
    return session, None
