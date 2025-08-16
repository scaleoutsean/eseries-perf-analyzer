# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import json
import logging
import os
from app.controllers import get_controller
from app.utils import get_json_output_path

LOG = logging.getLogger(__name__)

def get_drive_location(sys_id, session, san_headers, api_endpoints, loop_iteration, flags=None):
    """
    Retrieves hardware inventory and maps driveRefs to their tray and slot.
    :param sys_id: Storage system ID (WWN)
    :param session: HTTP session for API calls
    :param api_endpoints: list of API endpoint URLs
    :param loop_iteration: current iteration count for filename
    :return: dict mapping driveRef to [trayId, slot]
    """
    try:
        base_url = get_controller("sys", api_endpoints)
        resp = session.get(f"{base_url}/{sys_id}/hardware-inventory", headers=san_headers)
        try:
            hardware_list = resp.json()
        except Exception as e:
            LOG.error("[DRIVES] hardware-inventory response not JSON: %s", e)
            hardware_list = None
        # Hardware inventory is used ONLY for drive location enrichment
        # No need to save it to disk - location info gets embedded as tags in drive metrics
        # Unlike the less frequently collected metrics, we continue processing on same interval 
        # so that we detect fresh hardware data for drive location mapping as soon as other collectors do
        # This ensures new drives added during operation get proper location tags
        if not hardware_list:
            LOG.warning("[DRIVES] hardware-inventory response is None or empty.")
            return {}
        if isinstance(hardware_list, list) and len(hardware_list) == 0:
            LOG.warning("[DRIVES] hardware-inventory response is an empty list. This may be normal if no drive data is available yet.")
            return {}
        if not isinstance(hardware_list, dict):
            LOG.error(f"[DRIVES] Unexpected hardware-inventory response: {hardware_list}")
            return {}
        # Build tray ID map
        trays = hardware_list.get("trays", [])
        drives = hardware_list.get("drives", [])
        tray_ids = {tray.get("trayRef"): tray.get("trayId") for tray in trays}
        drive_location = {}
        unmatched_count = 0
        for drive in drives:
            drive_ref = drive.get("driveRef")
            tray_ref = drive.get("physicalLocation", {}).get("trayRef")
            tray_id = tray_ids.get(tray_ref)
            if tray_id and tray_id != "none":
                slot = drive.get("physicalLocation", {}).get("slot")
                drive_location[drive_ref] = [tray_id, slot]
            else:
                unmatched_count += 1
        
        # Log summary instead of individual errors as there could be hundreds
        if unmatched_count > 0:
            LOG.error("[DRIVES] %d drives couldn't be matched to a tray in the storage system", unmatched_count)
        
        return drive_location
    except Exception as e:
        LOG.error(f"[DRIVES] Error collecting drive locations: {e}")
        return {}
