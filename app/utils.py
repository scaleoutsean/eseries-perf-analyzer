# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import os
import logging
from datetime import datetime


def get_json_output_path(function_name, sys_id=None, outdir=None):
    """Generate JSON output file path with timestamp and system ID for all collectors."""
    # Get logger
    LOG = logging.getLogger("collector")
    
    # Determine output directory
    directory = outdir if outdir else '.'
    os.makedirs(directory, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    
    # Validate system ID - should be a WWN
    if not sys_id or sys_id == '1' or sys_id == 'unknown':
        LOG.warning(f"[UTILS] Invalid or missing WWN ({sys_id}) for {function_name} data. This will cause inconsistent JSON file naming and potentially non-attributable metrics.")

    # Always include system ID if provided to distinguish between multiple arrays
    if sys_id:
        # Clean WWN to be filesystem-safe (remove colons, if any)
        clean_wwn = sys_id.replace(':', '').upper()
        filename = f"{function_name}_{clean_wwn}_{timestamp}.json"
    else:
        # This should never happen in normal operation - WWN should be mandatory but we'll log an error
        LOG.error(f"[UTILS] Missing system ID for {function_name} data. File will not have system identifier.")
        filename = f"{function_name}_{timestamp}.json"
    
    return os.path.join(directory, filename)
 
def order_sensor_response_list(response):
    """
    Reorders the sensor readings list by ascending thermalSensorRef for stable sensor ordering.
    Handles both dict and list response formats for backward compatibility with older arrays.
    """
    LOG = logging.getLogger("collector")
    
    # Add debug logging to understand data structure differences between array versions
    LOG.debug(f"[order_sensor_response_list] Response type: {type(response)}")
    if isinstance(response, dict):
        LOG.debug(f"[order_sensor_response_list] Dict keys: {list(response.keys())}")
        if 'thermalSensorData' in response:
            LOG.debug(f"[order_sensor_response_list] thermalSensorData type: {type(response['thermalSensorData'])}, length: {len(response.get('thermalSensorData', []))}")
        else:
            LOG.warning(f"[order_sensor_response_list] No 'thermalSensorData' key found in response dict")
    elif isinstance(response, list):
        LOG.debug(f"[order_sensor_response_list] List length: {len(response)}")
        if response:
            LOG.debug(f"[order_sensor_response_list] First item type: {type(response[0])}")
            if isinstance(response[0], dict):
                LOG.debug(f"[order_sensor_response_list] First item keys: {list(response[0].keys())}")
    else:
        LOG.warning(f"[order_sensor_response_list] Unexpected response type: {type(response)}")
    
    # Handle different response formats for backward compatibility
    if isinstance(response, list):
        # Older arrays may return the sensor data directly as a list
        LOG.debug("[order_sensor_response_list] Processing response as direct list (older array format)")
        sensor_data = response
    elif isinstance(response, dict) and 'thermalSensorData' in response:
        # Newer arrays return sensor data wrapped in a dict
        LOG.debug("[order_sensor_response_list] Processing response as dict with thermalSensorData key (newer array format)")
        sensor_data = response['thermalSensorData']
    else:
        # Fallback for unexpected formats
        LOG.warning("[order_sensor_response_list] Unable to identify sensor data format, returning empty list")
        return []
    
    # Sort sensor data by thermalSensorRef if available
    osensor = []
    for i, item in enumerate(sensor_data):
        if isinstance(item, dict) and 'thermalSensorRef' in item:
            osensor.append((item.get('thermalSensorRef'), i))
        else:
            # If no thermalSensorRef, maintain original order
            osensor.append((i, i))
    
    osensor.sort()
    orderedResponse = []
    for _, idx in osensor:
        if idx < len(sensor_data):
            orderedResponse.append(sensor_data[idx])
    
    LOG.debug(f"[order_sensor_response_list] Returning {len(orderedResponse)} ordered sensor items")
    return orderedResponse
 
def create_failure_dict_item(sys_id, sys_name, fail_type, obj_ref, obj_type, is_active, the_time):
    """
    Build a failure dictionary item for InfluxDB with given parameters
    """
    item = dict(
        measurement="failures",
        tags=dict(
            sys_id=sys_id,
            sys_name=sys_name,
            failure_type=fail_type,
            object_ref=obj_ref,
            object_type=obj_type,
            active=is_active
        ),
        fields=dict(
            name_of=sys_name,
            type_of=fail_type
        ),
        time=the_time
    )
    return item
