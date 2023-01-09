#!/usr/bin/env python3
"""
Reads NetApp E-Series array names from config file and uploads as tags to InfluxDB server.
May also perform other database-related maintenance.
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

NUMBER_OF_THREADS = 2
INFLUXDB_HOSTNAME = 'influxdb'
INFLUXDB_PORT = 8086
INFLUXDB_DATABASE = 'eseries'
DEFAULT_RETENTION = '52w'  # 1y

__version__ = '1.0'

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

PARSER.add_argument('-t', '--intervalTime', type=int, default=300,
                    help='Provide the time (seconds) in which the script polls and sends folder '
                         'names from the JSON configuration file to InfluxDB to be exposed in Grafana. '
                         'Default: 300 (seconds). <int>')
PARSER.add_argument('--dbAddress', default='influxdb:8086', type=str, required=True,
                    help='<Required> The hostname (IPv4 address or FQDN) and port for InfluxDB. '
                    'Default: influxdb:8086. Use public IPv4 of InfluxDB system rather than the container name'
                    ' when running collector externally. In EPA InfluxDB uses port 8086. Example: 7.7.7.7:8086.')
PARSER.add_argument('-r', '--retention', type=str, default='52w',
                    help='The default retention duration for InfluxDB. At the moment, not used.')
PARSER.add_argument('-i', '--showIteration', action='store_true', default=0,
                    help='Outputs the current loop iteration')
PARSER.add_argument('-n', '--doNotPost', action='store_true', default=0,
                    help='Pull information, but do not post to InfluxDB')
CMD = PARSER.parse_args()


if CMD.dbAddress == '' or CMD.dbAddress == None:
    influxdb_host = INFLUXDB_HOSTNAME
    influxdb_port = INFLUXDB_PORT
else:
    influxdb_host = CMD.dbAddress.split(":")[0]
    influxdb_port = CMD.dbAddress.split(":")[1]

if CMD.retention == '' or CMD.retention == None:
    retention = DEFAULT_RETENTION
else:
    retention = CMD.retention


#######################
# HELPER FUNCTIONS ####
#######################


def get_configuration():
    try:
        with open("config.json") as config_file:
            config_data = json.load(config_file)
            if config_data:
                return config_data
    except:
        return dict()


def update_system_folders(folder_body):
    """
    Collects all folders defined in config.json and posts them to InfluxDB
    :param systems: List of all system folders (sys_name's)
    """
    try:
        if not CMD.doNotPost:
            client = InfluxDBClient(host=influxdb_host,
                                    port=influxdb_port, database=INFLUXDB_DATABASE)
            client.drop_measurement("folders")
            LOG.info("Uploading folders to InfluxDB: {}".format(folder_body))
            client.write_points(
                folder_body, database=INFLUXDB_DATABASE, time_precision="s")
    except RuntimeError:
        LOG.error("Error when attempting to create Grafana tags/folders")
    return

#######################
# MAIN FUNCTIONS ######
#######################


if __name__ == "__main__":
    executor = concurrent.futures.ThreadPoolExecutor(NUMBER_OF_THREADS)
    loopIteration = 1

    client = InfluxDBClient(host=influxdb_host,
                            port=influxdb_port, database=INFLUXDB_DATABASE)
    client.create_database(INFLUXDB_DATABASE)

    try:
        LOG.info("Reading config.json...")
        configuration = get_configuration()
        folder_body = list()
        for item in configuration['storage_systems']:
            # print(item['addresses'][0])
            sys_item = dict(
                measurement="folders",
                tags=dict(
                    folder_name="All Storage Systems",
                    sys_name=item['name']
                ),
                fields=dict(dummy=0)
            )
            folder_body.append(sys_item)
    except requests.exceptions.HTTPError or requests.exceptions.ConnectionError:
        LOG.exception("Failed to add configured systems!")
    except json.decoder.JSONDecodeError:
        LOG.exception("Failed to open configuration file due to invalid JSON!")

    last_folder_collection = -1

    while True:
        time_start = time.time()
        try:
            # LOG.info("Updating folders based upon folder update interval")
            update_system_folders(folder_body)
        except requests.exceptions.HTTPError or requests.exceptions.ConnectionError as e:
            LOG.warning(
                "Unable to connect!", e)
        else:
            LOG.info("Update loop evaluation complete, awaiting next run...")

        time_difference = time.time() - time_start
        if CMD.showIteration:
            LOG.info("Time interval: {:07.4f} Time to collect and send:"
                     " {:07.4f} Iteration: {:00.0f}"
                     .format(CMD.intervalTime, time_difference, loopIteration))
            loopIteration += 1

        # Dynamic wait time to get the proper interval
        wait_time = CMD.intervalTime - time_difference
        # LOG.info("Time to wait: {:07.4f}".format(wait_time))
        if CMD.intervalTime < time_difference:
            LOG.error("The interval specified is not long enough. Time used: {:07.4f} "
                      "Time interval specified: {:07.4f}"
                      .format(time_difference, CMD.intervalTime))
            wait_time = time_difference

        time.sleep(wait_time)
