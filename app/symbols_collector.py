# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

import json
import logging
from app.controllers import get_controller
from app.utils import order_sensor_response_list, get_json_output_path

LOG = logging.getLogger(__name__)

def collect_symbol_stats(sys_info, session, san_headers, api_endpoints, database_client, db_name, flags, loop_iteration):
    """
    Collects PSU power and thermal sensor metrics and posts them to InfluxDB or writes to JSON.
    :param sys_info: dict with 'wwn' and 'name'
    :param api_endpoints: list of SANtricity API endpoints
    :param database_client: DatabaseClient instance for InfluxDB writes
    :param db_name: InfluxDB database name
    :param flags: Configuration flags object
    :param loop_iteration: current iteration count (unused in this function)
    """
    LOG.info("[SYMBOLS] Entered collect_symbol_stats")
    # Strict output mode: either JSON or InfluxDB, never both
    to_json = getattr(flags, 'toJson', None)
    
    # Mandate WWN - it's essential for proper system identification
    if 'wwn' not in sys_info or not sys_info['wwn']:
        LOG.error("[SYMBOLS] Missing or empty WWN in system info. WWN is mandatory for proper metrics collection.")
        return []
        
    sys_id = sys_info['wwn']
    sys_name = sys_info['name']
    json_body = []

    # PSU metrics
    try:
        psu_url = f"{get_controller('sys', api_endpoints)}/{sys_id}/symbol/getEnergyStarData"
        psu_params = {"controller": "auto", "verboseErrorResponse": "false"}
        LOG.info(f"[SYMBOLS] GET {psu_url} params={psu_params}")
        psu_resp = session.get(
            psu_url,
            params=psu_params,
            timeout=(6.10, flags.intervalTime * 2),
            headers=san_headers
        )
        LOG.info(f"[SYMBOLS] PSU response: {psu_resp.status_code} {psu_resp.reason}")
        LOG.info(f"[SYMBOLS] PSU response headers: {psu_resp.headers}")
        try:
            psu_response = psu_resp.json()
        except Exception as e:
            LOG.error("[SYMBOLS] PSU response not JSON: %s", e)
            psu_response = None
        if not psu_response:
            LOG.warning("[SYMBOLS] PSU response is None or empty.")
        elif isinstance(psu_response, list) and len(psu_response) == 0:
            LOG.warning("[SYMBOLS] PSU response is an empty list. This may be normal if no PSU data is available yet.")
        else:
            # Robustly handle dict or list response as both have been seen in various API versions
            if isinstance(psu_response, dict):
                energy = psu_response.get('energyStarData', {})
            elif isinstance(psu_response, list) and len(psu_response) > 0 and isinstance(psu_response[0], dict):
                energy = psu_response[0].get('energyStarData', {})
            else:
                energy = {}
            
            # Check returnCode for system status
            return_code = psu_response.get('returnCode', 'unknown') if isinstance(psu_response, dict) else 'unknown'
            LOG.info(f"[SYMBOLS] PSU returnCode: {return_code}")
            
            fields = {}
            # Always include totalPower, even if 0 (impossible)
            total_power = energy.get('totalPower', 0)
            fields['totalPower'] = total_power
            LOG.info(f"[SYMBOLS] Total power: {total_power}W")
            
            # Handle variable number of trays (shelves) and PSUs per tray
            tray_power = energy.get('trayPower', [])
            num_trays = energy.get('numberOfTrays', 0)
            LOG.info(f"[SYMBOLS] Number of trays: {num_trays}, trayPower entries: {len(tray_power) if isinstance(tray_power, list) else 0}")
            
            if isinstance(tray_power, list) and tray_power:
                total_calculated_power = 0
                for tray in tray_power:
                    if not isinstance(tray, dict):
                        LOG.warning(f"[SYMBOLS] Skipping non-dict tray entry: {tray}")
                        continue
                        
                    tray_id = tray.get('trayID', 'unknown')
                    num_psus = tray.get('numberOfPowerSupplies', 0)
                    input_power = tray.get('inputPower', [])
                    
                    LOG.info(f"[SYMBOLS] Tray {tray_id}: {num_psus} PSUs, inputPower array length: {len(input_power) if isinstance(input_power, list) else 0}")
                    
                    if isinstance(input_power, list):
                        tray_total = 0
                        for idx, val in enumerate(input_power):
                            # Handle case where PSU value might be None or non-numeric
                            try:
                                psu_power = float(val) if val is not None else 0
                                fields[f'tray{tray_id}_psu{idx}_inputPower'] = psu_power
                                tray_total += psu_power
                                LOG.debug(f"[SYMBOLS] Tray {tray_id} PSU {idx}: {psu_power}W")
                            except (ValueError, TypeError) as e:
                                LOG.warning(f"[SYMBOLS] Invalid PSU power value for tray {tray_id} PSU {idx}: {val} - {e}")
                                fields[f'tray{tray_id}_psu{idx}_inputPower'] = 0
                        
                        fields[f'tray{tray_id}_totalPower'] = tray_total
                        total_calculated_power += tray_total
                        LOG.info(f"[SYMBOLS] Tray {tray_id} total: {tray_total}W")
                    else:
                        LOG.warning(f"[SYMBOLS] Tray {tray_id} inputPower is not a list: {input_power}")
                
                fields['calculatedTotalPower'] = total_calculated_power
                LOG.info(f"[SYMBOLS] Calculated total power: {total_calculated_power}W (vs reported: {total_power}W)")
                
                # Add validation field to track data quality
                power_diff = abs(total_calculated_power - total_power) if total_power > 0 else 0
                fields['powerValidation'] = 'ok' if power_diff <= 5 else 'mismatch'  # Allow 5W tolerance
            else:
                LOG.warning(f"[SYMBOLS] No valid tray power data found")
                fields['powerValidation'] = 'no_data'
            
            # Add system status fields for monitoring
            fields['numberOfTrays'] = num_trays
            fields['returnCode'] = return_code
            
            item = {
                'measurement': 'power',
                'tags': {'sys_id': sys_id, 'sys_name': sys_name, 'return_code': return_code},
                'fields': fields
            }
            json_body.append(item)
    except Exception as e:
        LOG.error("Error collecting PSU data: %s", e)

    # Temperature sensors
    try:
        temp_url = f"{get_controller('sys', api_endpoints)}/{sys_id}/symbol/getEnclosureTemperatures"
        temp_params = {"controller": "auto", "verboseErrorResponse": "false"}
        LOG.info(f"[SYMBOLS] GET {temp_url} params={temp_params}")
        temp_resp = session.get(
            temp_url,
            params=temp_params,
            timeout=(6.10, flags.intervalTime * 2),
            headers=san_headers
        )
        LOG.info(f"[SYMBOLS] Temp response: {temp_resp.status_code} {temp_resp.reason}")
        LOG.info(f"[SYMBOLS] Temp response headers: {temp_resp.headers}")
        try:
            temp_response = temp_resp.json()
        except Exception as e:
            LOG.error("[SYMBOLS] Temp response not JSON: %s", e)
            temp_response = None
        if not temp_response:
            LOG.warning("[SYMBOLS] Temp response is None or empty.")
            sensors = []
        elif isinstance(temp_response, list) and len(temp_response) == 0:
            LOG.warning("[SYMBOLS] Temp response is an empty list. This may be normal if no temperature data is available yet.")
            sensors = []
        else:
            # Check returnCode for system status
            return_code = temp_response.get('returnCode', 'unknown') if isinstance(temp_response, dict) else 'unknown'
            LOG.info(f"[SYMBOLS] Temperature returnCode: {return_code}")
            
            # Handle variable sensor data formats
            if isinstance(temp_response, dict):
                raw_sensors = temp_response.get('thermalSensorData', [])
            elif isinstance(temp_response, list):
                # Some arrays might return sensor data directly as a list
                raw_sensors = temp_response
            else:
                raw_sensors = []
            
            if not isinstance(raw_sensors, list):
                LOG.warning(f"[SYMBOLS] thermalSensorData is not a list: {type(raw_sensors)}")
                sensors = []
            else:
                # Use the enhanced order_sensor_response_list function that handles both dict/list formats
                try:
                    sensors = order_sensor_response_list(temp_response)
                    LOG.info(f"[SYMBOLS] Successfully ordered {len(sensors)} temperature sensors")
                except Exception as e:
                    LOG.error(f"[SYMBOLS] Error ordering sensor response: {e}")
                    # Fallback to raw sensor data if ordering fails
                    sensors = raw_sensors
            
            if len(sensors) == 0:
                LOG.warning("[SYMBOLS] No thermal sensor data found. This may be normal for systems without temperature monitoring.")
            else:
                LOG.info(f"[SYMBOLS] Processing {len(sensors)} temperature sensors")
        
        # Process sensors with enhanced error handling
        valid_sensors = 0
        for idx, sensor in enumerate(sensors):
            if not isinstance(sensor, dict):
                LOG.warning(f"[SYMBOLS] Skipping non-dict sensor at index {idx}: {sensor}")
                continue
                
            sensor_ref = sensor.get('thermalSensorRef', f'unknown_sensor_{idx}')
            current_temp = sensor.get('currentTemp')
            
            # Validate temperature reading
            try:
                if current_temp is not None:
                    temp_value = float(current_temp)
                    # Sanity check: typical data center temps are -40 to +100°C
                    if temp_value < -50 or temp_value > 150:
                        LOG.warning(f"[SYMBOLS] Unusual temperature reading for sensor {sensor_ref}: {temp_value}°C")
                else:
                    temp_value = None
                    LOG.warning(f"[SYMBOLS] No temperature reading for sensor {sensor_ref}")
            except (ValueError, TypeError) as e:
                LOG.warning(f"[SYMBOLS] Invalid temperature value for sensor {sensor_ref}: {current_temp} - {e}")
                temp_value = None
            
            # Sensor type classification based on field observations from E-Series arrays
            # Reference: https://scaleoutsean.github.io/2023/02/18/epa-eseries-monitor-sensors-psu-power-consumption.html
            # sensor_1 & sensor_3: CPU temperatures (40-80°C typical)
            # sensor_2 & sensor_4: Inlet temperature status (128 = normal, non-128 = abnormal)
            # sensor_5 & sensor_6: PSU temperatures (slightly above room temp, ~30°C)
            # Note: sensor_0 pattern varies and needs more field data
            sensor_type = 'unknown'
            status_indicator = None
            
            if temp_value is not None:
                if idx in [1, 3]:  # CPU temperature sensors
                    if 30 <= temp_value <= 90:
                        sensor_type = 'cpu_temp'
                        LOG.debug(f"[SYMBOLS] Sensor {sensor_ref} classified as CPU temp ({temp_value}°C)")
                    else:
                        sensor_type = 'cpu_temp'  # Still CPU sensor, but unusual reading
                        LOG.warning(f"[SYMBOLS] Unusual CPU temperature for sensor {sensor_ref}: {temp_value}°C")
                        
                elif idx in [2, 4]:  # Inlet temperature status indicators
                    if temp_value == 128:
                        sensor_type = 'inlet_status'
                        status_indicator = 'normal'
                        LOG.debug(f"[SYMBOLS] Sensor {sensor_ref} inlet status: NORMAL (128)")
                    else:
                        sensor_type = 'inlet_status'
                        status_indicator = 'abnormal'
                        LOG.warning(f"[SYMBOLS] Sensor {sensor_ref} inlet status: ABNORMAL ({temp_value})")
                        
                elif idx in [5, 6]:  # PSU temperature sensors
                    if 20 <= temp_value <= 50:
                        sensor_type = 'psu_temp'
                        LOG.debug(f"[SYMBOLS] Sensor {sensor_ref} classified as PSU temp ({temp_value}°C)")
                    else:
                        sensor_type = 'psu_temp'  # Still PSU sensor, but unusual reading
                        LOG.warning(f"[SYMBOLS] Unusual PSU temperature for sensor {sensor_ref}: {temp_value}°C")
                        
                elif idx == 0:  # sensor_0 pattern varies by hardware
                    if 30 <= temp_value <= 90:
                        sensor_type = 'cpu_temp'  # Possibly another CPU temp
                        LOG.debug(f"[SYMBOLS] Sensor {sensor_ref} (sensor_0) classified as CPU temp ({temp_value}°C)")
                    elif temp_value == 128:
                        sensor_type = 'status_indicator'
                        status_indicator = 'normal'
                        LOG.debug(f"[SYMBOLS] Sensor {sensor_ref} (sensor_0) status indicator: NORMAL")
                    else:
                        sensor_type = 'unknown'
                        LOG.warning(f"[SYMBOLS] Sensor {sensor_ref} (sensor_0) unknown pattern: {temp_value}°C")

                else:  # Higher index sensors - likely additional ambient/PSU sensors. Some guessing involved...
                    if 15 <= temp_value <= 50:
                        sensor_type = 'ambient'
                        LOG.debug(f"[SYMBOLS] Sensor {sensor_ref} (sensor_{idx}) classified as ambient temp ({temp_value}°C)")
                    elif temp_value == 128:
                        sensor_type = 'status_indicator'
                        status_indicator = 'normal'
                        LOG.debug(f"[SYMBOLS] Sensor {sensor_ref} (sensor_{idx}) status indicator: NORMAL")
                    else:
                        sensor_type = 'unknown'
                        LOG.warning(f"[SYMBOLS] Sensor {sensor_ref} (sensor_{idx}) unknown pattern: {temp_value}°C")
            
            LOG.info(f"[SYMBOLS] Sensor classification: {sensor_ref} = {sensor_type}" + 
                    (f" (status: {status_indicator})" if status_indicator else ""))
            
            item = {
                'measurement': 'temp',
                'tags': {
                    'sensor_ref': sensor_ref,
                    'sensor_seq': f"sensor_{idx}",
                    'sensor_type': sensor_type,  # cpu_temp, inlet_status, psu_temp, ambient, status_indicator, unknown
                    'sys_id': sys_id,
                    'sys_name': sys_name,
                    'sensor_status': 'ok' if temp_value is not None else 'no_data'
                },
                'fields': {
                    'temp': temp_value,
                    'sensor_index': idx,  # For debugging/monitoring sensor order changes
                    # Only include status_indicator if it's not None
                    **({"status_indicator": status_indicator} if status_indicator is not None else {})
                }
            }
            json_body.append(item)
            if temp_value is not None:
                valid_sensors += 1
        
        LOG.info(f"[SYMBOLS] Processed {len(sensors)} sensors, {valid_sensors} with valid readings")
    except Exception as e:
        LOG.error("Error collecting sensor data: %s", e)

    # Output
    LOG.info(f"[SYMBOLS] Returning {len(json_body)} symbol stats items")
    # Strict output: JSON or InfluxDB, never both
    if to_json:
        # Separate power and temperature metrics
        power_metrics = [item for item in json_body if item.get('measurement') == 'power']
        temp_metrics = [item for item in json_body if item.get('measurement') == 'temp']
        
        # Write power metrics to their own file
        if power_metrics:
            power_fname = get_json_output_path('power', sys_id, to_json)
            try:
                with open(power_fname, 'w') as f:
                    json.dump(power_metrics, f, indent=2)
                LOG.info(f"[SYMBOLS] Wrote {len(power_metrics)} power points to {power_fname}")
            except Exception as e:
                LOG.error(f"[SYMBOLS] Failed to write {power_fname}: {e}")
        
        # Write temperature metrics to their own file
        if temp_metrics:
            temp_fname = get_json_output_path('temp', sys_id, to_json)
            try:
                with open(temp_fname, 'w') as f:
                    json.dump(temp_metrics, f, indent=2)
                LOG.info(f"[SYMBOLS] Wrote {len(temp_metrics)} temperature points to {temp_fname}")
            except Exception as e:
                LOG.error(f"[SYMBOLS] Failed to write {temp_fname}: {e}")
    else:
        try:
            if not to_json:
                database_client.write(json_body)
                LOG.info(f"Wrote {len(json_body)} points to InfluxDB database {db_name}")
            else:
                LOG.warning("Attempted to write to InfluxDB in JSON mode - this should not happen")
        except Exception as e:
            LOG.error(f"Failed to write to InfluxDB: {e}")
    return json_body
