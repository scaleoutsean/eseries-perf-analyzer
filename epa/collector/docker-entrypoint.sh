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

# Build the base command
CMD="python collector.py"

# Database creation mode vs normal operation
if [ "${CREATE_DB}" = "true" ] || [ "${CREATE_DB}" = "1" ]; then
    # Database creation mode - only requires database parameters
    CMD="${CMD} --createDb"
    
    if [ -n "${DB_NAME}" ]; then
        CMD="${CMD} --dbName ${DB_NAME}"
    else
        echo "ERROR: CREATE_DB=true requires DB_NAME to be set"
        exit 1
    fi
    
    if [ -n "${DB_ADDRESS}" ] && [ -n "${DB_PORT}" ]; then
        CMD="${CMD} --dbAddress ${DB_ADDRESS}:${DB_PORT}"
    fi
else
    # Normal operation mode - requires SANtricity credentials
    if [ -z "${USERNAME}" ] || [ -z "${PASSWORD}" ] || [ -z "${API}" ] || [ -z "${SYSNAME}" ] || [ -z "${SYSID}" ]; then
        echo "ERROR: Normal operation requires USERNAME, PASSWORD, API, SYSNAME, and SYSID"
        exit 1
    fi
    
    CMD="${CMD} -u ${USERNAME} -p ${PASSWORD} --api ${API} --sysname ${SYSNAME} --sysid ${SYSID}"
    
    # Add optional database name override
    if [ -n "${DB_NAME}" ]; then
        CMD="${CMD} --dbName ${DB_NAME}"
    fi
    
    # Add database address and retention settings
    if [ -n "${DB_ADDRESS}" ] && [ -n "${DB_PORT}" ]; then
        CMD="${CMD} --dbAddress ${DB_ADDRESS}:${DB_PORT}"
    fi
    
    if [ -n "${RETENTION_PERIOD}" ]; then
        CMD="${CMD} --retention ${RETENTION_PERIOD}"
    fi
    
    # Add default flags for normal operation
    CMD="${CMD} -i -s"
fi

# Execute the command
echo "Executing: ${CMD}"
exec ${CMD}

