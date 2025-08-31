#!/usr/bin/env python3
"""
Retrieves and collects data from the the NetApp E-Series API server
and sends the data to an InfluxDB server
"""
import argparse
import concurrent.futures
import hashlib
import logging
import random
import sys
import time
from datetime import datetime, timezone

import requests
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError

DEFAULT_USERNAME = 'monitor'
DEFAULT_PASSWORD = 'monitor123'

DEFAULT_SYSTEM_NAME = ''
DEFAULT_SYSTEM_ID = ''
DEFAULT_SYSTEM_API_IP = ''

DEFAULT_SYSTEM_PORT = '8443'

INFLUXDB_HOSTNAME = 'influxdb'
INFLUXDB_PORT = 8086
INFLUXDB_DATABASE = 'eseries'
DEFAULT_RETENTION = '52w'  # 1y

__version__ = '1.0'

#######################
# LIST OF METRICS #####
#######################

CONTROLLER_PARAMS = [
    "observedTime",
    "observedTimeInMS",
    "readIOps",
    "writeIOps",
    "otherIOps",
    "combinedIOps",
    "readThroughput",
    "writeThroughput",
    "combinedThroughput",
    "readResponseTime",
    "readResponseTimeStdDev",
    "writeResponseTime",
    "writeResponseTimeStdDev",
    "combinedResponseTime",
    "combinedResponseTimeStdDev",
    "averageReadOpSize",
    "averageWriteOpSize",
    "readOps",
    "writeOps",
    "readPhysicalIOps",
    "writePhysicalIOps",
    "controllerId",
    "cacheHitBytesPercent",
    "randomIosPercent",
    "mirrorBytesPercent",
    "fullStripeWritesBytesPercent",
    "maxCpuUtilization",
    "maxCpuUtilizationPerCore",
    "cpuAvgUtilization",
    "cpuAvgUtilizationPerCore",
    "cpuAvgUtilizationPerCoreStdDev",
    "raid0BytesPercent",
    "raid1BytesPercent",
    "raid5BytesPercent",
    "raid6BytesPercent",
    "ddpBytesPercent",
    "readHitResponseTime",
    "readHitResponseTimeStdDev",
    "writeHitResponseTime",
    "writeHitResponseTimeStdDev",
    "combinedHitResponseTime",
    "combinedHitResponseTimeStdDev"
]

DRIVE_PARAMS = [
    'averageReadOpSize',
    'averageWriteOpSize',
    'combinedIOps',
    'combinedResponseTime',
    'combinedThroughput',
    'otherIOps',
    'readIOps',
    'readOps',
    'readPhysicalIOps',
    'readResponseTime',
    'readThroughput',
    'writeIOps',
    'writeOps',
    'writePhysicalIOps',
    'writeResponseTime',
    'writeThroughput',
    'spareBlocksRemainingPercent',
    'percentEnduranceUsed'
]

INTERFACE_PARAMS = [
    "readIOps",
    "writeIOps",
    "otherIOps",
    "combinedIOps",
    "readThroughput",
    "writeThroughput",
    "combinedThroughput",
    "readResponseTime",
    "writeResponseTime",
    "combinedResponseTime",
    "averageReadOpSize",
    "averageWriteOpSize",
    "readOps",
    "writeOps",
    "queueDepthTotal",
    "queueDepthMax",
    "channelErrorCounts"
]

SYSTEM_PARAMS = [
    "maxCpuUtilization",
    "cpuAvgUtilization"
]

VOLUME_PARAMS = [
    'averageReadOpSize',
    'averageWriteOpSize',
    'combinedIOps',
    'combinedResponseTime',
    'combinedThroughput',
    'flashCacheHitPct',
    'flashCacheReadHitBytes',
    'flashCacheReadHitOps',
    'flashCacheReadResponseTime',
    'flashCacheReadThroughput',
    'otherIOps',
    'queueDepthMax',
    'queueDepthTotal',
    'readCacheUtilization',
    'readHitBytes',
    'readHitOps',
    'readIOps',
    'readOps',
    'readPhysicalIOps',
    'readResponseTime',
    'readThroughput',
    'writeCacheUtilization',
    'writeHitBytes',
    'writeHitOps',
    'writeIOps',
    'writeOps',
    'writePhysicalIOps',
    'writeResponseTime',
    'writeThroughput'
]

MEL_PARAMS = [
    'id',
    'description',
    'location'
]

SENSOR_PARAMS = [
    'temp'
]

PSU_PARAMS = [
    'totalPower'
]

CONFIG_VOLUME_PARAMS = [
    # Fields from config_volumes.metrics file
    'blockSize',
    'capacity', 
    'segmentSize',
    'totalSizeInBytes',
    'usableCapacity',
    'reserved1',
    'reserved2',
    'flashCached',
    'preReadRedundancyCheckEnabled',
    'protectionInformationCapable',
    'protectionType',
    'repositoryCapacity',
    'dssMaxSegmentSize',
    'dssPreReadRedundancyCheckEnabled',
    'dssWriteCacheEnabled'
]

CONFIG_HOSTS_PARAMS = [
    # Host configuration boolean flags
    'isSAControlled',
    'confirmLUNMappingCreation',
    'protectionInformationCapableAccessMethod',
    'isLargeBlockFormatHost',
    'isLun0Restricted',
    # Host type and counts
    'hostTypeIndex',
    'initiatorCount',
    'hostSidePortCount',
    # Flattened first initiator data (for primary initiator info)
    'initiators_first_initiatorRef',
    'initiators_first_nodeName_ioInterfaceType',
    'initiators_first_nodeName_iscsiNodeName',
    'initiators_first_nodeName_remoteNodeWWN',
    'initiators_first_nodeName_nvmeNodeName',
    'initiators_first_label',
    'initiators_first_hostRef',
    'initiators_first_initiatorInactive',
    'initiators_first_initiatorNodeName_interfaceType',
    'initiators_first_id',
    # Flattened first host-side port data  
    'hostSidePorts_first_type',
    'hostSidePorts_first_mtpIoInterfaceType',
    'hostSidePorts_first_id'
]

CONFIG_STORAGE_POOLS_PARAMS = [
    # Basic pool metrics
    'sequenceNum',
    'offline',
    'raidLevel',
    'raidStatus', 
    'state',
    'drivePhysicalType',
    'driveMediaType',
    'spindleSpeedMatch',
    'isInaccessible',
    'drawerLossProtection',
    'protectionInformationCapable',
    'reservedSpaceAllocated',
    'diskPool',
    # Capacity fields (large integers)
    'usedSpace',
    'totalRaidedSpace',
    'freeSpace',
    # Block size fields
    'blkSizeRecommended',
    # Flattened blkSizeSupported (boolean for each supported size)
    'blkSizeSupported_512',
    'blkSizeSupported_4096',
    # Flattened volumeGroupData
    'volumeGroupData_type',
    # Flattened extents summary (from first extent)
    'extents_rawCapacity',
    'extents_raidLevel'
]

CONFIG_DRIVE_PARAMS = [
    # Tags (for identity and filtering)
    'driveRef',
    'serialNumber',
    'productID',
    'driveMediaType',
    'physicalLocation__trayRef',
    'physicalLocation_slot',
    # Fields (metrics, booleans, status, etc.)
    'available',
    'cause',
    'currentVolumeGroupRef',
    'driveTemperature_currentTemp',
    'hasDegradedChannel',
    'hotSpare',
    'id',
    # Explicit interfaceType deviceName fields for each type
    'interfaceType_sas_deviceName',
    'interfaceType_nvme_deviceName',
    'interfaceType_fibre_deviceName',
    'interfaceType_scsi_deviceName',
    'invalidDriveData',
    'manufacturer',
    'offline',
    'pfa',
    'pfaReason',
    'rawCapacity',
    'removed',
    'sparedForDriveRef',
    'status',
    'uncertified',
    'usableCapacity',
    'volumeGroupIndex',
    'worldWideName',
]

#######################
# GLOBAL CACHE VARIABLES FOR CROSS-REFERENCING
#######################

# Cache for cross-referencing between configuration measurements
# Populated by collect_config_* functions, used by collect_config_volumes
_STORAGE_POOLS_CACHE = {}  # volumeGroupRef -> pool info  
_HOSTS_CACHE = {}          # clusterRef -> host info


_VOLUME_MAPPINGS_CACHE = {} # mapRef -> mapping info
# Cache for cross-referencing drive config (driveRef -> drive info)
_DRIVES_CACHE = {}  # driveRef -> drive info

def collect_config_drives(system_info):
    """
    Collects drive configuration information and posts it to InfluxDB
    :param system_info: The JSON object of a storage_system
    """
    # Early exit if not a config collection interval
    if not should_collect_config_data():
        LOG.info("Skipping config_drives collection - not a scheduled interval (collected every 15 minutes)")
        return

    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)
        json_body = list()

        # Get drive configuration data from the API
        drives_response = session.get(f"{get_controller('sys')}/{sys_id}/drives").json()

        LOG.debug(f"Retrieved {len(drives_response)} drive configurations")

        for drive in drives_response:
            config_fields = {}
            # Extract all simple fields from CONFIG_DRIVE_PARAMS except interfaceType_*_deviceName and tags
            for param in CONFIG_DRIVE_PARAMS:
                if param.startswith('interfaceType_'):
                    continue
                # skip tags, will be handled in tags dict
                if param in ['driveRef', 'serialNumber', 'productID', 'driveMediaType', 'physicalLocation__trayRef', 'physicalLocation_slot']:
                    continue
                value = drive.get(param)
                if value is not None:
                    config_fields[param] = value

            # Flatten interfaceType fields for each type
            interface_types = ['sas', 'nvme', 'fibre', 'scsi']
            interfaceType = drive.get('interfaceType', {})
            for itype in interface_types:
                key = f'interfaceType_{itype}_deviceName'
                val = None
                if isinstance(interfaceType, dict):
                    itype_obj = interfaceType.get(itype)
                    if isinstance(itype_obj, dict):
                        raw_val = itype_obj.get('deviceName')
                        # Clean up trailing whitespace from deviceName strings
                        if raw_val and isinstance(raw_val, str):
                            val = raw_val.rstrip()
                        else:
                            val = raw_val
                config_fields[key] = val

            # Apply field coercion
            config_fields = coerce_fields_dict(config_fields)

            # Tags for drive identity
            tags = {
                "sys_id": sys_id,
                "sys_name": sys_name,
                "driveRef": drive.get("driveRef", "unknown"),
                "serialNumber": drive.get("serialNumber", "unknown"),
                "productID": drive.get("productID", "unknown"),
                "driveMediaType": drive.get("driveMediaType", "unknown"),
                "physicalLocation__trayRef": str(drive.get("physicalLocation", {}).get("trayRef", "unknown")),
                "physicalLocation_slot": str(drive.get("physicalLocation", {}).get("slot", "unknown")),
            }

            drive_config_item = {
                "measurement": "config_drives",
                "tags": tags,
                "fields": config_fields
            }

            if not CMD.include or drive_config_item["measurement"] in CMD.include:
                json_body.append(drive_config_item)
                LOG.debug(f"Added config_drives measurement for drive {drive.get('driveRef', 'unknown')}")
            else:
                LOG.debug(f"Skipped config_drives measurement (not in --include filter)")

        LOG.debug(f"collect_config_drives: Prepared {len(json_body)} measurements for InfluxDB")
        if not CMD.doNotPost:
            client.write_points(json_body, database=INFLUXDB_DATABASE, time_precision="s")
            LOG.info("LOG: drive configuration data sent")
        else:
            LOG.debug("Skipped posting to InfluxDB (--doNotPost enabled)")

    except RuntimeError:
        LOG.error(f"Error when attempting to post drive configuration for {system_info['name']}/{system_info['wwn']}")

#######################
# FIELD TYPE COERCION #
#######################

# Production InfluxDB schema-based field type coercion mapping
# Based on analysis of real EPA production databases to prevent
# field type conflicts that cause write failures
FIELD_COERCIONS = {
    # Fields that MUST be integers in production
    'spareBlocksRemainingPercent': int,
    'percentEnduranceUsed': int,
    'totalPower': int,
    'temp': int,
    
    # Config volume fields - integers
    'blockSize': int,
    'blkSize': int,
    'blkSizePhysical': int,
    'segmentSize': int,
    'volumeHandle': int,
    'repairedBlockCount': int,
    'dataDriveCount': int,
    'parityDriveCount': int,
    'usableCapacity': int,
    'reserved1': int,
    'reserved2': int,
    'repositoryCapacity': int,
    'dssMaxSegmentSize': int,
    
    # Config host fields - integers  
    'initiatorCount': int,
    'hostSidePortCount': int,
    
    # Config volume fields - booleans (will be converted to strings)
    'offline': bool,
    'mapped': bool,
    'hostUnmapEnabled': bool,
    'volumeFull': bool,
    'diskPool': bool,
    'flashCached': bool,
    'preReadRedundancyCheckEnabled': bool,
    'protectionInformationCapable': bool,
    'protectionType': bool,
    'dssPreReadRedundancyCheckEnabled': bool,
    'dssWriteCacheEnabled': bool,
    
    # Config host fields - booleans (will be converted to strings)
    'isSAControlled': bool,
    'confirmLUNMappingCreation': bool,
    'protectionInformationCapableAccessMethod': bool,
    'isLargeBlockFormatHost': bool,
    'isLun0Restricted': bool,
    'initiators_first_initiatorInactive': bool,
    
    # Config storage pools fields - integers
    'sequenceNum': int,
    'blkSizeRecommended': int,
    
    # Config storage pools fields - booleans (will be converted to strings)
    'offline': bool,
    'spindleSpeedMatch': bool,
    'isInaccessible': bool,
    'drawerLossProtection': bool,
    'protectionInformationCapable': bool,
    'reservedSpaceAllocated': bool,
    'diskPool': bool,
    'blkSizeSupported_512': bool,
    'blkSizeSupported_4096': bool,
    
    # Config storage pools fields - large capacity (integers converted from strings)
    'usedSpace': int,
    'totalRaidedSpace': int,
    'freeSpace': int,
    'extents_rawCapacity': int,
    
    # Flattened mapping fields
    'listOfMappings_lun': int,
    'listOfMappings_ssid': int,
    
    # Large capacity fields - should be floats for InfluxDB compatibility
    'capacity': float,
    'totalSizeInBytes': float,

    # All other numeric fields should be floats to match production schema
    # This includes all performance metrics, utilization percentages, etc.
    # String fields (MEL descriptions, failure names) are left unchanged
}

#######################
# PARAMETERS ##########
#######################

NUMBER_OF_THREADS = 8

# Configuration data collection interval (in minutes)
# Config data changes infrequently, so collect every N minutes instead of every iteration
CONFIG_COLLECTION_INTERVAL_MINUTES = 15  # Collect config data every 15 minutes

# LOGGING
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Disable urllib3 warnings (SSL verification disabled)
try:
    requests.packages.urllib3.disable_warnings()
except AttributeError:
    # urllib3 warnings suppression failed, continuing without it
    pass
LOG = logging.getLogger("collector")

# Disables reset connection warning message if the connection time is too long
try:
    logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(
        logging.WARNING)
except (AttributeError, KeyError):
    # Fallback for different urllib3 configurations
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


#######################
# ARGUMENT PARSER #####
#######################

PARSER = argparse.ArgumentParser()

PARSER.add_argument('-u', '--username', default='', type=str, required=False,
                    help='Username to connect to the SANtricity API. '
                         'Required unless --createDb is used. Default: \'' + DEFAULT_USERNAME + '\'. <String>')
PARSER.add_argument('-p', '--password', default='', type=str, required=False,
                    help='Password for this user to connect to the SANtricity API. '
                         'Required unless --createDb is used. Default: \'' + DEFAULT_PASSWORD + '\'. <String>')
PARSER.add_argument('--api', default='',  nargs='+', required=False,
                    help='The IPv4 address for the SANtricity API endpoint. '
                         'Required unless --createDb is used. '
                         'Example: --api 5.5.5.5 6.6.6.6. Port number is auto-set to: \'' +
                    DEFAULT_SYSTEM_PORT + '\'. '
                         'May be provided twice (for two controllers). <IPv4 Address>')
PARSER.add_argument('--sysname', default='', type=str, required=False,
                    help='SANtricity system\'s user-configured array name. '
                         'Required unless --createDb is used. Example: dc1r226-elk. Default: None. <String>')
PARSER.add_argument('--sysid', default='', type=str, required=False,
                    help='SANtricity storage system\'s WWN. '
                         'Required unless --createDb is used. '
                         'Example: 600A098000F63714000000005E79C17C. Default: None. <String>')
PARSER.add_argument('-t', '--intervalTime', type=int, default=60, choices=[60, 120, 300, 600],
                    help='Interval (seconds) to poll and send data from the SANtricity API '
                    ' to InfluxDB. Default: 60. <Integer>')
PARSER.add_argument('--dbAddress', default='influxdb:8086', type=str, required=False,
                    help='The hostname (IPv4 address or FQDN) and the port for InfluxDB. '
                    'Required unless --doNotPost is used. '
                    'Default: influxdb:8086. Use public IPv4 of InfluxDB system rather than container name'
                    ' when running collector externally. In EPA InfluxDB uses port 8086. Example: 7.7.7.7:8086.')
PARSER.add_argument('-r', '--retention', default=DEFAULT_RETENTION, type=str, required=False,
                    help='Data retention for InfluxDB as an integer suffixed by a calendar unit. '
                    'Example: 4w translates into 28 day data retention. Default: 52w. '
                    'Default: \'' + DEFAULT_RETENTION + '\'.')
PARSER.add_argument('--dbName', default='', type=str, required=False,
                    help='Optional InfluxDB database name to override the default (eseries).')
PARSER.add_argument('--createDb', action='store_true', default=False,
                    help='Create the database and exit. Requires --dbName to be specified.')
PARSER.add_argument('-s', '--showStorageNames', action='store_true',
                    help='Outputs the storage array names found from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-v', '--showVolumeNames', action='store_true', default=0,
                    help='Outputs the volume names found from the SANtricity API to console.  Optional. <switch>')
PARSER.add_argument('-f', '--showInterfaceNames', action='store_true', default=0,
                    help='Outputs the interface names found from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-a', '--showVolumeMetrics', action='store_true', default=0,
                    help='Outputs the volume payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-d', '--showDriveNames', action='store_true', default=0,
                    help='Outputs the drive names found from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-b', '--showDriveMetrics', action='store_true', default=0,
                    help='Outputs the drive payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-ct', '--showControllerMetrics', action='store_true', default=0,
                    help='Outputs the controller payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-c', '--showSystemMetrics', action='store_true', default=0,
                    help='Outputs the system payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-m', '--showMELMetrics', action='store_true', default=0,
                    help='Outputs the MEL payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-e', '--showStateMetrics', action='store_true', default=0,
                    help='Outputs the state payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-g', '--showInterfaceMetrics', action='store_true', default=0,
                    help='Outputs the interface payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-pw', '--showPower', action='store_true', default=0,
                    help='Outputs the PSU reading to console. Optional. <switch>')
PARSER.add_argument('-en', '--showSensor', action='store_true', default=0,
                    help='Outputs the readings from environmental sensors (temperature) to console. Optional. <switch>')
PARSER.add_argument('-i', '--showIteration', action='store_true', default=0,
                    help='Outputs the current loop iteration. Optional. <switch>')
PARSER.add_argument('-n', '--doNotPost', action='store_true', default=0,
                    help='Pull information from SANtricity, but do not send it to InfluxDB. Optional. <switch>')
PARSER.add_argument('--debug', action='store_true', default=False,
                    help='Enable debug logging to show detailed collection and filtering information. Optional. <switch>')
PARSER.add_argument('--include', nargs='+', required=False,
                    help='Only collect specified measurements. Options: '
                         'disks, interface, systems, volumes, controllers, power, temp, '
                         'major_event_log, failures, config_storage_pools, config_volumes, config_hosts, config_drives. '
                         'Example: --include disks interface. If not specified, '
                         'all measurements are collected.')
CMD = PARSER.parse_args()

# Set logging level based on debug flag
if CMD.debug:
    logging.getLogger().setLevel(logging.DEBUG)
    LOG.setLevel(logging.DEBUG)
    LOG.debug("Debug logging enabled")

# Conditional validation for database creation mode
if CMD.createDb:
    # For database creation, only dbName and dbAddress are required
    if not CMD.dbName:
        PARSER.error("--createDb requires --dbName to be specified")
else:
    # For normal operation, SANtricity API parameters are required
    if not CMD.username:
        PARSER.error("--username is required for normal operation")
    if not CMD.password:
        PARSER.error("--password is required for normal operation")
    if not CMD.api:
        PARSER.error("--api is required for normal operation")
    if not CMD.sysname:
        PARSER.error("--sysname is required for normal operation")
    if not CMD.sysid:
        PARSER.error("--sysid is required for normal operation")

# Conditional validation: dbAddress is required unless doNotPost is used
if not CMD.doNotPost and (CMD.dbAddress == '' or CMD.dbAddress is None):
    PARSER.error("--dbAddress is required when --doNotPost is not used")

# Only set up SANtricity-related variables if not in createDb mode
if not CMD.createDb:
    if CMD.sysname == '' or CMD.sysname is None:
        LOG.warning("sysname not provided. Using default: %s",
                    DEFAULT_SYSTEM_NAME)
        sys_name = DEFAULT_SYSTEM_NAME
    else:
        sys_name = CMD.sysname

    if CMD.sysid == '' or CMD.sysid is None:
        LOG.warning("sysid not provided. Using default: %s", DEFAULT_SYSTEM_ID)
        sys_id = DEFAULT_SYSTEM_ID
    else:
        sys_id = CMD.sysid
else:
    # In createDb mode, these variables are not needed
    sys_name = None
    sys_id = None

if CMD.dbAddress == '' or CMD.dbAddress is None:
    if not CMD.doNotPost:
        LOG.warning(
            "InfluxDB server was not provided. Default setting (influxdb:8086) "
            "works only when collector and InfluxDB containers are on same host")
    influxdb_host = INFLUXDB_HOSTNAME
    influxdb_port = INFLUXDB_PORT
else:
    influxdb_host = CMD.dbAddress.split(":")[0]
    influxdb_port = CMD.dbAddress.split(":")[1]

if (CMD.retention == '' or CMD.retention is None):
    LOG.warning("retention set to: %s", DEFAULT_RETENTION)
    RETENTION_DUR = DEFAULT_RETENTION
else:
    RETENTION_DUR = CMD.retention

# Define which measurements each collection function provides
FUNCTION_MEASUREMENTS = {
    'collect_storage_metrics': ['disks', 'interface', 'systems', 'volumes'],
    'collect_controller_metrics': ['controllers'],
    'collect_symbol_stats': ['power', 'temp'],
    'collect_major_event_log': ['major_event_log'],
    'collect_system_state': ['failures'],
    'collect_config_storage_pools': ['config_storage_pools'],
    'collect_config_volumes': ['config_volumes'],
    'collect_config_hosts': ['config_hosts'],
    'collect_config_drives': ['config_drives']
}

# Validate --include options if provided
if hasattr(CMD, 'include') and CMD.include:
    valid_measurements = set()
    for measurements in FUNCTION_MEASUREMENTS.values():
        valid_measurements.update(measurements)

    invalid_measurements = [
        m for m in CMD.include if m not in valid_measurements]
    if invalid_measurements:
        PARSER.error(f"Invalid measurement(s) in --include: "
                     f"{', '.join(invalid_measurements)}. "
                     f"Valid options: {', '.join(sorted(valid_measurements))}")

    LOG.info(
        f"Selective collection enabled. Including measurements: {', '.join(CMD.include)}")
    LOG.debug(f"CMD.include value: {CMD.include}")
    LOG.debug(f"CMD.include type: {type(CMD.include)}")
else:
    LOG.info("Collecting all measurements (default behavior)")
    LOG.debug(f"CMD.include value: {CMD.include}")
    LOG.debug(f"CMD.include type: {type(CMD.include)}")


#######################
# HELPER FUNCTIONS ####
#######################


def should_collect_config_data():
    """
    Determine if config data should be collected this iteration.
    Config data changes infrequently, so collect only every N minutes.
    Returns True if current minute is a collection minute (0, 15, 30, 45 by default).
    """
    current_minute = datetime.now().minute
    return current_minute % CONFIG_COLLECTION_INTERVAL_MINUTES == 0


def get_session():
    """
    Returns a session with the appropriate content type and login information.
    :return: Returns a request session for the SANtricity API endpoint
    """
    request_session = requests.Session()

    username = CMD.username
    password = CMD.password

    request_session.auth = (username, password)
    request_session.headers = {"Accept": "application/json",
                               "Content-Type": "application/json",
                               "netapp-client-type": "collector-" + __version__}

    request_session.verify = False
    return request_session


def get_controller(query):
    """
    Returns a SANtricity API URL with param-based path.
    :return: Returns a SANtricity API URL path string to storage-systems or firmware
    """
    if query == "sys":
        api_path = '/devmgr/v2/storage-systems'
    elif query == "fw":
        api_path = '/devmgr/v2/firmware/embedded-firmware'
    else:
        LOG.error("Unsupported API path requested")
        raise ValueError(f"Unsupported query type: {query}")
    if (len(CMD.api) == 0) or (CMD.api is None) or (CMD.api == ''):
        storage_controller_ep = 'https://' + \
            DEFAULT_SYSTEM_API_IP + ':' + DEFAULT_SYSTEM_PORT + api_path
    elif (len(CMD.api) == 1):
        storage_controller_ep = 'https://' + \
            CMD.api[0] + ':' + DEFAULT_SYSTEM_PORT + api_path
    else:
        controller = random.randrange(0, 2)
        storage_controller_ep = 'https://' + \
            CMD.api[controller] + ':' + DEFAULT_SYSTEM_PORT + \
            api_path
        LOG.info(f"Controller selection: {storage_controller_ep}")
    return (storage_controller_ep)


def get_drive_location(sys_id, session):
    """
    :param sys_id: Storage system ID (WWN) on the controller
    :param session: the session of the thread that calls this definition
    ::return: returns a dictionary containing the disk id matched up against
    the tray id it is located in:
    """
    hardware_list = session.get(
        f"{get_controller('sys')}/{sys_id}/hardware-inventory").json()
    tray_list = hardware_list["trays"]
    drive_list = hardware_list["drives"]
    tray_ids = {}
    drive_location = {}

    for tray in tray_list:
        tray_ids[tray["trayRef"]] = tray["trayId"]

    for drive in drive_list:
        drive_tray = drive["physicalLocation"]["trayRef"]
        tray_id = tray_ids.get(drive_tray)
        if tray_id != "none":
            drive_location[drive["driveRef"]] = [
                tray_id, drive["physicalLocation"]["slot"]]
        else:
            LOG.error("Error matching drive to a tray in the storage system")
    return drive_location


def collect_symbol_stats(system_info):
    """
    Collects temp sensor and PSU consumption (W) and posts them to InfluxDB
    :param system_info: The JSON object
    """
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)
        # PSU
        psu_response = session.get(f"{get_controller('sys')}/{sys_id}/symbol/getEnergyStarData",
                                   params={"controller": "auto", "verboseErrorResponse": "false"}, timeout=(6.10, CMD.intervalTime*2)).json()
        psu_total = psu_response['energyStarData']['totalPower']
        if CMD.showPower:
            LOG.info("PSU response (total): %s", psu_total)
        json_body = list()
        item = {
            "measurement": "power",
            "tags": {
                "sys_id": sys_id,
                "sys_name": sys_name
            },
            "fields": coerce_fields_dict({"totalPower": psu_total})
        }
        if not CMD.include or item["measurement"] in CMD.include:
            json_body.append(item)
            LOG.debug(f"Added {item['measurement']} measurement to collection")
        else:
            LOG.debug(f"Skipped {item['measurement']} measurement (not in --include filter)")
        LOG.info("LOG: PSU data prepared")

        # ENVIRONMENTAL SENSORS
        response = session.get(
            f"{get_controller('sys')}/{sys_id}/symbol/getEnclosureTemperatures",
            params={"controller": "auto", "verboseErrorResponse": "false"},
            timeout=(6.10, CMD.intervalTime*2)).json()
        if CMD.showSensor:
            LOG.info("Sensor response: %s", response['thermalSensorData'])
        env_response = order_sensor_response_list(response)
        for i, sensor in enumerate(env_response):
            sensor_id = sensor['thermalSensorRef']
            sensor_order = f"sensor_{i}"
            item = {
                "measurement": "temp",
                "tags": {
                    "sensor": sensor_id,
                    "sensor_seq": sensor_order,
                    "sys_id": sys_id,
                    "sys_name": sys_name
                },
                "fields": coerce_fields_dict({"temp": sensor['currentTemp']})
            }
            if not CMD.include or item["measurement"] in CMD.include:
                json_body.append(item)
        LOG.info("LOG: sensor data prepared")

        LOG.debug(f"collect_symbol_stats: Prepared {len(json_body)} measurements for InfluxDB")
        if not CMD.doNotPost:
            client.write_points(
                json_body, database=INFLUXDB_DATABASE, time_precision="s")
            LOG.info("LOG: SYMbol V2 PSU and sensor readings sent")

    except RuntimeError:
        LOG.error(
            f"Error when attempting to post tmp sensors data for {system_info['name']}/{system_info['wwn']}")


def field_coerce(field_name, value):
    """
    Coerce field values to match production InfluxDB schema types.

    Prevents field type conflicts that cause write failures when NetApp API
    returns mixed int/float values for fields that already exist as specific
    types in the production database.

    Args:
        field_name (str): Name of the field
        value: The value to potentially coerce

    Returns:
        The value coerced to the appropriate type, or unchanged if no coercion needed
    """
    if value is None:
        return None

    # Handle explicit coercions from mapping
    if field_name in FIELD_COERCIONS:
        target_type = FIELD_COERCIONS[field_name]
        try:
            if target_type == bool:
                # For boolean fields, convert to string representation for InfluxDB
                coerced_value = str(bool(value)).lower()
                if type(value) != bool and LOG.isEnabledFor(logging.DEBUG):
                    LOG.debug(
                        f"Coerced field '{field_name}': {type(value).__name__}({value}) -> string({coerced_value})")
                return coerced_value
            else:
                coerced_value = target_type(value)
                if type(value) != target_type and LOG.isEnabledFor(logging.DEBUG):
                    LOG.debug(
                        f"Coerced field '{field_name}': {type(value).__name__}({value}) -> {target_type.__name__}({coerced_value})")
                return coerced_value
        except (ValueError, TypeError):
            LOG.warning(
                f"Could not coerce field '{field_name}' value {value} to {target_type.__name__}")
            return value

    # For all other numeric fields, coerce to float to match production schema
    # (except strings and explicitly mapped integers)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not isinstance(value, float) and LOG.isEnabledFor(logging.DEBUG):
            LOG.debug(
                f"Coerced field '{field_name}': {type(value).__name__}({value}) -> float({float(value)})")
        return float(value)

    # Leave strings, booleans, and other types unchanged
    return value


def coerce_fields_dict(fields_dict):
    """
    Apply field coercion to all fields in a dictionary.

    Args:
        fields_dict (dict): Dictionary of field names to values

    Returns:
        dict: Dictionary with coerced field values
    """
    return {field_name: field_coerce(field_name, value)
            for field_name, value in fields_dict.items()}


def collect_storage_metrics(system_info):
    """
    Collects all defined storage metrics and posts them to InfluxDB: drives, system stats,
    interfaces, and volumes
    :param sys: The JSON object of a storage system
    """
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)
        json_body = list()
        drive_stats_list = session.get(
            f"{get_controller('sys')}/{sys_id}/analysed-drive-statistics").json()
        drive_locations = get_drive_location(sys_id, session)
        if CMD.showDriveNames:
            for stats in drive_stats_list:
                location_send = drive_locations.get(stats["diskId"])
                if location_send is not None:
                    LOG.info(
                        f"Tray{location_send[0]:02.0f}, Slot{location_send[1]:03.0f}")
                else:
                    LOG.warning(
                        f"Could not find location for drive {stats['diskId']}")

        # Get firmware version to determine API capabilities
        fw_resp = session.get(
            f"{get_controller('fw')}/{sys_id}/versions").json()
        fw_cv = fw_resp['codeVersions']
        minor_vers = 0
        for mod in (range(len(fw_cv))):
            if fw_cv[mod]['codeModule'] == 'management':
                minor_vers = int((fw_cv[mod]['versionString']).split(".")[1])
                break

        # Get SSD wear statistics from the new drive-health-history endpoint
        ssd_wear_dict = {}
        if minor_vers >= 80:
            try:
                drive_health_response = session.get(f"{get_controller('sys')}/{sys_id}/drives/drive-health-history",
                                                    params={"all-history": "false"}).json()

                # Extract SSD wear data from the response
                if 'collections' in drive_health_response and len(drive_health_response['collections']) > 0:
                    latest_collection = drive_health_response['collections'][0]
                    if 'ssdDriveWearStatistics' in latest_collection:
                        for ssd_stat in latest_collection['ssdDriveWearStatistics']:
                            # Use volGroupName as primary key for safe correlation
                            vol_group_name = ssd_stat.get('volumeGroupName')
                            drive_wwn = ssd_stat.get('driveWwn')
                            spare_blocks = ssd_stat.get(
                                'spareBlockRemainingPercentage')
                            wearlife_percent = ssd_stat.get(
                                'wearlifePercentageUsed')

                            if vol_group_name:
                                # Create composite key: volGroupName + WWN suffix for uniqueness
                                if len(drive_wwn) >= 12:
                                    composite_key = f"{vol_group_name}#{drive_wwn[-12:]}"
                                    # Store both wear metrics as a dict
                                    wear_data = {}
                                    if spare_blocks is not None:
                                        wear_data['spareBlocksRemainingPercent'] = spare_blocks
                                    # Handle wearlifePercentageUsed: null means "no wear yet" so use 0
                                    if wearlife_percent is not None:
                                        wear_data['percentEnduranceUsed'] = wearlife_percent
                                    else:
                                        # null = no wear yet
                                        wear_data['percentEnduranceUsed'] = 0
                                    if wear_data:  # Only store if we have at least one metric
                                        ssd_wear_dict[composite_key] = wear_data
                LOG.info(
                    f"Found SSD wear data for {len(ssd_wear_dict)} drives")
            except (requests.exceptions.RequestException, KeyError, ValueError) as e:
                LOG.warning(f"Could not retrieve SSD wear statistics: {e}")
        else:
            version_string = next((fw_cv[mod]['versionString'] for mod in range(len(fw_cv))
                                   if fw_cv[mod]['codeModule'] == 'management'), 'unknown')
            LOG.warning(
                f"SSD wear level ignored for this SANtricity version {version_string}")

        for stats in drive_stats_list:
            pdict = {}
            disk_location_info = drive_locations.get(stats["diskId"])

            # Try to get SSD wear data using volGroupName as primary correlation
            disk_id = stats.get("diskId")
            vol_group_name = stats.get("volGroupName")

            if disk_id and vol_group_name and ssd_wear_dict:
                # Create composite key using volGroupName + diskId suffix for safe matching
                if len(disk_id) >= 12:
                    composite_key = f"{vol_group_name}#{disk_id[-12:]}"
                    if composite_key in ssd_wear_dict:
                        wear_data = ssd_wear_dict[composite_key]
                        pdict = wear_data.copy()  # Copy the wear metrics dictionary
                        wear_metrics = []
                        if 'spareBlocksRemainingPercent' in wear_data:
                            wear_metrics.append(
                                f"spareBlocks={wear_data['spareBlocksRemainingPercent']}%")
                        if 'percentEnduranceUsed' in wear_data:
                            wear_metrics.append(
                                f"enduranceUsed={wear_data['percentEnduranceUsed']}%")
                        LOG.debug(
                            f"Found SSD wear data for drive {disk_id} in {vol_group_name}: {', '.join(wear_metrics)}")

            if pdict:
                fields_dict = dict((metric, stats.get(metric))
                                   for metric in DRIVE_PARAMS) | pdict
            else:
                fields_dict = dict((metric, stats.get(metric))
                                   for metric in DRIVE_PARAMS)

            # Apply field type coercion to match production InfluxDB schema
            fields_dict = coerce_fields_dict(fields_dict)

            # Safely handle disk location info with fallbacks
            if disk_location_info is not None and len(disk_location_info) >= 2:
                tray_id = disk_location_info[0]
                slot_id = disk_location_info[1]
            else:
                # Fallback to trayRef and driveSlot from stats if location info is unavailable
                tray_id = stats.get('trayRef', 99)
                slot_id = stats.get('driveSlot', 999)

            disk_item = {
                "measurement": "disks",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    "sys_tray": f"{tray_id:02.0f}",
                    "sys_tray_slot": f"{slot_id:03.0f}"
                },
                "fields": fields_dict
            }

            # Add volume group tag if available
            if vol_group_name is not None:
                disk_item["tags"]["vol_group_name"] = vol_group_name
            if CMD.showDriveMetrics:
                LOG.info("Drive payload: %s", disk_item)
            if not CMD.include or disk_item["measurement"] in CMD.include:
                json_body.append(disk_item)

        interface_stats_list = session.get(
            f"{get_controller('sys')}/{sys_id}/analysed-interface-statistics").json()
        if CMD.showInterfaceNames:
            for stats in interface_stats_list:
                LOG.info(stats["interfaceId"])
        for stats in interface_stats_list:
            interface_fields = dict((metric, stats.get(metric))
                                    for metric in INTERFACE_PARAMS)
            interface_fields = coerce_fields_dict(interface_fields)

            if_item = {
                "measurement": "interface",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    "interface_id": stats["interfaceId"],
                    "channel_type": stats["channelType"]
                },
                "fields": interface_fields
            }
            if CMD.showInterfaceMetrics:
                LOG.info("Interface payload: %s", if_item)
            if not CMD.include or if_item["measurement"] in CMD.include:
                json_body.append(if_item)

        system_stats_list = session.get(
            f"{get_controller('sys')}/{sys_id}/analysed-system-statistics").json()
        system_fields = dict((metric, system_stats_list.get(metric))
                             for metric in SYSTEM_PARAMS)
        system_fields = coerce_fields_dict(system_fields)

        sys_item = {
            "measurement": "systems",
            "tags": {
                "sys_id": sys_id,
                "sys_name": sys_name
            },
            "fields": system_fields
        }
        if CMD.showSystemMetrics:
            LOG.info("System payload: %s", sys_item)
        if not CMD.include or sys_item["measurement"] in CMD.include:
            json_body.append(sys_item)

        volume_stats_list = session.get(
            f"{get_controller('sys')}/{sys_id}/analysed-volume-statistics").json()
        if CMD.showVolumeNames:
            for stats in volume_stats_list:
                LOG.info(stats["volumeName"])
        for stats in volume_stats_list:
            volume_fields = dict((metric, stats.get(metric))
                                 for metric in VOLUME_PARAMS)
            volume_fields = coerce_fields_dict(volume_fields)

            vol_item = {
                "measurement": "volumes",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    "vol_name": stats["volumeName"]
                },
                "fields": volume_fields
            }
            if CMD.showVolumeMetrics:
                LOG.info("Volume payload: %s", vol_item)
            if not CMD.include or vol_item["measurement"] in CMD.include:
                json_body.append(vol_item)

        LOG.debug(f"collect_storage_metrics: Prepared {len(json_body)} measurements for InfluxDB")
        if not CMD.doNotPost:
            client.write_points(
                json_body, database=INFLUXDB_DATABASE, time_precision="s")
            LOG.info("LOG: storage metrics sent")
        else:
            LOG.debug("Skipped posting to InfluxDB (--doNotPost enabled)")

    except RuntimeError:
        LOG.error(
            f"Error when attempting to post statistics for {system_info['name']}/{system_info['wwn']}")


def collect_major_event_log(system_info):
    """
    Collects all defined MEL metrics and posts them to InfluxDB
    :param sys: The JSON object of a storage_system
    """
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)
        json_body = list()
        start_from = -1
        mel_grab_count = 8192
        query = client.query(
            f"SELECT id FROM major_event_log WHERE sys_id='{sys_id}' ORDER BY time DESC LIMIT 1")

        if query:
            start_from = int(next(query.get_points())["id"]) + 1

        mel_response = session.get(f"{get_controller('sys')}/{sys_id}/mel-events",
                                   params={"count": mel_grab_count, "startSequenceNumber": start_from}, timeout=(6.10, CMD.intervalTime*2)).json()
        if CMD.showMELMetrics:
            LOG.info("Starting from %s", str(start_from))
            LOG.info("Grabbing %s MELs", str(len(mel_response)))
        for mel in mel_response:
            item = {
                "measurement": "major_event_log",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    "event_type": mel["eventType"],
                    "time_stamp": mel["timeStamp"],
                    "category": mel["category"],
                    "priority": mel["priority"],
                    "critical": mel["critical"],
                    "ascq": mel["ascq"],
                    "asc": mel["asc"]
                },
                "fields": coerce_fields_dict(dict(
                    (metric, mel.get(metric)) for metric in MEL_PARAMS
                )),
                "time": datetime.fromtimestamp(
                    int(mel["timeStamp"]), timezone.utc).isoformat()
            }
            if CMD.showMELMetrics:
                LOG.info("MEL payload: %s", item)
            if not CMD.include or item["measurement"] in CMD.include:
                json_body.append(item)
        try:
            client.write_points(
                json_body, database=INFLUXDB_DATABASE, time_precision="s")
            LOG.info("LOG: MEL payload sent")
        except InfluxDBClientError as e:
            if "beyond retention policy" in str(e):
                LOG.debug(f"Some MEL events were beyond retention policy and dropped by InfluxDB: {e}")
                LOG.info("LOG: MEL payload sent (some events outside retention dropped)")
            else:
                # Re-raise other InfluxDB errors
                raise
    except RuntimeError:
        LOG.error(
            f"Error when attempting to post MEL for {system_info['name']}/{system_info['wwn']}")


def create_failure_dict_item(sys_id, sys_name, fail_type, obj_ref, obj_type, is_active, the_time):
    item = {
        "measurement": "failures",
        "tags": {
            "sys_id": sys_id,
            "sys_name": sys_name,
            "failure_type": fail_type,
            "object_ref": obj_ref,
            "object_type": obj_type,
            "active": is_active
        },
        "fields": coerce_fields_dict({
            "name_of": sys_name,
            "type_of": fail_type
        }),
        "time": the_time
    }
    return item


def collect_system_state(system_info, checksums):
    """
    Collects state information from the storage system and posts it to InfluxDB
    :param sys: The JSON object of a storage_system
    :param checksums: The MD5 checksum of failure response from last time we checked
    """
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)

        sys_id = system_info["wwn"]
        sys_name = system_info["name"]
        failure_response = session.get(
            f"{get_controller('sys')}/{sys_id}/failures").json()

        # we can skip us if this is the same response we handled last time
        old_checksum = checksums.get(str(sys_id))
        new_checksum = hashlib.md5(
            str(failure_response).encode("utf-8")).hexdigest()
        if old_checksum is not None and str(new_checksum) == str(old_checksum):
            return
        checksums.update({str(sys_id): str(new_checksum)})

        # pull most recent failures for this system from our database, including their active status
        query_string = f'SELECT last("type_of"),failure_type,object_ref,object_type,active FROM "failures" WHERE ("sys_id" = \'{sys_id}\') GROUP BY "sys_name", "failure_type"'
        query = client.query(query_string)
        failure_points = list(query.get_points())

        json_body = list()

        # take care of active failures we don't know about
        for failure in failure_response:
            r_fail_type = failure.get("failureType")
            r_obj_ref = failure.get("objectRef")
            r_obj_type = failure.get("objectType")

            # we push if we haven't seen this, or we think it's inactive
            push = True
            for point in failure_points:
                p_fail_type = point["failure_type"]
                p_obj_ref = point["object_ref"]
                p_obj_type = point["object_type"]
                p_active = point["active"]
                if (r_fail_type == p_fail_type
                    and r_obj_ref == p_obj_ref
                        and r_obj_type == p_obj_type):
                    if p_active == "True":
                        push = False  # we already know this is an active failure so don't push
                    break

            if push:
                failure_item = create_failure_dict_item(sys_id, sys_name,
                                                        r_fail_type, r_obj_ref, r_obj_type,
                                                        True, datetime.now(timezone.utc).isoformat())
                if CMD.showStateMetrics:
                    LOG.info("Failure payload T1: %s", failure_item)
                if not CMD.include or failure_item["measurement"] in CMD.include:
                    json_body.append(failure_item)

        # take care of failures that are no longer active
        for point in failure_points:
            # we only care about points that we think are active
            p_active = point["active"]
            if not p_active:
                continue

            p_fail_type = point["failure_type"]
            p_obj_ref = point["object_ref"]
            p_obj_type = point["object_type"]

            # we push if we are no longer active, but think that we are
            push = True
            for failure in failure_response:
                r_fail_type = failure.get("failureType")
                r_obj_ref = failure.get("objectRef")
                r_obj_type = failure.get("objectType")
                if (r_fail_type == p_fail_type
                    and r_obj_ref == p_obj_ref
                        and r_obj_type == p_obj_type):
                    push = False  # we are still active, so don't push
                    break

            if push:
                failure_item = create_failure_dict_item(sys_id, sys_name,
                                                        p_fail_type, p_obj_ref, p_obj_type,
                                                        False, datetime.now(timezone.utc).isoformat())
                if CMD.showStateMetrics:
                    LOG.info("Failure payload T2: %s", failure_item)
                if not CMD.include or failure_item["measurement"] in CMD.include:
                    json_body.append(failure_item)

        # write failures to InfluxDB
        if CMD.showStateMetrics:
            LOG.info(f"Writing {len(json_body)} failures")
        client.write_points(json_body, database=INFLUXDB_DATABASE)

    except RuntimeError:
        LOG.error(
            f"Error when attempting to post state information for {system_info['name']}/{system_info['id']}")


def collect_config_volumes(system_info):
    """
    Collects volume configuration information and posts it to InfluxDB
    :param system_info: The JSON object of a storage_system
    """
    # Early exit if not a config collection interval
    if not should_collect_config_data():
        LOG.info("Skipping config_volumes collection - not a scheduled interval (collected every 15 minutes)")
        return
        
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)
        json_body = list()
        
        # Get volume configuration data from the API
        volumes_response = session.get(f"{get_controller('sys')}/{sys_id}/volumes").json()
        
        LOG.debug(f"Retrieved {len(volumes_response)} volume configurations")
        
        for volume in volumes_response:
            # Extract configuration fields (numeric/boolean values from CONFIG_VOLUME_PARAMS)
            config_fields = {}
            for param in CONFIG_VOLUME_PARAMS:
                value = volume.get(param)
                if value is not None:
                    config_fields[param] = value
            
            # Add controller IDs as fields (not tags) for querying mismatches
            config_fields['currentControllerId'] = volume.get('currentControllerId', 'unknown')
            config_fields['preferredControllerId'] = volume.get('preferredControllerId', 'unknown')
            
            # Add raidLevel and status as fields (they can change)
            config_fields['raidLevel'] = volume.get('raidLevel', 'unknown')
            config_fields['status'] = volume.get('status', 'unknown')
            
            # Flatten listOfMappings (take first mapping if multiple exist)
            mappings = volume.get('listOfMappings', [])
            if mappings and len(mappings) > 0:
                first_mapping = mappings[0]
                config_fields['listOfMappings_lunMappingRef'] = first_mapping.get('lunMappingRef', 'unknown')
                config_fields['listOfMappings_lun'] = first_mapping.get('lun', 0)
                config_fields['listOfMappings_ssid'] = first_mapping.get('ssid', 0)
            else:
                config_fields['listOfMappings_lunMappingRef'] = 'unmapped'
                config_fields['listOfMappings_lun'] = 0
                config_fields['listOfMappings_ssid'] = 0
            
            # Apply field coercion to ensure proper types
            config_fields = coerce_fields_dict(config_fields)
            
            vol_config_item = {
                "measurement": "config_volumes",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    # Essential volume identifiers only
                    "volumeHandle": str(volume.get("volumeHandle", "unknown")),
                    "worldWideName": volume.get("worldWideName", "unknown"),
                    "label": volume.get("label", "unknown"),
                    "volumeRef": volume.get("volumeRef", "unknown"),
                    "wwn": volume.get("wwn", "unknown"),
                    "name": volume.get("name", "unknown"),
                    "id": volume.get("id", "unknown"),
                    # Group reference for volume grouping
                    "volumeGroupRef": volume.get("volumeGroupRef", "unknown"),
                    # Extended identifier 
                    "extendedUniqueIdentifier": volume.get("extendedUniqueIdentifier", "unknown")
                },
                "fields": config_fields
            }
            
            if not CMD.include or vol_config_item["measurement"] in CMD.include:
                json_body.append(vol_config_item)
                LOG.debug(f"Added config_volumes measurement for volume {volume.get('name', 'unknown')}")
            else:
                LOG.debug(f"Skipped config_volumes measurement (not in --include filter)")
        
        LOG.debug(f"collect_config_volumes: Prepared {len(json_body)} measurements for InfluxDB")
        if not CMD.doNotPost:
            client.write_points(json_body, database=INFLUXDB_DATABASE, time_precision="s")
            LOG.info("LOG: volume configuration data sent")
        else:
            LOG.debug("Skipped posting to InfluxDB (--doNotPost enabled)")
            
    except RuntimeError:
        LOG.error(f"Error when attempting to post volume configuration for {system_info['name']}/{system_info['wwn']}")


def collect_config_storage_pools(system_info):
    """
    Collects storage pool configuration information and posts it to InfluxDB
    :param system_info: The JSON object of a storage_system
    """
    global _STORAGE_POOLS_CACHE
    
    # Early exit if not a config collection interval
    if not should_collect_config_data():
        LOG.info("Skipping config_storage_pools collection - not a scheduled interval (collected every 15 minutes)")
        return
    
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)
        json_body = list()
        
        # Get storage pool configuration data from the API
        storage_pools_response = session.get(f"{get_controller('sys')}/{sys_id}/storage-pools").json()
        
        LOG.debug(f"Retrieved {len(storage_pools_response)} storage pool configurations")
        
        for pool in storage_pools_response:
            # Extract configuration fields (numeric/boolean values from CONFIG_STORAGE_POOLS_PARAMS)
            config_fields = {}
            for param in CONFIG_STORAGE_POOLS_PARAMS:
                if param.startswith('blkSizeSupported_'):
                    # Handle flattened blkSizeSupported array
                    blk_size_supported = pool.get('blkSizeSupported', [])
                    if param == 'blkSizeSupported_512':
                        config_fields[param] = 512 in blk_size_supported
                    elif param == 'blkSizeSupported_4096':
                        config_fields[param] = 4096 in blk_size_supported
                elif param.startswith('volumeGroupData_'):
                    # Handle flattened volumeGroupData
                    volume_group_data = pool.get('volumeGroupData', {})
                    if param == 'volumeGroupData_type':
                        config_fields[param] = volume_group_data.get('type', 'unknown')
                elif param.startswith('extents_'):
                    # Handle flattened extents (sum all extents)
                    extents = pool.get('extents', [])
                    if param == 'extents_rawCapacity':
                        # Sum all extent raw capacities
                        total_raw_capacity = 0
                        for extent in extents:
                            raw_capacity = extent.get('rawCapacity')
                            if raw_capacity is not None:
                                # Convert string to int if needed
                                if isinstance(raw_capacity, str):
                                    try:
                                        total_raw_capacity += int(raw_capacity)
                                    except ValueError:
                                        LOG.warning(f"Could not convert extent rawCapacity '{raw_capacity}' to int")
                                else:
                                    total_raw_capacity += raw_capacity
                        config_fields[param] = total_raw_capacity
                    elif param == 'extents_raidLevel':
                        # Use first extent's raid level (they should all be the same)
                        if extents and len(extents) > 0:
                            config_fields[param] = extents[0].get('raidLevel', 'unknown')
                        else:
                            config_fields[param] = 'unknown'
                else:
                    # Direct field mapping
                    value = pool.get(param)
                    if value is not None:
                        config_fields[param] = value
            
            # Apply field coercion to ensure proper types
            config_fields = coerce_fields_dict(config_fields)
            
            # Cache storage pool data for cross-referencing
            pool_ref = pool.get('volumeGroupRef', 'unknown')
            if pool_ref != 'unknown':
                _STORAGE_POOLS_CACHE[pool_ref] = {
                    'raidLevel': pool.get('raidLevel', 'unknown'),
                    'driveMediaType': pool.get('driveMediaType', 'unknown'),
                    'label': pool.get('label', 'unknown'),
                    'state': pool.get('state', 'unknown'),
                    'diskPool': pool.get('diskPool', False)
                }
            
            pool_config_item = {
                "measurement": "config_storage_pools",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    # Essential pool identifiers
                    "volumeGroupRef": pool.get("volumeGroupRef", "unknown"),
                    "id": pool.get("id", "unknown"),
                    "label": pool.get("label", "unknown"),
                    "name": pool.get("name", "unknown"),
                    # Pool type and RAID level as tags for easy filtering
                    "raidLevel": pool.get("raidLevel", "unknown"),
                    "state": pool.get("state", "unknown"),
                    "driveMediaType": pool.get("driveMediaType", "unknown")
                },
                "fields": config_fields
            }
            
            if not CMD.include or pool_config_item["measurement"] in CMD.include:
                json_body.append(pool_config_item)
                LOG.debug(f"Added config_storage_pools measurement for pool {pool.get('label', 'unknown')}")
            else:
                LOG.debug(f"Skipped config_storage_pools measurement (not in --include filter)")
        
        LOG.debug(f"collect_config_storage_pools: Prepared {len(json_body)} measurements for InfluxDB")
        if not CMD.doNotPost:
            client.write_points(json_body, database=INFLUXDB_DATABASE, time_precision="s")
            LOG.info("LOG: storage pool configuration data sent")
        else:
            LOG.debug("Skipped posting to InfluxDB (--doNotPost enabled)")
            
    except RuntimeError:
        LOG.error(f"Error when attempting to post storage pool configuration for {system_info['name']}/{system_info['wwn']}")


def collect_config_hosts(system_info):
    """
    Collects host configuration information and posts it to InfluxDB
    :param system_info: The JSON object of a storage_system
    """
    # Early exit if not a config collection interval
    if not should_collect_config_data():
        LOG.info("Skipping config_hosts collection - not a scheduled interval (collected every 15 minutes)")
        return
        
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)
        json_body = list()
        
        # Get host configuration data from the API
        hosts_response = session.get(f"{get_controller('sys')}/{sys_id}/hosts").json()
        
        LOG.debug(f"Retrieved {len(hosts_response)} host configurations")
        
        for host in hosts_response:
            # Extract configuration fields (numeric/boolean values from CONFIG_HOSTS_PARAMS)
            config_fields = {}
            for param in CONFIG_HOSTS_PARAMS:
                if param.startswith('initiators_first_'):
                    # Handle flattened initiator fields
                    initiators = host.get('initiators', [])
                    if initiators and len(initiators) > 0:
                        first_initiator = initiators[0]
                        if param == 'initiators_first_initiatorRef':
                            config_fields[param] = first_initiator.get('initiatorRef', '')
                        elif param == 'initiators_first_nodeName_ioInterfaceType':
                            node_name = first_initiator.get('nodeName', {})
                            config_fields[param] = node_name.get('ioInterfaceType') or ''
                        elif param == 'initiators_first_nodeName_iscsiNodeName':
                            node_name = first_initiator.get('nodeName', {})
                            config_fields[param] = node_name.get('iscsiNodeName') or ''
                        elif param == 'initiators_first_nodeName_remoteNodeWWN':
                            node_name = first_initiator.get('nodeName', {})
                            config_fields[param] = node_name.get('remoteNodeWWN') or ''
                        elif param == 'initiators_first_nodeName_nvmeNodeName':
                            node_name = first_initiator.get('nodeName', {})
                            config_fields[param] = node_name.get('nvmeNodeName') or ''
                        elif param == 'initiators_first_label':
                            config_fields[param] = first_initiator.get('label', '')
                        elif param == 'initiators_first_hostRef':
                            config_fields[param] = first_initiator.get('hostRef', '')
                        elif param == 'initiators_first_initiatorInactive':
                            config_fields[param] = first_initiator.get('initiatorInactive', False)
                        elif param == 'initiators_first_initiatorNodeName_interfaceType':
                            initiator_node_name = first_initiator.get('initiatorNodeName', {})
                            config_fields[param] = initiator_node_name.get('interfaceType', '')
                        elif param == 'initiators_first_id':
                            config_fields[param] = first_initiator.get('id', '')
                    else:
                        # No initiators present - set appropriate defaults
                        if param == 'initiators_first_initiatorInactive':
                            config_fields[param] = False
                        else:
                            config_fields[param] = ''
                            
                elif param.startswith('hostSidePorts_first_'):
                    # Handle flattened host-side port fields
                    host_side_ports = host.get('hostSidePorts', [])
                    if host_side_ports and len(host_side_ports) > 0:
                        first_port = host_side_ports[0]
                        if param == 'hostSidePorts_first_type':
                            config_fields[param] = first_port.get('type', '')
                        elif param == 'hostSidePorts_first_mtpIoInterfaceType':
                            config_fields[param] = first_port.get('mtpIoInterfaceType', '')
                        elif param == 'hostSidePorts_first_id':
                            config_fields[param] = first_port.get('id', '')
                    else:
                        # No host-side ports present
                        config_fields[param] = ''
                        
                elif param == 'initiatorCount':
                    # Count of initiators
                    initiators = host.get('initiators', [])
                    config_fields[param] = len(initiators)
                    
                elif param == 'hostSidePortCount':
                    # Count of host-side ports
                    host_side_ports = host.get('hostSidePorts', [])
                    config_fields[param] = len(host_side_ports)
                    
                else:
                    # Direct field mapping (skip hostTypeIndex since it's now a tag)
                    if param != 'hostTypeIndex':
                        value = host.get(param)
                        if value is not None:
                            config_fields[param] = value
            
            # Apply field coercion to ensure proper types
            config_fields = coerce_fields_dict(config_fields)
            
            host_config_item = {
                "measurement": "config_hosts",
                "tags": {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    # Essential host identifiers
                    "hostRef": host.get("hostRef", "unknown"),
                    "id": host.get("id", "unknown"),
                    "name": host.get("name", "unknown"),
                    "label": host.get("label", "unknown"),
                    # Host type as string (safer for unknown OS types)
                    "hostTypeIndex": str(host.get("hostTypeIndex", "unknown")),
                    # Cluster reference for host grouping
                    "clusterRef": host.get("clusterRef", "unknown")
                },
                "fields": config_fields
            }
            
            if not CMD.include or host_config_item["measurement"] in CMD.include:
                json_body.append(host_config_item)
                LOG.debug(f"Added config_hosts measurement for host {host.get('name', 'unknown')}")
            else:
                LOG.debug(f"Skipped config_hosts measurement (not in --include filter)")
        
        LOG.debug(f"collect_config_hosts: Prepared {len(json_body)} measurements for InfluxDB")
        if not CMD.doNotPost:
            client.write_points(json_body, database=INFLUXDB_DATABASE, time_precision="s")
            LOG.info("LOG: host configuration data sent")
        else:
            LOG.debug("Skipped posting to InfluxDB (--doNotPost enabled)")
            
    except RuntimeError:
        LOG.error(f"Error when attempting to post host configuration for {system_info['name']}/{system_info['wwn']}")


def collect_controller_metrics(system_info):
    """
    Collects controller performance metrics from both controllers and posts them to InfluxDB
    :param system_info: The JSON object of a storage_system
    """
    try:
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)
        json_body = list()
        
        # Since both controllers return data for all controllers in the cluster,
        # we only need to query one controller to get metrics for both
        # Use existing get_controller() logic which handles failover automatically
        
        try:
            # Create a session and use existing controller selection logic
            session = get_session()
            
            # Build controller URL using existing get_controller() logic (handles failover)
            controller_url = f"{get_controller('sys')}/{sys_id}/analyzed/controller-statistics"
            
            # Use statisticsFetchTime as required by the API method, 60 seconds for recent data
            params = {"statisticsFetchTime": "60"}
            
            LOG.debug(f"[CONTROLLER_COLLECTOR] GET {controller_url} with params {params}")
            
            # Use shorter timeout for controller metrics to avoid long delays if a controller is down
            controller_response = session.get(controller_url, params=params, timeout=(6.10, 15))
            
            LOG.debug(f"[CONTROLLER_COLLECTOR] Response status: {controller_response.status_code}")
            LOG.debug(f"[CONTROLLER_COLLECTOR] Response headers: {dict(controller_response.headers)}")
            
            controller_stats_response = controller_response.json()
            
            LOG.info(f"Retrieved controller statistics from controller API")
            LOG.debug(f"[CONTROLLER_COLLECTOR] Response type: {type(controller_stats_response)}")
            LOG.debug(f"[CONTROLLER_COLLECTOR] Response content: {controller_stats_response}")
            
            # Handle different response formats with defensive programming
            if isinstance(controller_stats_response, str):
                LOG.warning(f"API returned string instead of JSON object: {controller_stats_response}")
                return
            elif isinstance(controller_stats_response, dict):
                # Check if response has 'statistics' key (wrapped format)
                if 'statistics' in controller_stats_response:
                    controller_stats_list = controller_stats_response['statistics']
                    LOG.debug(f"[CONTROLLER_COLLECTOR] Found {len(controller_stats_list)} controllers in statistics array")
                else:
                    # Single controller response - wrap in list
                    controller_stats_list = [controller_stats_response]
                    LOG.debug(f"[CONTROLLER_COLLECTOR] Treating dict response as single controller")
            elif isinstance(controller_stats_response, list):
                # Multiple controllers response (direct list)
                controller_stats_list = controller_stats_response
                LOG.debug(f"[CONTROLLER_COLLECTOR] Found {len(controller_stats_response)} controllers in direct list")
            else:
                LOG.warning(f"Unexpected response format: {type(controller_stats_response)}")
                return
            
            # Validate we have actual controller data
            if not controller_stats_list:
                LOG.warning("No controller statistics found in API response")
                return
            
            # Process each controller's statistics
            for controller_stats in controller_stats_list:
                # Extract performance fields based on CONTROLLER_PARAMS
                controller_fields = {}
                for param in CONTROLLER_PARAMS:
                    value = controller_stats.get(param)
                    if value is not None:
                        # Handle array fields specially for InfluxDB compatibility
                        if isinstance(value, list):
                            if param == "maxCpuUtilizationPerCore":
                                # Store the maximum value from the array
                                controller_fields[f"{param}_max"] = max(value) if value else 0
                            elif param == "cpuAvgUtilizationPerCore":
                                # Store the maximum average utilization from the array
                                controller_fields[f"{param}_max"] = max(value) if value else 0
                            elif param == "cpuAvgUtilizationPerCoreStdDev":
                                # Store the maximum standard deviation from the array
                                controller_fields[f"{param}_max"] = max(value) if value else 0
                            else:
                                # For other arrays, skip or convert to string (fallback)
                                LOG.debug(f"Skipping array field {param}: {value}")
                                continue
                        else:
                            controller_fields[param] = value
                
                # Ensure we have at least some fields to prevent "missing fields" error
                if not controller_fields:
                    LOG.warning(f"No valid fields found for controller {controller_stats.get('controllerId', 'unknown')}")
                    continue
                
                # Apply field coercion to ensure proper types
                controller_fields = coerce_fields_dict(controller_fields)
                
                # Build tags for this controller
                tags = {
                    "sys_id": sys_id,
                    "sys_name": sys_name,
                    "controller_id": str(controller_stats.get("controllerId", "unknown"))
                }
                
                controller_item = {
                    "measurement": "controllers",
                    "tags": tags,
                    "fields": controller_fields
                }
                
                if CMD.showControllerMetrics:
                    LOG.info("Controller payload: %s", controller_item)
                
                if not CMD.include or controller_item["measurement"] in CMD.include:
                    json_body.append(controller_item)
                    LOG.debug(f"Added controllers measurement for controller {controller_stats.get('controllerId', 'unknown')}")
                else:
                    LOG.debug(f"Skipped controllers measurement (not in --include filter)")
                    
        except Exception as e:
            LOG.warning(f"Could not retrieve controller statistics: {e}")
            return
        
        LOG.debug(f"collect_controller_metrics: Prepared {len(json_body)} measurements for InfluxDB")
        if not CMD.doNotPost:
            client.write_points(json_body, database=INFLUXDB_DATABASE, time_precision="s")
            LOG.info("LOG: controller metrics sent")
        else:
            LOG.debug("Skipped posting to InfluxDB (--doNotPost enabled)")
            
    except Exception as e:
        LOG.error(f"Error when attempting to collect controller metrics for {system_info['name']}/{system_info['wwn']}: {e}")


def parse_retention_weeks(retention_str):
    """
    Parse retention string to return number of weeks
    Supports: 52w, 365d, 2y formats
    """
    if retention_str.endswith('y'):
        return int(retention_str[:-1]) * 52
    elif retention_str.endswith('w'):
        return int(retention_str[:-1])
    elif retention_str.endswith('d'):
        return int(retention_str[:-1]) // 7
    return 52  # Default fallback


def create_temporal_pruning_query(client, database):
    """
    Creates temporal pruning queries for measurements that preserve meaningful state
    while reducing storage overhead. Uses LAST() function to retain actual readings
    rather than meaningless averages.
    :param client: InfluxDB client instance  
    :param database: The measurement name (e.g., config_volumes, temp, power)
    """
    try:
        # Define measurement-specific tags for preserving object identity
        measurement_tags = {
            'config_volumes': ['volumeRef', 'name', 'worldWideName'],
            'config_storage_pools': ['poolRef', 'name'],
            'config_hosts': ['hostRef', 'id', 'name'],
            'config_drives': [
                'driveRef',
                'serialNumber',
                'productID',
                'driveMediaType',
                'physicalLocation__trayRef',
                'physicalLocation_slot'
            ],
            'temp': ['sys_id', 'sys_name', 'sensor_ref'],  # Temperature sensors by location
            'power': ['sys_id', 'sys_name', 'psu_ref']      # Power supplies by location
        }
        
        if database not in measurement_tags:
            LOG.warning(f"No tag definition found for {database} - skipping pruning query")
            return
            
        tags = measurement_tags[database]
        tag_clause = ', '.join([f'"{tag}"' for tag in tags])
        
        # Create pruning query: retain last sample per hour for each unique object
        pruning_select = f"""SELECT LAST(*) 
                            INTO "{INFLUXDB_DATABASE}"."pruned_retention"."{database}" 
                            FROM "{database}" 
                            WHERE (time < now()-1h) 
                            GROUP BY time(1h), {tag_clause}"""
        
        query_name = f"prune_{database}"
        client.create_continuous_query(query_name, pruning_select, INFLUXDB_DATABASE, "")
        LOG.debug(f"Created temporal pruning query for {database} with tags: {tags}")
        
    except InfluxDBClientError as err:
        LOG.info(f"Creation of pruning query for '{database}' failed: {err}")


def create_continuous_query(client, params_list, database):
    """
    Creates continuous data-pruning queries with intelligent measurement-specific strategies
    :param client: InfluxDB client instance
    :param params_list: The list of metrics to create the continuous query for
    :param database: The InfluxDB measurement to down-sample in EPA's database
    """
    try:
        # Handle measurements that use temporal pruning instead of downsampling
        pruning_measurements = [
            "temp",                    # Temperature sensors - preserve last reading per hour
            "power",                   # Power readings - preserve last reading per hour  
            "major_event_log",         # Event logs can't be averaged
            "failures",                # Failure events can't be averaged
        ]
        
        # Handle config measurements with temporal pruning
        if database.startswith('config_') or database in pruning_measurements:
            if database in ["major_event_log", "failures"]:
                LOG.info(f"Skipping continuous query for '{database}' - event data not suitable for processing")
                return
            else:
                create_temporal_pruning_query(client, database)
                return

        # Multi-tier downsampling for performance metrics
        retention_weeks = parse_retention_weeks(CMD.retention)
        
        for metric in params_list:
            # Tier 1: 5-minute averages for data older than 1 week
            ds_select_5m = f"""SELECT mean("{metric}") AS "ds_{metric}" 
                              INTO "{INFLUXDB_DATABASE}"."downsample_retention"."{database}" 
                              FROM "{database}" 
                              WHERE (time < now()-1w) GROUP BY time(5m)"""
            
            client.create_continuous_query(f"downsample_5m_{database}_{metric}", ds_select_5m, INFLUXDB_DATABASE, "")
            
            # Tier 2: 1-hour averages for data older than 4 weeks (only for long retention policies)
            if retention_weeks > 8:
                ds_select_1h = f"""SELECT mean("ds_{metric}") AS "ds_hourly_{metric}" 
                                  INTO "{INFLUXDB_DATABASE}"."longterm_retention"."{database}" 
                                  FROM "{INFLUXDB_DATABASE}"."downsample_retention"."{database}" 
                                  WHERE (time < now()-4w) GROUP BY time(1h)"""
                
                client.create_continuous_query(f"downsample_1h_{database}_{metric}", ds_select_1h, INFLUXDB_DATABASE, "")
                LOG.debug(f"Created 2-tier downsampling for {database}.{metric} (retention: {retention_weeks}w)")
            else:
                LOG.debug(f"Created 1-tier downsampling for {database}.{metric} (retention: {retention_weeks}w)")
                
    except InfluxDBClientError as err:
        LOG.info(f"Creation of continuous query on '{database}' failed: {err}")


def order_sensor_response_list(response):
    """
    Reorders the sensor readings list by ascending thermalSensorRef string for "stable" sensor ordering and tagging
    :param response: the response from the SANtricity SYMbol v2 API with environmental sensor readings
    ::return: returns a response dictionary with the sensor readings (thermalSensorRef) list items in ascending order
    """
    osensor = []
    i = 0
    for item in response['thermalSensorData']:
        pair = (item['thermalSensorRef'], i)
        osensor.append(pair)
        i = i+1
    osensor.sort()
    orderedResponse = []
    for item in osensor:
        orderedResponse.append(response['thermalSensorData'][item[1]])
    return (orderedResponse)


def ensure_database(client, dbname):
    """
    Create the InfluxDB database if it doesn't exist. Raises on failure.
    :param client: InfluxDB client instance
    :param dbname: Database name to create
    """
    try:
        client.create_database(dbname)
        LOG.info("Database '%s' created or already exists", dbname)
    except Exception as e:
        LOG.error("Failed to create database '%s': %s", dbname, e)
        raise


#######################
# MAIN FUNCTIONS ######
#######################


if __name__ == "__main__":
    executor = concurrent.futures.ThreadPoolExecutor(NUMBER_OF_THREADS)

    SESSION = get_session()
    loopIteration = 1

    # Override database name if provided
    if CMD.dbName:
        INFLUXDB_DATABASE = CMD.dbName

    client = InfluxDBClient(host=influxdb_host,
                            port=influxdb_port, database=INFLUXDB_DATABASE)

    # Handle database creation request
    if CMD.createDb:
        if not CMD.dbName:
            LOG.error("--createDb requires --dbName to be specified")
            sys.exit(1)
        try:
            ensure_database(client, INFLUXDB_DATABASE)
            LOG.info("Database creation completed. Exiting as requested.")
            sys.exit(0)
        except (InfluxDBClientError, requests.exceptions.RequestException):
            LOG.error("Database creation failed")
            sys.exit(1)

    # Ensure database exists for normal operation (not just --createDb)
    try:
        ensure_database(client, INFLUXDB_DATABASE)
        LOG.info(f"Database '{INFLUXDB_DATABASE}' is ready")
    except (InfluxDBClientError, requests.exceptions.RequestException):
        LOG.error(f"Failed to ensure database '{INFLUXDB_DATABASE}' exists")
        sys.exit(1)

    try:

        try:
            client.create_retention_policy(
                "default_retention", "1w", "1", INFLUXDB_DATABASE, True)
        except InfluxDBClientError:
            LOG.info("Updating retention policy to 1w...")
            client.alter_retention_policy("default_retention", INFLUXDB_DATABASE,
                                          "1w", "1", True)
        try:
            client.create_retention_policy(
                "downsample_retention", RETENTION_DUR, "1", INFLUXDB_DATABASE, False)
        except InfluxDBClientError:
            LOG.info(f"Updating retention policy to {RETENTION_DUR}...")
            client.alter_retention_policy("downsample_retention", INFLUXDB_DATABASE,
                                          RETENTION_DUR, "1", False)

        # Create longterm_retention policy for 2-tier downsampling (longer retention for hourly data)
        try:
            client.create_retention_policy(
                "longterm_retention", RETENTION_DUR, "1", INFLUXDB_DATABASE, False)
        except InfluxDBClientError:
            LOG.info(f"Updating longterm retention policy to {RETENTION_DUR}...")
            client.alter_retention_policy("longterm_retention", INFLUXDB_DATABASE,
                                          RETENTION_DUR, "1", False)

        # Create pruned_retention policy for config data temporal pruning
        try:
            client.create_retention_policy(
                "pruned_retention", RETENTION_DUR, "1", INFLUXDB_DATABASE, False)
        except InfluxDBClientError:
            LOG.info(f"Updating pruned retention policy to {RETENTION_DUR}...")
            client.alter_retention_policy("pruned_retention", INFLUXDB_DATABASE,
                                          RETENTION_DUR, "1", False)

        # create continuous queries that downsample our metric data
        # Only create queries for measurements that will be collected to avoid log spam
        if hasattr(CMD, 'include') and CMD.include:
            # Create queries only for included measurements
            query_mapping = {
                'disks': (DRIVE_PARAMS, "disks"),
                'systems': (SYSTEM_PARAMS, "systems"),
                'volumes': (VOLUME_PARAMS, "volumes"),
                'interface': (INTERFACE_PARAMS, "interface"),
                'power': (PSU_PARAMS, "power"),
                'temp': (SENSOR_PARAMS, "temp"),
                'config_volumes': (CONFIG_VOLUME_PARAMS, "config_volumes"),
                'config_hosts': (CONFIG_HOSTS_PARAMS, "config_hosts"),
                'config_storage_pools': (CONFIG_STORAGE_POOLS_PARAMS, "config_storage_pools"),
                'config_drives': (CONFIG_DRIVE_PARAMS, "config_drives")
            }
            for measurement in CMD.include:
                if measurement in query_mapping:
                    params, db = query_mapping[measurement]
                    create_continuous_query(client, params, db)
                    LOG.info(
                        f"Created continuous queries for included measurement: {measurement}")
        else:
            # Create all queries (default behavior when no --include specified)
            create_continuous_query(client, DRIVE_PARAMS, "disks")
            create_continuous_query(client, SYSTEM_PARAMS, "systems")
            create_continuous_query(client, VOLUME_PARAMS, "volumes")
            create_continuous_query(client, INTERFACE_PARAMS, "interface")
            create_continuous_query(client, CONTROLLER_PARAMS, "controllers")
            create_continuous_query(client, PSU_PARAMS, "power")
            create_continuous_query(client, SENSOR_PARAMS, "temp")
            create_continuous_query(client, CONFIG_STORAGE_POOLS_PARAMS, "config_storage_pools")
            create_continuous_query(client, CONFIG_VOLUME_PARAMS, "config_volumes")
            create_continuous_query(client, CONFIG_HOSTS_PARAMS, "config_hosts")

    except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError):
        LOG.exception("Failed to add configured systems!")

    checksums = {}
    while True:
        time_start = time.time()
        try:
            response = SESSION.get(get_controller("sys"))
            if response.status_code != 200:
                LOG.warning(
                    f"Unable to connect to storage-system API endpoint! Status-code={response.status_code}")
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            LOG.warning("Unable to connect to the API! %s", e)
        except Exception as e:
            LOG.warning("Unexpected exception! %s", e)
        else:
            sys = {'name': sys_name, 'wwn': sys_id}
            if CMD.showStorageNames:
                LOG.info(sys_name)

            # Conditionally collect measurements based on --include filter
            if hasattr(CMD, 'include') and CMD.include:
                LOG.info(f"Starting selective collection for measurements: {', '.join(CMD.include)}")
                # Only run functions whose measurements are included
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_storage_metrics']):
                    LOG.info("Collecting storage metrics (disks, interface, systems, volumes)...")
                    collect_storage_metrics(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_controller_metrics']):
                    LOG.info("Collecting controller metrics...")
                    collect_controller_metrics(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_symbol_stats']):
                    LOG.info("Collecting power and temperature data...")
                    collect_symbol_stats(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_system_state']):
                    LOG.info("Collecting system state and failure information...")
                    collect_system_state(sys, checksums)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_major_event_log']):
                    LOG.info("Collecting major event log (MEL)...")
                    collect_major_event_log(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_storage_pools']):
                    LOG.info("Collecting storage pool configuration...")
                    collect_config_storage_pools(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_volumes']):
                    LOG.info("Collecting volume configuration...")
                    collect_config_volumes(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_hosts']):
                    LOG.info("Collecting host configuration...")
                    collect_config_hosts(sys)
                if any(m in CMD.include for m in FUNCTION_MEASUREMENTS['collect_config_drives']):
                    LOG.info("Collecting drive configuration...")
                    collect_config_drives(sys)
            else:
                # Default: collect all measurements
                LOG.info("Starting full collection cycle for all measurements...")
                LOG.info("Collecting storage metrics (disks, interface, systems, volumes)...")
                collect_storage_metrics(sys)
                LOG.info("Collecting controller metrics...")
                collect_controller_metrics(sys)
                LOG.info("Collecting power and temperature data...")
                collect_symbol_stats(sys)
                LOG.info("Collecting system state and failure information...")
                collect_system_state(sys, checksums)
                LOG.info("Collecting major event log (MEL)...")
                collect_major_event_log(sys)
                LOG.info("Collecting storage pool configuration...")
                collect_config_storage_pools(sys)
                LOG.info("Collecting volume configuration...")
                collect_config_volumes(sys)
                LOG.info("Collecting host configuration...")
                collect_config_hosts(sys)
                LOG.info("Collecting drive configuration...")
                collect_config_drives(sys)
                
            LOG.info(f"Collection cycle completed for system '{sys_name}' ({sys_id})")

        time_difference = time.time() - time_start
        if CMD.showIteration:
            LOG.info(
                f"Time interval: {CMD.intervalTime:07.4f} Time to collect and send: {time_difference:07.4f} Iteration: {loopIteration:00.0f}")
            loopIteration += 1

        wait_time = CMD.intervalTime - time_difference
        if CMD.intervalTime < time_difference:
            LOG.error(
                f"The interval specified is not long enough. Time used: {time_difference:07.4f} Time interval specified: {CMD.intervalTime:07.4f}")
            wait_time = time_difference

        time.sleep(wait_time)
