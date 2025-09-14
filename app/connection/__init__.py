"""
Connection utilities for E-Series API interactions.
"""

import requests
import logging
import ssl
from typing import Tuple, List, Optional, Dict, Any

# Initialize logger
LOG = logging.getLogger(__name__)

def get_controller(endpoint_type: str, api_list: List[str]) -> str:
    """
    Get the controller URL for the specified endpoint type.
    
    Args:
        endpoint_type: The type of endpoint to construct
        api_list: List of API endpoints to use
        
    Returns:
        The complete controller URL
    """
    if not api_list:
        raise ValueError("No API endpoints provided")
    
    base_url = f"https://{api_list[0]}:8443"
    
    endpoint_mapping = {
        "sys": f"{base_url}/devmgr/v2/storage-systems",
        "drives": f"{base_url}/devmgr/v2/storage-systems/1/drives",
        "volumes": f"{base_url}/devmgr/v2/storage-systems/1/volumes",
        "interfaces": f"{base_url}/devmgr/v2/storage-systems/1/interfaces",
        "controllers": f"{base_url}/devmgr/v2/storage-systems/1/controllers",
        "hardware": f"{base_url}/devmgr/v2/storage-systems/1/hardware-inventory",
        "events": f"{base_url}/devmgr/v2/storage-systems/1/mel-events"
    }
    
    return endpoint_mapping.get(endpoint_type, endpoint_mapping["sys"])

def get_session(
    username: str,
    password: str,
    api_endpoints: List[str],
    tls_ca: Optional[str] = None,
    tls_validation: str = 'strict'
) -> Tuple[requests.Session, str, str]:
    """
    Establish a session with the E-Series API server using bearer token authentication.
    
    Args:
        username: Username for API authentication
        password: Password for API authentication
        api_endpoints: List of API endpoints to try
        tls_ca: Path to CA certificate for TLS validation
        tls_validation: TLS validation mode ('strict', 'normal', 'none')
        
    Returns:
        Tuple of (session object, access token, active endpoint)
    """
    if not api_endpoints:
        raise ValueError("No API endpoints provided")
    
    # Configure TLS verification based on mode
    verify_ssl = True
    if tls_validation == 'none':
        verify_ssl = False
        # Disable SSL warnings if verification is disabled
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)
    elif tls_ca:
        verify_ssl = tls_ca
    
    session = requests.Session()
    session.verify = verify_ssl
    
    # Try each endpoint until one succeeds
    for endpoint in api_endpoints:
        try:
            base_url = f"https://{endpoint}:8443"
            auth_url = f"{base_url}/devmgr/utils/login"
            
            # Attempt to authenticate using bearer token
            auth_data = {"userId": username, "password": password}
            response = session.post(
                auth_url,
                json=auth_data,
                timeout=30
            )
            
            if response.status_code == 200:
                # Extract the bearer token from response
                try:
                    token = response.json().get("accessToken")
                    if token:
                        LOG.info(f"Successfully authenticated to {endpoint}")
                        return session, token, base_url
                except Exception as e:
                    LOG.warning(f"Failed to parse authentication response from {endpoint}: {e}")
            else:
                LOG.warning(f"Authentication failed for {endpoint}: HTTP {response.status_code}")
        
        except requests.exceptions.RequestException as e:
            LOG.warning(f"Connection error for endpoint {endpoint}: {e}")
    
    # If we get here, all endpoints failed
    raise ConnectionError("Failed to establish connection with any of the provided API endpoints")