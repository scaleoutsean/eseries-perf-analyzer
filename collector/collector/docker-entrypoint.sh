#!/bin/sh

# Username and password may be provided via Docker compose file:
# collector/docker-compose.yaml
# 
# sysname can be arbitrary alphanumeric name, but if you want to keep it consistent,
#   use E-Series array name (see screenshots on where to find them)
# The same sysname should be provided to dbmanager in collector/dbmanager/config.json!
#
# sysid should be array WWN (also, see screenshots on where to find it)
# 
# Find other details with:
# python3 collector.py -h

python collector.py -u ${USERNAME} -p ${PASSWORD} --api ${API} --dbAddress ${DB_ADDRESS}:${DB_PORT} --retention ${RETENTION_PERIOD} --sysname ${SYSNAME} --sysid ${SYSID} -i -s

