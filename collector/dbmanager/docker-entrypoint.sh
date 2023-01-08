#!/bin/sh

# InfluxDB v1 does not require username/password
# Unlike in collector intervals can be long as long as dbmanager is restarted
#   each time after new collector is added and config.json updated
# 
# Find other details with:
# python3 db_manager.py -h
#
# Example: python3 db_manager.py --dbAddress 1.2.3.4:8086 -t 600

python db_manager.py --dbAddress ${DB_ADDRESS}:${DB_PORT} -t ${COLLECTION_INTERVAL} --retention ${RETENTION_PERIOD} -i

