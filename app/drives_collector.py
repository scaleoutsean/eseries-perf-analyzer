# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

"""
Drives data collector module for E-Series Performance Analyzer.

Handles collection of drive information including media type, SSD wear life,
physical location data, firmware and more. Collected every DRIVES_COLLECTION_INTERVAL
seconds due to the static nature of data.
"""

import json
import logging
import time
from datetime import datetime, timezone

from app.controllers import get_controller
from app.utils import get_json_output_path

LOG = logging.getLogger(__name__)

# Get configuration
try:
    from app.config import EnvConfig
    DRIVES_COLLECTION_INTERVAL = EnvConfig().DRIVES_COLLECTION_INTERVAL
except Exception:
    # Fallback to default if config import fails
    DRIVES_COLLECTION_INTERVAL = 604800  # 1 week in seconds

# Track last collection time globally
last_collection_time = 0

def write_to_influxdb_http(influxdb_url, auth_token, database, records, measurement_name):
    """
    Write records to InfluxDB using HTTP API instead of client library
    """
    raise NotImplementedError("Direct HTTP line protocol ingestion is disabled. Use the InfluxDB3 Python client.")

def collect_drives_data(sys_info, session, san_headers, api_endpoints, database_client, db_name, flags, loop_iteration=None, influxdb_url=None, auth_token=None):
    """
    Collects drive information, including media type and SSD wear life.
    This function runs at a lower frequency than normal metric collection.

    Args:
        sys_info: dict with 'wwn' and 'name'
        session: HTTP session for API calls
        san_headers: Headers for SANtricity API requests
        api_endpoints: list of SANtricity API endpoints
        database_client: DatabaseClient instance for InfluxDB writes
        db_name: Database name
        flags: Configuration flags object
        loop_iteration: Loop iteration (unused, kept for compatibility)
        influxdb_url: InfluxDB URL (unused, kept for compatibility)
        auth_token: Auth token (unused, kept for compatibility)

    Returns:
        list: Empty list as required by execute_collector_safely
    """
    LOG.info("[DRIVES_COLLECTOR] Entered collect_drives_data")
    LOG.info("[DRIVES_COLLECTOR] Using collection interval: %s seconds", DRIVES_COLLECTION_INTERVAL)

    global last_collection_time

    # Validate system info
    LOG.info(f"[DRIVES_COLLECTOR] sys_info: {sys_info}")
    if 'wwn' not in sys_info or not sys_info['wwn']:
        LOG.error("[DRIVES_COLLECTOR] Missing or empty WWN in system info. WWN is mandatory for proper metrics collection.")
        return []

    # Get system identifiers
    sys_id = sys_info['wwn']
    sys_name = sys_info.get('name', 'unknown')
    LOG.info(f"[DRIVES_COLLECTOR] Processing system {sys_name} (WWN: {sys_id})")

    # Check if we should collect based on time elapsed
    current_time = int(time.time())
    time_since_last = current_time - last_collection_time

    if time_since_last < DRIVES_COLLECTION_INTERVAL and last_collection_time > 0:
        LOG.info(f"[DRIVES_COLLECTOR] Skipping drive collection. Last collection was {time_since_last} seconds ago (interval: {DRIVES_COLLECTION_INTERVAL})")
        return []

    LOG.info(f"[DRIVES_COLLECTOR] Collecting drive information for {sys_name} (WWN: {sys_id})")

    # Record this collection time
    last_collection_time = current_time

    try:
        # Get the controller URL
        LOG.info("[DRIVES_COLLECTOR] Before get_controller()")
        base = get_controller('sys', api_endpoints)
        LOG.info(f"[DRIVES_COLLECTOR] base: {base}")

        # Make the API request to /storage-systems/{sys_id}/drives
        endpoint_url = f"{base}/{sys_id}/drives"
        LOG.info(f"[DRIVES_COLLECTOR] About to GET drives data: GET {endpoint_url}")

        resp = session.get(endpoint_url, headers=san_headers)
        LOG.info(f"[DRIVES_COLLECTOR] Got drives data response: {resp.status_code}")

        if resp.status_code != 200:
            LOG.error(f"[DRIVES_COLLECTOR] Failed to get drives data: HTTP {resp.status_code}")
            return []

        drives_data = resp.json()
        if not drives_data:
            LOG.warning("[DRIVES_COLLECTOR] Empty drives data response")
            return []

        LOG.info(f"[DRIVES_COLLECTOR] Got {len(drives_data)} drives")

        # Process the drives data first (both for InfluxDB and consistent JSON format)
        points = []
        timestamp = datetime.now(timezone.utc)

        for drive in drives_data:
            # Extract all fields from the drive
            tags = {
                "system_id": sys_id,
                "system_name": sys_name,
            }

            # Add key identifiers as tags (for faster queries)
            for id_field in ['id', 'driveRef', 'serialNumber']:
                if id_field in drive:
                    tags[id_field] = drive[id_field]

            # Add drive media type as a tag since it's a categorical value
            if 'driveMediaType' in drive:
                tags['driveMediaType'] = drive['driveMediaType']

            # Add interface type as a tag since it's a categorical value
            if 'interfaceType' in drive:
                tags['interfaceType'] = drive['interfaceType']

            # Add status as a tag since it's a categorical value
            if 'status' in drive:
                tags['status'] = drive['status']

            # Prepare fields - exclude the ones we already used as tags
            exclude_from_fields = list(tags.keys()) + ['system_id', 'system_name']

            # All remaining fields go into the fields dict
            fields = {}
            for k, v in drive.items():
                if k not in exclude_from_fields:
                    # Handle different types of values
                    if isinstance(v, (int, float)):
                        fields[k] = v
                    elif isinstance(v, bool):
                        fields[k] = v
                    elif isinstance(v, dict):
                        # Flatten nested dictionaries with underscores
                        for nested_k, nested_v in v.items():
                            if isinstance(nested_v, (int, float, bool)):
                                fields[f"{k}_{nested_k}"] = nested_v
                            elif isinstance(nested_v, dict):
                                # Handle deeper nesting (e.g., interfaceType.nvme.deviceName)
                                for deep_k, deep_v in nested_v.items():
                                    if deep_k == "deviceName" and isinstance(deep_v, str):
                                        # Clean deviceName - keep only part before first space
                                        clean_name = deep_v.split()[0] if deep_v.split() else deep_v
                                        fields[f"{k}_{nested_k}_{deep_k}"] = clean_name
                                    elif isinstance(deep_v, (int, float, bool)):
                                        fields[f"{k}_{nested_k}_{deep_k}"] = deep_v
                                    elif deep_v is not None and not isinstance(deep_v, (list, dict)):
                                        fields[f"{k}_{nested_k}_{deep_k}"] = str(deep_v)
                                    # Skip arrays and complex nested objects
                            elif nested_k == "locationParent":
                                # Skip locationParent - it's a complex nested dict as string
                                continue
                            elif nested_v is not None and not isinstance(nested_v, (list, dict)):
                                fields[f"{k}_{nested_k}"] = str(nested_v)
                            # Skip arrays and complex nested objects
                    elif v is not None:
                        fields[k] = str(v)

            # Create point data (consistent with other collectors)
            point_data = {
                "measurement": "drives",
                "tags": tags,
                "fields": fields,
                "time": timestamp
            }

            # Add to points list
            points.append(point_data)

        # Save processed InfluxDB points to JSON if requested (consistent with other collectors)
        to_json = getattr(flags, 'toJson', None)
        if to_json:
            LOG.info(f"[DRIVES_COLLECTOR] toJson flag set, preparing to write processed InfluxDB points")
            json_path = get_json_output_path('drives', sys_id, to_json)
            LOG.info(f"[DRIVES_COLLECTOR] JSON output path: {json_path}")

            try:
                with open(json_path, 'w') as f:
                    json.dump(points, f, indent=2, default=str)  # default=str handles datetime serialization
                LOG.info(f"[DRIVES_COLLECTOR] Successfully wrote {len(points)} processed InfluxDB points to {json_path}")
            except Exception as e:
                LOG.error(f"[DRIVES_COLLECTOR] Failed to write JSON: {e}")

        # Write to InfluxDB if client available
        if database_client and database_client.is_available():
            try:
                # For InfluxDBClient3
                records = []
                for p in points:
                    tags = p["tags"]
                    fields = p["fields"]
                    timestamp = p.get("time", datetime.now(timezone.utc))
                    # Ensure timestamp is a datetime object for proper InfluxDB3 handling
                    if isinstance(timestamp, str):
                        try:
                            timestamp = datetime.fromisoformat(timestamp.replace(" ", "T"))
                        except Exception:
                            timestamp = datetime.now(timezone.utc)
                    record = {**tags, **fields, "time": timestamp}  # Use "time" not "timestamp"
                    records.append(record)

                # Write to InfluxDB if we have points
                if records:
                    LOG.info(f"[DRIVES_COLLECTOR] Sample record: {records[0]}")
                    LOG.info(f"[DRIVES_COLLECTOR] Total drive records to write: {len(records)}")

                    # Use centralized database client (handles integer field conversion internally)
                    database_client.write(records, "drives")
                    LOG.info(f"[DRIVES_COLLECTOR] Successfully wrote {len(records)} drive records to InfluxDB via database client")
                else:
                    LOG.warning("[DRIVES_COLLECTOR] No drive records to write to InfluxDB")

            except Exception as e:
                LOG.error(f"[DRIVES_COLLECTOR] Failed to write to InfluxDB: {e}")

    except Exception as e:
        LOG.error(f"[DRIVES_COLLECTOR] Error collecting drive data: {e}")

    return []  # Empty list as required by execute_collector_safely
