# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import json
import logging
from app.config import INFLUXDB_WRITE_PRECISION
from app.controllers import get_controller
from app.drives import get_drive_location
from app.metrics_config import DRIVE_PARAMS, INTERFACE_PARAMS, VOLUME_PARAMS
from app.utils import get_json_output_path

print("[STORAGE DIAG] storage.py module loaded")

LOG = logging.getLogger(__name__)

def collect_storage_metrics(sys_info, session, san_headers, api_endpoints, influx_host, influx_port, db_name, auth_token, flags, loop_iteration):
    """
    Collects storage metrics (drive, interface, system, volume) and writes to InfluxDB or JSON.
    :param sys_info: dict with 'wwn' and 'name'
    :param api_endpoints: list of SANtricity API endpoints
    :param influx_host: InfluxDB host URL
    :param influx_port: InfluxDB port
    :param db_name: InfluxDB database name
    :param auth_token: InfluxDB authentication token
    :param loop_iteration: current iteration count
    """
    print("[STORAGE DIAG] Entered collect_storage_metrics")
    LOG.info("[STORAGE] Entered collect_storage_metrics")
    def ensure_list_of_dicts(obj, label):
        """Ensure obj is a list of dicts. Log and skip non-dict items. Return empty list if not a list."""
        if not isinstance(obj, list):
            LOG.error(f"[STORAGE] {label} response is not a list: {obj}")
            return []
        filtered = []
        for i, item in enumerate(obj):
            if isinstance(item, dict):
                filtered.append(item)
            else:
                LOG.error(f"[STORAGE] {label} item at index {i} is not a dict: {item}")
        return filtered

    # Strict output mode: either JSON or InfluxDB, never both
    to_json = getattr(flags, 'toJson', None)
    if not to_json:
        from influxdb_client_3 import InfluxDBClient3
        client = InfluxDBClient3(host=influx_host, port=influx_port, database=db_name, token=auth_token)

    try:
        print("[STORAGE DIAG] Using session and Bearer token from main collector")
        session.headers.update(san_headers)
        print(f"[STORAGE DIAG] sys_info: {sys_info}")
        
        # Mandate WWN - it's essential for proper system identification
        if 'wwn' not in sys_info or not sys_info['wwn']:
            print("[STORAGE DIAG] ERROR: Missing or empty WWN in system info")
            LOG.error("[STORAGE] Missing or empty WWN in system info. WWN is mandatory for proper metrics collection.")
            return []
            
        sys_id = sys_info['wwn']
        print(f"[STORAGE DIAG] sys_id: {sys_id}")
        sys_name = sys_info['name']
        print(f"[STORAGE DIAG] sys_name: {sys_name}")
        json_body = []
        # Log loop iteration if present
        if hasattr(flags, 'loopIteration'):
            LOG.info(f"Loop iteration: {getattr(flags, 'loopIteration')}")

        print("[STORAGE DIAG] Before get_controller()")
        base = get_controller('sys', api_endpoints)
        print(f"[STORAGE DIAG] base: {base}")

        def log_api_call(resp, url, label):
            LOG.debug(f"[API-DEBUG] {label} request: GET {url}")
            LOG.debug(f"[API-DEBUG] {label} response: {resp.status_code} {resp.reason}")
            LOG.debug(f"[API-DEBUG] {label} response headers: {resp.headers}")
            LOG.debug(f"[API-DEBUG] {label} response body (first 500 chars): {resp.text[:500]}")

        # Drive (performance) statistics (as opposed to "drives" measurement which collects disks' properties and attributes)
        drive_url = f"{base}/{sys_id}/analysed-drive-statistics"
        print(f"[STORAGE DIAG] About to GET drive stats: {drive_url}")
        LOG.info(f"[STORAGE] GET {drive_url}")
        try:
            drive_resp = session.get(drive_url)
            print(f"[STORAGE DIAG] Got drive stats response: {drive_resp.status_code}")
            log_api_call(drive_resp, drive_url, "DriveStats")
            LOG.info(f"[STORAGE] Drive stats response: {drive_resp.status_code}")
            drive_stats = ensure_list_of_dicts(drive_resp.json(), "DriveStats")
            if len(drive_stats) == 0:
                LOG.warning("[STORAGE] Drive stats response is an empty list. This is normal if the system has not yet collected at least two statistics snapshots. See API docs for /analysed-drive-statistics.")
            LOG.info(f"[STORAGE] Drive stats count: {len(drive_stats)}")
        except Exception as e:
            print(f"[STORAGE DIAG] Exception fetching drive stats: {e}")
            LOG.error(f"[STORAGE] Error fetching drive stats: {e}")
            drive_stats = []

        drive_locations = get_drive_location(sys_id, session, san_headers, api_endpoints, loop_iteration, flags)
        print(f"[STORAGE DIAG] Got {len(drive_locations)} drive locations")
        for s in drive_stats:
            if not isinstance(s, dict):
                LOG.error(f"[STORAGE] Skipping non-dict drive stat: {s}")
                continue
            pdict = {}
            fields = {m: s.get(m) for m in DRIVE_PARAMS} | pdict
            tags = {'sys_id': sys_id, 'sys_name': sys_name}
            loc = drive_locations.get(s.get('diskId'))
            if loc:
                tags['sys_tray'], tags['sys_tray_slot'] = f"{loc[0]:02.0f}", f"{loc[1]:03.0f}"
            json_body.append({'measurement': 'disks', 'tags': tags, 'fields': fields})
        print(f"[STORAGE DIAG] Appended {len(drive_stats)} drive stats")
        LOG.info(f"[STORAGE] Appended {len(drive_stats)} drive stats")

        # Interface statistics
        intf_url = f"{base}/{sys_id}/analysed-interface-statistics"
        print(f"[STORAGE DIAG] About to GET interface stats: {intf_url}")
        LOG.info(f"[STORAGE] GET {intf_url}")
        try:
            intf_resp = session.get(intf_url)
            print(f"[STORAGE DIAG] Got interface stats response: {intf_resp.status_code}")
            log_api_call(intf_resp, intf_url, "InterfaceStats")
            LOG.info(f"[STORAGE] Interface stats response: {intf_resp.status_code}")
            intf_stats = ensure_list_of_dicts(intf_resp.json(), "InterfaceStats")
            if len(intf_stats) == 0:
                LOG.warning(f"[STORAGE] Interface stats response is an empty list.")
            LOG.info(f"[STORAGE] Interface stats count: {len(intf_stats)}")
        except Exception as e:
            print(f"[STORAGE DIAG] Exception fetching interface stats: {e}")
            LOG.error(f"[STORAGE] Error fetching interface stats: {e}")
            intf_stats = []
        for s in intf_stats:
            if not isinstance(s, dict):
                LOG.error(f"[STORAGE] Skipping non-dict interface stat: {s}")
                continue
            item = {
                'measurement': 'interface',
                'tags': {'sys_id': sys_id, 'sys_name': sys_name,
                         'interface_id': s.get('interfaceId'),
                         'channel_type': s.get('channelType')},
                'fields': {m: s.get(m) for m in INTERFACE_PARAMS}
            }
            json_body.append(item)
        print(f"[STORAGE DIAG] Appended {len(intf_stats)} interface stats")
        LOG.info(f"[STORAGE] Appended {len(intf_stats)} interface stats")

        # System statistics
        sys_url = f"{base}/{sys_id}/analysed-system-statistics"
        print(f"[STORAGE DIAG] About to GET system stats: {sys_url}")
        LOG.info(f"[STORAGE] GET {sys_url}")
        try:
            sys_resp = session.get(sys_url)
            print(f"[STORAGE DIAG] Got system stats response: {sys_resp.status_code}")
            log_api_call(sys_resp, sys_url, "SystemStats")
            LOG.info(f"[STORAGE] System stats response: {sys_resp.status_code}")
            sys_stats = sys_resp.json()
            if not isinstance(sys_stats, dict):
                LOG.error(f"[STORAGE] System stats response is not a dict: {sys_stats}")
                sys_stats = {}
            LOG.info(f"[STORAGE] System stats keys: {list(sys_stats.keys()) if isinstance(sys_stats, dict) else 'N/A'}")
        except Exception as e:
            print(f"[STORAGE DIAG] Exception fetching system stats: {e}")
            LOG.error(f"[STORAGE] Error fetching system stats: {e}")
            sys_stats = {}
        
        # Include all fields from the system stats response, not just those listed in SYSTEM_PARAMS
        system_fields = {}
        source_controller = None
        if isinstance(sys_stats, dict):
            # Extract sourceController for use as a tag
            source_controller = sys_stats.get('sourceController', 'unknown')
            # Include all fields from the response, excluding system identification fields
            system_fields = {k: v for k, v in sys_stats.items() 
                           if k not in ['storageSystemId', 'storageSystemWWN', 'storageSystemName', 'sourceController']}

        # Use sourceController as a tag for proper controller-level visibility despite this being overall system-level data
        system_tags = {
            'sys_id': sys_id, 
            'sys_name': sys_name,
            'source_controller': source_controller or 'unknown'
        }
        
        json_body.append({'measurement': 'systems',
                          'tags': system_tags,
                          'fields': system_fields})
        print(f"[STORAGE DIAG] Appended system stats")
        LOG.info(f"[STORAGE] Appended system stats")

        # Volume statistics
        vol_url = f"{base}/{sys_id}/analysed-volume-statistics"
        print(f"[STORAGE DIAG] About to GET volume stats: {vol_url}")
        LOG.info(f"[STORAGE] GET {vol_url}")
        try:
            vol_resp = session.get(vol_url)
            print(f"[STORAGE DIAG] Got volume stats response: {vol_resp.status_code}")
            log_api_call(vol_resp, vol_url, "VolumeStats")
            LOG.info(f"[STORAGE] Volume stats response: {vol_resp.status_code}")
            vol_stats = ensure_list_of_dicts(vol_resp.json(), "VolumeStats")
            if len(vol_stats) == 0:
                LOG.warning(f"[STORAGE] Volume stats response is an empty list.")
            LOG.info(f"[STORAGE] Volume stats count: {len(vol_stats)}")
        except Exception as e:
            print(f"[STORAGE DIAG] Exception fetching volume stats: {e}")
            LOG.error(f"[STORAGE] Error fetching volume stats: {e}")
            vol_stats = []
        for s in vol_stats:
            if not isinstance(s, dict):
                LOG.error(f"[STORAGE] Skipping non-dict volume stat: {s}")
                continue
            item = {'measurement': 'volumes',
                    'tags': {'sys_id': sys_id, 'sys_name': sys_name,
                             'vol_name': s.get('volumeName')},
                    'fields': {m: s.get(m) for m in VOLUME_PARAMS}}
            json_body.append(item)
        print(f"[STORAGE DIAG] Appended {len(vol_stats)} volume stats")
        LOG.info(f"[STORAGE] Appended {len(vol_stats)} volume stats")

        print(f"[STORAGE DIAG] Total metrics to write: {len(json_body)}")
        LOG.info(f"[STORAGE] Total metrics to write: {len(json_body)}")
        if json_body:
            print(f"[STORAGE DIAG] First metric: {json_body[0]}")
            LOG.info(f"[STORAGE] First metric: {json_body[0]}")
        else:
            print(f"[STORAGE DIAG] No metrics collected, nothing to write.")
            LOG.warning(f"[STORAGE] No metrics collected, nothing to write.")

        # Strict output: JSON or InfluxDB, never both
        if to_json:
            # Write to separate JSON files for each metric type
            # Create separate lists for each metric type
            drive_metrics = [item for item in json_body if item.get('measurement') == 'disks']
            interface_metrics = [item for item in json_body if item.get('measurement') == 'interface']
            system_metrics = [item for item in json_body if item.get('measurement') == 'systems']
            volume_metrics = [item for item in json_body if item.get('measurement') == 'volumes']
            # Controller(s) metrics are collected elsewhere 
            
            # Write drives to their own file
            if drive_metrics:
                drives_fname = get_json_output_path('drive', sys_id, to_json)
                try:
                    with open(drives_fname, 'w') as f:
                        json.dump(drive_metrics, f, indent=2)
                    LOG.info(f"Wrote {len(drive_metrics)} drive points to {drives_fname}")
                except Exception as e:
                    LOG.error(f"Failed to write {drives_fname}: {e}")
            
            # Write interfaces to their own file
            if interface_metrics:
                interfaces_fname = get_json_output_path('interface', sys_id, to_json)
                try:
                    with open(interfaces_fname, 'w') as f:
                        json.dump(interface_metrics, f, indent=2)
                    LOG.info(f"Wrote {len(interface_metrics)} interface points to {interfaces_fname}")
                except Exception as e:
                    LOG.error(f"Failed to write {interfaces_fname}: {e}")
            
            # Write system metrics to their own file
            if system_metrics:
                system_fname = get_json_output_path('system', sys_id, to_json)
                try:
                    with open(system_fname, 'w') as f:
                        json.dump(system_metrics, f, indent=2)
                    LOG.info(f"Wrote {len(system_metrics)} system points to {system_fname}")
                except Exception as e:
                    LOG.error(f"Failed to write {system_fname}: {e}")
            
            # Write volume metrics to their own file
            if volume_metrics:
                volumes_fname = get_json_output_path('volume', sys_id, to_json)
                try:
                    with open(volumes_fname, 'w') as f:
                        json.dump(volume_metrics, f, indent=2)
                    LOG.info(f"Wrote {len(volume_metrics)} volume points to {volumes_fname}")
                except Exception as e:
                    LOG.error(f"Failed to write {volumes_fname}: {e}")
                    
            # Also write complete combined metrics for backward compatibility
            fname = get_json_output_path('storage', sys_id, to_json)
            try:
                with open(fname, 'w') as f:
                    json.dump(json_body, f, indent=2)
                LOG.info(f"Wrote {len(json_body)} total points to {fname}")
            except Exception as e:
                LOG.error(f"Failed to write {fname}: {e}")
        else:
            # Write to InfluxDB only
            try:
                if not to_json:
                    client.write(json_body, database=db_name, time_precision=INFLUXDB_WRITE_PRECISION)
                    LOG.info(f"Wrote {len(json_body)} points to InfluxDB database {db_name}")
                else:
                    LOG.warning("Attempted to write to InfluxDB in JSON mode - this should not happen")
            except Exception as e:
                LOG.error(f"Failed to write to InfluxDB: {e}")
    except Exception as e:
        print(f"[STORAGE DIAG] UNEXPECTED EXCEPTION: {e}")
        LOG.error(f"[STORAGE] UNEXPECTED EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return
print("[STORAGE DIAG] storage.py module end")
