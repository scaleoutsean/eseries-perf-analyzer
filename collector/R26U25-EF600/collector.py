#!/usr/bin/env python3
"""
Retrieves and collects data from the the NetApp E-Series API server
and sends the data to an InfluxDB server
"""
import struct
import time
import logging
import socket
import argparse
import concurrent.futures
import requests
import json
import pickle
import hashlib
from datetime import datetime
import random
from datetime import datetime
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError

DEFAULT_USERNAME = 'monitor'
DEFAULT_PASSWORD = 'monitor123'

# global DEFAULT_SYSTEM_NAME
# global DEFAULT_SYSTEM_ID
# global sys_name
# global sys_id
# DEFAULT_SYSTEM_NAME = 'rack26u25-ef600'
# DEFAULT_SYSTEM_ID = '600A098000F63714000000005E79C888'
# DEFAULT_SYSTEM_API_IP = '5.5.5.5'
DEFAULT_SYSTEM_NAME = ''
DEFAULT_SYSTEM_ID = ''
DEFAULT_SYSTEM_API_IP = ''

DEFAULT_SYSTEM_PORT = '8443'
# DEFAULT_SYSTEM_EP = 'https://' + DEFAULT_SYSTEM_API_IP + \
#    ':' + DEFAULT_SYSTEM_PORT + '/devmgr/v2/storage-systems'

INFLUXDB_HOSTNAME = 'influxdb'
INFLUXDB_PORT = 8086
INFLUXDB_DATABASE = 'eseries'
DEFAULT_RETENTION = '52w'  # 1y

# NOTE(bdustin): time in seconds between folder collections
# FOLDER_COLLECTION_INTERVAL = 86400*365*10
# FOLDER_COLLECTION_INTERVAL = 120

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
    "maxCpuUtilizationPerCore"
    "cpuAvgUtilization",
    "cpuAvgUtilizationPerCore"
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
    'writeThroughput'
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


#######################
# PARAMETERS ##########
#######################

NUMBER_OF_THREADS = 8

# LOGGING
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
requests.packages.urllib3.disable_warnings()
LOG = logging.getLogger("collector")

# Disables reset connection warning message if the connection time is too long
logging.getLogger('requests.packages.urllib3.connectionpool').setLevel(
    logging.WARNING)


#######################
# ARGUMENT PARSER #####
#######################

PARSER = argparse.ArgumentParser()

PARSER.add_argument('-u', '--username', default='', type=str, required=True,
                    help='<Required> Username to connect to the SANtricity API. '
                         'Default: \'' + DEFAULT_USERNAME + '\'. <String>')
PARSER.add_argument('-p', '--password', default='', type=str, required=True,
                    help='<Required> Password for this user to connect to the SANtricity API. '
                         'Default: \'' + DEFAULT_PASSWORD + '\'. <String>')
PARSER.add_argument('--api', default='',  nargs='+', required=True,
                    help='<Required> The IPv4 address for the SANtricity API endpoint. '
                         'Example: --api 5.5.5.5 6.6.6.6. Port number is auto-set to: \'' +
                    DEFAULT_SYSTEM_PORT + '\'. '
                         'May be provided twice (for two controllers). <IPv4 Address>')
PARSER.add_argument('--sysname', default='', type=str, required=True,
                    help='<Required> SANtricity system\'s user-configured array name. '
                         ' Example: dc1r226-elk. Default: None. <String>')
PARSER.add_argument('--sysid', default='', type=str, required=True,
                    help='<Required> SANtricity storage system\'s WWN. '
                         'Example: 600A098000F63714000000005E79C17C. Default: None. <String>')
PARSER.add_argument('-t', '--intervalTime', type=int, default=60, choices=[60, 120, 300, 600],
                    help='Interval (seconds) to poll and send data from the SANtricity API '
                    ' to InfluxDB. Default: 60. <Integer>')
PARSER.add_argument('--dbAddress', default='influxdb:8086', type=str, required=True,
                    help='<Required> The hostname (IPv4 address or FQDN) and the port for InfluxDB. '
                    'Default: influxdb:8086. Use public IPv4 of InfluxDB system rather than container name'
                    ' when running collector externally. In EPA InfluxDB uses port 8086. Example: 7.7.7.7:8086.')
PARSER.add_argument('-r', '--retention', default=DEFAULT_RETENTION, type=str, required=False,
                    help='Data retention for InfluxDB as an integer suffixed by a calendar unit. '
                    'Example: 4w translates into 28 day data retention. Default: 52w. '
                    'Default: \'' + DEFAULT_RETENTION + '\'.')
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
PARSER.add_argument('-c', '--showSystemMetrics', action='store_true', default=0,
                    help='Outputs the system payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-m', '--showMELMetrics', action='store_true', default=0,
                    help='Outputs the MEL payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-e', '--showStateMetrics', action='store_true', default=0,
                    help='Outputs the state payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-g', '--showInterfaceMetrics', action='store_true', default=0,
                    help='Outputs the interface payload metrics from the SANtricity API to console. Optional. <switch>')
PARSER.add_argument('-i', '--showIteration', action='store_true', default=0,
                    help='Outputs the current loop iteration. Optional. <switch>')
PARSER.add_argument('-n', '--doNotPost', action='store_true', default=0,
                    help='Pull information from SANtricity, but do not send it to InfluxDB.  Optional. <swtich>')
CMD = PARSER.parse_args()

if CMD.sysname == '' or CMD.sysname == None:
    LOG.warning("sysname not provided. Using default: %s", DEFAULT_SYSTEM_NAME)
    sys_name = DEFAULT_SYSTEM_NAME
else:
    sys_name = CMD.sysname

if CMD.sysid == '' or CMD.sysid == None:
    LOG.warning("sysid not provided. Using default: %s", DEFAULT_SYSTEM_ID)
    sys_id = DEFAULT_SYSTEM_ID
else:
    sys_id = CMD.sysid

if CMD.dbAddress == '' or CMD.dbAddress == None:
    LOG.warning("InfluxDB server was not provided. Default setting (influxdb:8086) works only when collector and InfluxDB are on same host")
    influxdb_host = INFLUXDB_HOSTNAME
    influxdb_port = INFLUXDB_PORT
else:
    influxdb_host = CMD.dbAddress.split(":")[0]
    influxdb_port = CMD.dbAddress.split(":")[1]


#######################
# HELPER FUNCTIONS ####
#######################


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


def get_controller():
    if (len(CMD.api) == 0) or (CMD.api == None) or (CMD.api == ''):
        storage_controller_ep = 'https://' + \
            DEFAULT_SYSTEM_API_IP + ':' + DEFAULT_SYSTEM_PORT + '/devmgr/v2/storage-systems'
    elif (len(CMD.api) == 1):
        storage_controller_ep = 'https://' + \
            CMD.api[0] + ':' + DEFAULT_SYSTEM_PORT + \
            '/devmgr/v2/storage-systems'
    else:
        controller = random.randrange(0, 2)
        storage_controller_ep = 'https://' + \
            CMD.api[controller] + ':' + DEFAULT_SYSTEM_PORT + \
            '/devmgr/v2/storage-systems'
    return (storage_controller_ep)


# def get_system_name(sys):
    #sys_id = CMD.sysid
    #sys_name = CMD.sysname
    #if not sys_name or len(sys_name) <= 0:
    #    sys_name = sys_id
    #if not sys_name or len(sys_name) <= 0:
    #    sys_name = DEFAULT_SYSTEM_NAME
    #    sys_id = DEFAULT_SYSTEM_ID
    #return sys_name, sys_id


def get_drive_location(sys_id, session):
    """
    :param sys_id: Storage system ID (WWN) on the controller
    :param session: the session of the thread that calls this definition
    ::return: returns a dictionary containing the disk id matched up against
    the tray id it is located in:
    """
    hardware_list = session.get("{}/{}/hardware-inventory".format(
        get_controller(), sys_id)).json()
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


def collect_storage_metrics(sys):
    """
    Collects all defined storage metrics and posts them to InfluxDB
    :param sys: The JSON object of a storage system
    """
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)

        # sys_name = (get_system_name(sys))[0]
        # sys_id = (get_system_name(sys))[1]

        json_body = list()

        drive_stats_list = session.get(("{}/{}/analysed-drive-statistics").format(
            get_controller(), sys_id)).json()
        drive_locations = get_drive_location(sys_id, session)
        if CMD.showDriveNames:
            for stats in drive_stats_list:
                location_send = drive_locations.get(stats["diskId"])
                LOG.info(("Tray{:02.0f}, Slot{:03.0f}").format(
                    location_send[0], location_send[1]))

        for stats in drive_stats_list:
            disk_location_info = drive_locations.get(stats["diskId"])
            disk_item = dict(
                measurement="disks",
                tags=dict(
                    sys_id=sys_id,
                    sys_name=sys_name,
                    sys_tray=("{:02.0f}").format(disk_location_info[0]),
                    sys_tray_slot=("{:03.0f}").format(disk_location_info[1])
                ),
                fields=dict(
                    (metric, stats.get(metric)) for metric in DRIVE_PARAMS
                )
            )
            if CMD.showDriveMetrics:
                LOG.info("Drive payload: %s", disk_item)
            json_body.append(disk_item)

        interface_stats_list = session.get(("{}/{}/analysed-interface-statistics").format(
            get_controller(), sys_id)).json()
        if CMD.showInterfaceNames:
            for stats in interface_stats_list:
                LOG.info(stats["interfaceId"])
        for stats in interface_stats_list:
            if_item = dict(
                measurement="interface",
                tags=dict(
                    sys_id=sys_id,
                    sys_name=sys_name,
                    interface_id=stats["interfaceId"],
                    channel_type=stats["channelType"]
                ),
                fields=dict(
                    (metric, stats.get(metric)) for metric in INTERFACE_PARAMS
                )
            )
            if CMD.showInterfaceMetrics:
                LOG.info("Interface payload: %s", if_item)
            json_body.append(if_item)

        system_stats_list = session.get(("{}/{}/analysed-system-statistics").format(
            get_controller(), sys_id)).json()
        sys_item = dict(
            measurement="systems",
            tags=dict(
                sys_id=sys_id,
                sys_name=sys_name
            ),
            fields=dict(
                (metric, system_stats_list.get(metric)) for metric in SYSTEM_PARAMS
            )
        )
        if CMD.showSystemMetrics:
            LOG.info("System payload: %s", sys_item)
        json_body.append(sys_item)

        volume_stats_list = session.get(("{}/{}/analysed-volume-statistics").format(
            get_controller(), sys_id)).json()
        if CMD.showVolumeNames:
            for stats in volume_stats_list:
                LOG.info(stats["volumeName"])
        for stats in volume_stats_list:
            vol_item = dict(
                measurement="volumes",
                tags=dict(
                    sys_id=sys_id,
                    sys_name=sys_name,
                    vol_name=stats["volumeName"]
                ),
                fields=dict(
                    (metric, stats.get(metric)) for metric in VOLUME_PARAMS
                )
            )
            if CMD.showVolumeMetrics:
                LOG.info("Volume payload: %s", vol_item)
            json_body.append(vol_item)

        if not CMD.doNotPost:
            client.write_points(
                json_body, database=INFLUXDB_DATABASE, time_precision="s")

    except RuntimeError:
        LOG.error(
            ("Error when attempting to post statistics for {}/{}").format(sys["name"], sys["wwn"]))


def collect_major_event_log(sys):
    """
    Collects all defined MEL metrics and posts them to InfluxDB
    :param sys: The JSON object of a storage_system
    """
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)

        # sys_name = get_system_name(sys)[0]
        # sys_id = get_system_name(sys)[1]
        json_body = list()
        start_from = -1
        mel_grab_count = 8192
        query = client.query(
            "SELECT id FROM major_event_log WHERE sys_id='%s' ORDER BY time DESC LIMIT 1" % sys_id)

        if query:
            start_from = int(next(query.get_points())["wwn"]) + 1

        mel_response = session.get(("{}/{}/mel-events").format(get_controller(), sys_id),
                                   params={"count": mel_grab_count, "startSequenceNumber": start_from}, timeout=(6.10, CMD.intervalTime*2)).json()
        if CMD.showMELMetrics:
            LOG.info("Starting from %s", str(start_from))
            LOG.info("Grabbing %s MELs", str(len(mel_response)))
        for mel in mel_response:
            item = dict(
                measurement="major_event_log",
                tags=dict(
                    sys_id=sys_id,
                    sys_name=sys_name,
                    event_type=mel["eventType"],
                    time_stamp=mel["timeStamp"],
                    category=mel["category"],
                    priority=mel["priority"],
                    critical=mel["critical"],
                    ascq=mel["ascq"],
                    asc=mel["asc"]
                ),
                fields=dict(
                    (metric, mel.get(metric)) for metric in MEL_PARAMS
                ),
                time=datetime.utcfromtimestamp(
                    int(mel["timeStamp"])).isoformat()
            )
            if CMD.showMELMetrics:
                LOG.info("MEL payload: %s", item)
            json_body.append(item)
        client.write_points(
            json_body, database=INFLUXDB_DATABASE, time_precision="s")
    except RuntimeError:
        LOG.error(
            ("Error when attempting to post MEL for {}/{}").format(sys["name"], sys["wwn"]))


def create_failure_dict_item(sys_id, sys_name, fail_type, obj_ref, obj_type, is_active, the_time):
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


def collect_system_state(sys, checksums):
    """
    Collects state information from the storage system and posts it to InfluxDB
    :param sys: The JSON object of a storage_system
    """
    try:
        session = get_session()
        client = InfluxDBClient(host=influxdb_host,
                                port=influxdb_port, database=INFLUXDB_DATABASE)

        sys_id = sys["wwn"]
        sys_name = sys["name"]
        failure_response = session.get(
            ("{}/{}/failures").format(get_controller(), sys_id)).json()

        # we can skip us if this is the same response we handled last time
        old_checksum = checksums.get(str(sys_id))
        new_checksum = hashlib.md5(
            str(failure_response).encode("utf-8")).hexdigest()
        if old_checksum is not None and str(new_checksum) == str(old_checksum):
            return
        checksums.update({str(sys_id): str(new_checksum)})

        # pull most recent failures for this system from our database, including their active status
        query_string = (
            "SELECT last(\"type_of\"),failure_type,object_ref,object_type,active FROM \"failures\" WHERE (\"sys_id\" = '{}') GROUP BY \"sys_name\", \"failure_type\"").format(sys_id)
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
                if CMD.showStateMetrics:
                    LOG.info("Failure payload T1: %s", item)
                json_body.append(create_failure_dict_item(sys_id, sys_name,
                                                          r_fail_type, r_obj_ref, r_obj_type,
                                                          True, datetime.utcnow().isoformat()))

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
                if CMD.showStateMetrics:
                    LOG.info("Failure payload T2: %s", item)
                json_body.append(create_failure_dict_item(sys_id, sys_name,
                                                          p_fail_type, p_obj_ref, p_obj_type,
                                                          False, datetime.utcnow().isoformat()))

        # write failures to InfluxDB
        if CMD.showStateMetrics:
            LOG.info("Writing {} failures".format(len(json_body)))
        client.write_points(json_body, database=INFLUXDB_DATABASE)

    except RuntimeError:
        LOG.error(
            ("Error when attempting to post state information for {}/{}").format(sys["name"], sys["id"]))


def create_continuous_query(params_list, database):
    try:
        for metric in params_list:
            ds_select = "SELECT mean(\"" + metric + "\") AS \"ds_" + metric + "\" INTO \"" + INFLUXDB_DATABASE + \
                "\".\"downsample_retention\".\"" + database + "\" FROM \"" + \
                database + "\" WHERE (time < now()-1w) GROUP BY time(5m)"
            client.create_continuous_query(
                "downsample_" + database + "_" + metric, ds_select, INFLUXDB_DATABASE, "")
    except Exception as err:
        LOG.info(
            "Creation of continuous query on '{}' failed: {}".format(database, err))


#######################
# MAIN FUNCTIONS ######
#######################


if __name__ == "__main__":
    executor = concurrent.futures.ThreadPoolExecutor(NUMBER_OF_THREADS)

    SESSION = get_session()
    loopIteration = 1

    client = InfluxDBClient(host=influxdb_host,
                            port=influxdb_port, database=INFLUXDB_DATABASE)
    client.create_database(INFLUXDB_DATABASE)

    storage_controller_ep = get_controller()

    try:
        SESSION.get(storage_controller_ep, timeout=30)

        try:
            client.create_retention_policy(
                "default_retention", "1w", "1", INFLUXDB_DATABASE, True)
        except InfluxDBClientError:
            LOG.info("Updating retention policy to {}...".format("1w"))
            client.alter_retention_policy("default_retention", INFLUXDB_DATABASE,
                                          "1w", "1", True)
        try:
            client.create_retention_policy(
                "downsample_retention", DEFAULT_RETENTION, "1", INFLUXDB_DATABASE, False)
        except InfluxDBClientError:
            LOG.info("Updating retention policy to {}...".format(retention))
            client.alter_retention_policy("downsample_retention", INFLUXDB_DATABASE,
                                          DEFAULT_RETENTION, "1", False)

        # set up continuous queries that will downsample our metric data periodically
        create_continuous_query(DRIVE_PARAMS, "disks")
        create_continuous_query(SYSTEM_PARAMS, "system")
        create_continuous_query(VOLUME_PARAMS, "volumes")
        create_continuous_query(INTERFACE_PARAMS, "interface")

    except requests.exceptions.HTTPError or requests.exceptions.ConnectionError:
        LOG.exception("Failed to add configured systems!")

    checksums = dict()
    while True:
        time_start = time.time()
        try:
            response = SESSION.get(storage_controller_ep)
            if response.status_code != 200:
                LOG.warning(
                    "We were unable to retrieve the storage-system list! Status-code={}".format(response.status_code))
        except requests.exceptions.HTTPError or requests.exceptions.ConnectionError as e:
            LOG.warning(
                "Unable to connect to the API to get storage-system list!", e)
        except Exception as e:
            LOG.warning("Unexpected exception!", e)
        else:
            sys = {'name': sys_name, 'wwn': sys_id}
            if CMD.showStorageNames:
                LOG.info(sys_name)

            collector = [executor.submit(
                collect_storage_metrics, sys)]
            concurrent.futures.wait(collector)

            collector = [executor.submit(
                collect_system_state, sys, checksums)]
            concurrent.futures.wait(collector)

            collector = [executor.submit(
                collect_major_event_log, sys)]
            concurrent.futures.wait(collector)

        time_difference = time.time() - time_start
        if CMD.showIteration:
            LOG.info("Time interval: {:07.4f} Time to collect and send:"
                     " {:07.4f} Iteration: {:00.0f}"
                     .format(CMD.intervalTime, time_difference, loopIteration))
            loopIteration += 1

        wait_time = CMD.intervalTime - time_difference
        if CMD.intervalTime < time_difference:
            LOG.error("The interval specified is not long enough. Time used: {:07.4f} "
                      "Time interval specified: {:07.4f}"
                      .format(time_difference, CMD.intervalTime))
            wait_time = time_difference

        time.sleep(wait_time)
