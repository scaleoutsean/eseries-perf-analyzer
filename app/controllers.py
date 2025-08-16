# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import random
import sys
import logging

LOG = logging.getLogger("collector")
DEFAULT_SYSTEM_PORT = '8443'


def get_controller(query, api_endpoints):
    """
    Returns a SANtricity API URL with param-based path for storage-systems or firmware.
    :param query: "sys" for storage-systems, "fw" for firmware
    :param api_endpoints: list of SANtricity controller IPs (strings)
    :return: full HTTPS URL string
    """
    if query == "sys":
        api_path = '/devmgr/v2/storage-systems'
    elif query == "fw":
        api_path = '/devmgr/v2/firmware/embedded-firmware'
    else:
        LOG.error("Unsupported API path requested, exiting...")
        sys.exit(1)
    # pick a random controller (or the only one if len==1)
    idx = random.randrange(len(api_endpoints))
    url = f"https://{api_endpoints[idx]}:{DEFAULT_SYSTEM_PORT}{api_path}"
    LOG.info("Controller selection: %s", url)
    return url
