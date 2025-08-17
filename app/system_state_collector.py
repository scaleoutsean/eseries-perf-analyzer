# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import json
import os
import logging
import sys
import hashlib
from datetime import datetime, timezone
from collections.abc import Iterable
from app.config import INFLUXDB_WRITE_PRECISION
from app.controllers import get_controller
from app.utils import create_failure_dict_item, get_json_output_path

LOG = logging.getLogger(__name__)

def load_system_failures_checkpoint(influx_client, sys_id):
    """Load system failures checkpoint from file-based storage"""
    # Use file-based approach as InfluxDB v3 may not be available
    checkpoint_file = f"/tmp/system_failures_checkpoint_{sys_id}.json"
    try:
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r') as f:
                data = json.load(f)
                return {
                    'content_checksum': data.get('content_checksum', '')
                }
    except Exception as e:
        LOG.warning(f"Could not load system failures checkpoint for {sys_id}: {e}")
    
    return {'content_checksum': ''}

def save_system_failures_checkpoint(influx_client, sys_id, checksum, db_name):
    """Save system failures checkpoint using both InfluxDB and file-based backup"""
    # Save to InfluxDB for metrics/monitoring
    try:
        checkpoint_data = [{
            'measurement': 'system_failures_checkpoint',
            'tags': {
                'sys_id': sys_id
            },
            'fields': {
                'content_checksum': str(checksum)
            },
            'time': datetime.now(timezone.utc).isoformat()
        }]
        influx_client.write(checkpoint_data, database=db_name, time_precision=INFLUXDB_WRITE_PRECISION)
        LOG.debug(f"Saved system failures checkpoint to InfluxDB for {sys_id}")
    except Exception as e:
        LOG.warning(f"Could not save system failures checkpoint to InfluxDB for {sys_id}: {e}")
    
    # Save to local file as backup/primary storage until InfluxDB query works reliably
    try:
        checkpoint_file = f"/tmp/system_failures_checkpoint_{sys_id}.json"
        checkpoint_data = {
            'content_checksum': str(checksum),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f)
        LOG.debug(f"Saved system failures checkpoint to file for {sys_id}")
    except Exception as e:
        LOG.error(f"Could not save system failures checkpoint to file for {sys_id}: {e}")

def collect_system_state(sys_info, checksums, session, san_headers, api_endpoints, influx_host, influx_port, db_name, auth_token, flags, influx_client=None):
    """
    Collects state information from the storage system and posts it to InfluxDB or writes to JSON.
    :param sys_info: dict with 'wwn' and 'name'
    :param checksums: dict tracking previous failure_response checksums
    :param api_endpoints: list of SANtricity API endpoints
    :param influx_host: InfluxDB host URL
    :param influx_port: InfluxDB port
    :param db_name: InfluxDB database name
    :param auth_token: InfluxDB auth token
    """
    try:
        # Strict output mode: either JSON or InfluxDB, never both
        to_json = getattr(flags, 'toJson', None)
        
        # Mandate WWN - it's essential for proper system identification
        if 'wwn' not in sys_info or not sys_info['wwn']:
            LOG.error("[SYSTEM_STATE] Missing or empty WWN in system info. WWN is mandatory for proper metrics collection.")
            return []
            
        sys_id = sys_info['wwn']
        sys_name = sys_info['name']
        session.headers.update(san_headers)
        failure_response = session.get(
            f"{get_controller('sys', api_endpoints)}/{sys_id}/failures"
        ).json()

        # Calculate checksum for change detection
        new_checksum = hashlib.md5(json.dumps(failure_response).encode('utf-8')).hexdigest()
        
        # For JSON mode with InfluxDB available, use persistent checkpoint for better duplicate detection
        if to_json and influx_client is not None:
            # Load persistent checkpoint from file/InfluxDB
            checkpoint = load_system_failures_checkpoint(influx_client, sys_id)
            old_checksum_persistent = checkpoint['content_checksum']
            
            if old_checksum_persistent and str(new_checksum) == str(old_checksum_persistent):
                LOG.info("System failures content unchanged for system %s (persistent checkpoint), skipping JSON write", sys_id)
                return
        
        # For non-JSON mode (InfluxDB), use in-memory checksums to skip InfluxDB writes when unchanged
        # This preserves the original behavior of avoiding duplicate InfluxDB writes
        old_checksum = checksums.get(str(sys_id))
        if old_checksum is not None and new_checksum == old_checksum and not to_json:
            return
        checksums[str(sys_id)] = new_checksum

        json_body = []
        if not to_json:
            from influxdb_client_3 import InfluxDBClient3
            client = InfluxDBClient3(host=influx_host, port=influx_port, database=db_name, token=auth_token)
            # query existing failures with active status
            query_string = (
                f"SELECT last(\"type_of\"),failure_type,object_ref,object_type,active "
                f"FROM \"failures\" WHERE (\"sys_id\" = '{sys_id}') "
                f"GROUP BY \"sys_name\", \"failure_type\"")
            query = client.query(query_string)
            if isinstance(query, list):
                failure_points = query
            elif isinstance(query, dict):
                failure_points = [query]
            elif isinstance(query, Iterable):
                try:
                    failure_points = list(query)
                except Exception as e:
                    LOG.error("InfluxDB query result not iterable: %s", e)
                    sys.exit(1)
            else:
                LOG.error("InfluxDB query result not iterable. Exiting.")
                sys.exit(1)
        else:
            # In JSON mode, just use empty failure_points (no DB query)
            failure_points = []

        # new failures
        for failure in failure_response:
            r_type = failure.get('failureType')
            r_ref = failure.get('objectRef')
            r_obj = failure.get('objectType')
            push = True
            p_active = None
            for point in failure_points:
                if (r_type == point.get('failure_type') and
                    r_ref == point.get('object_ref') and
                    r_obj == point.get('object_type')):
                    p_active = point.get('active')
                    if p_active == 'True':
                        push = False
                    break
            if push:
                item = create_failure_dict_item(sys_id, sys_name,
                                                r_type, r_ref, r_obj,
                                                True,
                                                datetime.now(timezone.utc).isoformat())
                json_body.append(item)
        # resolved failures
        for point in failure_points:
            if not point.get('active'):
                continue
            p_type = point.get('failure_type')
            p_ref = point.get('object_ref')
            p_obj = point.get('object_type')
            push = True
            for failure in failure_response:
                if (failure.get('failureType') == p_type and
                    failure.get('objectRef') == p_ref and
                    failure.get('objectType') == p_obj):
                    push = False
                    break
            if push:
                item = create_failure_dict_item(sys_id, sys_name,
                                                p_type, p_ref, p_obj,
                                                False,
                                                datetime.now(timezone.utc).isoformat())
                json_body.append(item)

        # Strict output: JSON or InfluxDB, never both
        if to_json:
            outdir = to_json
            os.makedirs(outdir, exist_ok=True)
            fname = get_json_output_path('system_failures', sys_id, outdir)
            
            LOG.info(f"[DEBUG] toJson is set: {outdir}")
            LOG.info(f"[DEBUG] About to write system failures to: {fname}")
            LOG.info(f"[DEBUG] Data preview (first 500 chars): {str(json_body)[:500]}")
            try:
                with open(fname, 'w') as f:
                    json.dump(json_body, f, indent=4)
                LOG.info(f"[DEBUG] Successfully wrote system failures to {fname}")
                
                # Save persistent checkpoint after successful JSON write
                if influx_client is not None:
                    save_system_failures_checkpoint(influx_client, sys_id, new_checksum, db_name)
                    
            except Exception as e:
                LOG.error(f"[CRITICAL] Failed to write system failures to {fname}: {e}")
                raise
        else:
            client.write(json_body, database=db_name, time_precision=INFLUXDB_WRITE_PRECISION)
            LOG.info("State metrics sent to InfluxDB")
    except Exception as e:
        # Even in exception handling, we prefer to use the actual WWN if available
        if sys_info and 'wwn' in sys_info and sys_info['wwn']:
            sys_id = sys_info['wwn']
        else:
            sys_id = "unknown"
        sys_name = sys_info.get('name', 'unknown')
        LOG.error("Error posting state info for %s/%s: %s", sys_name, sys_id, e)
