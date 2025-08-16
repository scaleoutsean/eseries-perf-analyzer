# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import json
import logging
import sys
import hashlib
import os
import pickle
from datetime import datetime, timezone
from collections.abc import Iterable
from app.config import INFLUXDB_WRITE_PRECISION
from app.connection import get_session
from app.controllers import get_controller
from app.utils import get_json_output_path
from app.metrics_config import MEL_PARAMS

LOG = logging.getLogger(__name__)

def load_mel_checkpoint(influx_client, sys_id):
    """Load MEL checkpoint from InfluxDB using a simple file-based fallback"""
    # For now, use a simple file-based approach until we can verify InfluxDB v3 availability
    checkpoint_file = f"/tmp/mel_checkpoint_{sys_id}.json"
    try:
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r') as f:
                data = json.load(f)
                return {
                    'last_sequence_id': data.get('last_sequence_id', -1),
                    'content_checksum': data.get('content_checksum', '')
                }
    except Exception as e:
        LOG.warning(f"Could not load MEL checkpoint for {sys_id}: {e}")
    
    return {'last_sequence_id': -1, 'content_checksum': ''}

def save_mel_checkpoint(influx_client, sys_id, sequence_id, checksum, db_name):
    """Save MEL checkpoint using both InfluxDB and file-based backup"""
    # Save to InfluxDB for metrics/monitoring
    try:
        checkpoint_data = [{
            'measurement': 'mel_checkpoint',
            'tags': {
                'sys_id': sys_id
            },
            'fields': {
                'last_sequence_id': int(sequence_id),
                'content_checksum': str(checksum)
            },
            'time': datetime.now(timezone.utc).isoformat()
        }]
        influx_client.write(checkpoint_data, database=db_name, time_precision=INFLUXDB_WRITE_PRECISION)
        LOG.debug(f"Saved MEL checkpoint to InfluxDB for {sys_id}: seq={sequence_id}")
    except Exception as e:
        LOG.warning(f"Could not save MEL checkpoint to InfluxDB for {sys_id}: {e}")
    
    # Save to local file as backup/primary storage until InfluxDB query works reliably
    try:
        checkpoint_file = f"/tmp/mel_checkpoint_{sys_id}.json"
        checkpoint_data = {
            'last_sequence_id': int(sequence_id),
            'content_checksum': str(checksum),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        with open(checkpoint_file, 'w') as f:
            json.dump(checkpoint_data, f)
        LOG.debug(f"Saved MEL checkpoint to file for {sys_id}: seq={sequence_id}")
    except Exception as e:
        LOG.error(f"Could not save MEL checkpoint to file for {sys_id}: {e}")

def collect_major_event_log(sys_info, session, san_headers, api_endpoints, influx_host, influx_port, db_name, auth_token, flags, checksums=None, influx_client=None):
    """
    Collects all defined MEL metrics and posts them to InfluxDB or writes to JSON.
    :param sys_info: dict with 'wwn' and 'name'
    :param api_endpoints: list of SANtricity API endpoints
    :param influx_host: InfluxDB host URL
    :param influx_port: InfluxDB port
    :param db_name: InfluxDB database name
    :param auth_token: InfluxDB auth token
    """
    # Strict output mode: either JSON or InfluxDB, never both
    to_json = getattr(flags, 'toJson', None)
    
    # Mandate WWN - it's essential for proper system system identification
    if 'wwn' not in sys_info or not sys_info['wwn']:
        LOG.error("[EVENTS] Missing or empty WWN in system info. WWN is mandatory for proper metrics collection.")
        return []
        
    sys_id = sys_info['wwn']
    sys_name = sys_info['name']
    json_body = []
    start_from = -1
    mel_grab_count = 8192

    if not to_json:
        from influxdb_client_3 import InfluxDBClient3
        client = InfluxDBClient3(host=influx_host, port=influx_port, database=db_name, token=auth_token)
        # Query last ID from InfluxDB
        result = client.query(f"SELECT id FROM major_event_log WHERE sys_id='{sys_id}' ORDER BY time DESC LIMIT 1")
        try:
            if isinstance(result, list):
                lst = result
            elif isinstance(result, dict):
                lst = [result]
            elif isinstance(result, Iterable) and not isinstance(result, (str, bytes, dict)):
                lst = list(result)
            else:
                raise TypeError("Query result is not iterable")
        except Exception as e:
            LOG.error("Query result is not iterable. Exiting. Error: %s", e)
            sys.exit(1)
        if lst:
            start_from = int(lst[0].get('id', -1)) + 1

    # In JSON mode, just start from -1 (all events) which makes the first JSON / write to InfluxDB big
    # and subsequent smaller as long as checkpointing works or EPA Collector is not restarted
    base = get_controller('sys', api_endpoints)
    mel_response = session.get(
        f"{base}/{sys_id}/mel-events",
        params={"count": mel_grab_count, "startSequenceNumber": start_from},
        timeout=(6.10, flags.intervalTime * 2),
        headers=san_headers
    ).json()
    
    # Initialize variables for checkpoint tracking
    max_sequence_id = -1
    new_checksum = None
    
    # For JSON mode with InfluxDB available, use InfluxDB checkpoint for better persistence
    # For JSON mode without InfluxDB, fall back to simple duplicate detection
    if to_json and influx_client is not None:
        print(f"[MEL DIAG] Using InfluxDB checkpoint for sys_id: {sys_id}")
        # Load MEL checkpoint from InfluxDB
        checkpoint = load_mel_checkpoint(influx_client, sys_id)
        old_checksum = checkpoint['content_checksum']
        new_checksum = hashlib.md5(str(mel_response).encode("utf-8")).hexdigest()
        
        print(f"[MEL DIAG] old_checksum: {old_checksum}")
        print(f"[MEL DIAG] new_checksum: {new_checksum}")
        print(f"[MEL DIAG] checksums match: {old_checksum and str(new_checksum) == str(old_checksum)}")
        
        if old_checksum and str(new_checksum) == str(old_checksum):
            print(f"[MEL DIAG] SKIPPING: MEL content unchanged for system {sys_id}")
            LOG.info("MEL content unchanged for system %s (InfluxDB checkpoint), skipping JSON write", sys_id)
            return
        else:
            print(f"[MEL DIAG] PROCEEDING: MEL content changed, will write JSON")
        
        # Find the highest sequence ID from this response for checkpoint
        if mel_response:
            max_sequence_id = max(int(mel.get('sequenceNumber', -1)) for mel in mel_response)
            print(f"[MEL DIAG] max_sequence_id: {max_sequence_id}")
            
    elif to_json:
        # JSON mode - use file-based checkpointing
        print(f"[MEL DIAG] JSON mode - using file-based checkpointing")
        LOG.info("JSON mode - using file-based checkpointing")
        
        # Load existing checkpoint from file
        checkpoint_file = f"{to_json}/mel_checkpoint_{sys_id}.json"
        previous_checksum = None
        try:
            if os.path.exists(checkpoint_file):
                with open(checkpoint_file, 'r') as f:
                    checkpoint_data = json.load(f)
                    previous_checksum = checkpoint_data.get('checksum')
                    print(f"[MEL DIAG] Loaded previous checksum from file: {previous_checksum}")
        except Exception as e:
            print(f"[MEL DIAG] Failed to load checkpoint file: {e}")
            LOG.warning(f"Failed to load MEL checkpoint file: {e}")
        
        # Calculate current checksum
        new_checksum = hashlib.md5(str(mel_response).encode("utf-8")).hexdigest()
        print(f"[MEL DIAG] Current checksum: {new_checksum}")
        
        # Check if content has changed
        if previous_checksum == new_checksum:
            print(f"[MEL DIAG] SKIPPING: MEL content unchanged (file checkpoint), skipping JSON write")
            LOG.info("MEL content unchanged for system %s (file checkpoint), skipping JSON write", sys_id)
            return
        else:
            print(f"[MEL DIAG] PROCEEDING: MEL content changed, will write JSON")
        
        # Find the highest sequence ID from this response for checkpoint
        if mel_response:
            max_sequence_id = max(int(mel.get('sequenceNumber', -1)) for mel in mel_response)
    
    for mel in mel_response:
        item = {
            'measurement': 'major_event_log',
            'tags': {
                'sys_id': sys_id,
                'sys_name': sys_name,
                'event_type': mel.get('eventType'),
                'time_stamp': mel.get('timeStamp'),
                'category': mel.get('category'),
                'priority': mel.get('priority'),
                'critical': mel.get('critical'),
                'ascq': mel.get('ascq'),
                'asc': mel.get('asc')
            },
            'fields': {metric: mel.get(metric) for metric in MEL_PARAMS},
            'time': datetime.fromtimestamp(int(mel.get('timeStamp', 0)), timezone.utc).isoformat()
        }
        json_body.append(item)
    LOG.info("DEBUG: collect_major_event_log built %d MEL items", len(json_body))

    # Strict output: JSON or InfluxDB, never both
    if to_json:
        outdir = to_json
        os.makedirs(outdir, exist_ok=True)
        filename = get_json_output_path('mel', sys_id, outdir)
        with open(filename, 'w') as f:
            json.dump(json_body, f, indent=4)
        LOG.info("MEL JSON written to %s", filename)
        
        # Save checkpoint after successful JSON write
        if influx_client is not None and new_checksum is not None and max_sequence_id >= 0:
            # InfluxDB checkpoint
            save_mel_checkpoint(influx_client, sys_id, max_sequence_id, new_checksum, db_name)
        elif new_checksum is not None and max_sequence_id >= 0:
            # File-based checkpoint for JSON-only mode
            checkpoint_file = f"{to_json}/mel_checkpoint_{sys_id}.json"
            try:
                checkpoint_data = {
                    'checksum': new_checksum,
                    'max_sequence_id': max_sequence_id,
                    'last_updated': datetime.now(timezone.utc).isoformat()
                }
                with open(checkpoint_file, 'w') as f:
                    json.dump(checkpoint_data, f, indent=2)
                print(f"[MEL DIAG] Saved checkpoint to file: {checkpoint_file}")
                LOG.info(f"Saved MEL checkpoint to file: {checkpoint_file}")
            except Exception as e:
                print(f"[MEL DIAG] Failed to save checkpoint file: {e}")
                LOG.error(f"Failed to save MEL checkpoint file: {e}")
            
    else:
        client.write(json_body, database=db_name, time_precision=INFLUXDB_WRITE_PRECISION)
        LOG.info("MEL payload sent to InfluxDB")
