#!/bin/sh

# Username and password may be provided via Docker compose file located
# in the root of the project (docker-compose.yml) under stats_collector

python collector.py -u ${USERNAME} -p ${PASSWORD} --api ${API} --dbAddress ${DB_ADDRESS}:${DB_PORT} --retention ${RETENTION_PERIOD} --sysname ${SYSNAME} --sysid ${SYSID} -i -s

