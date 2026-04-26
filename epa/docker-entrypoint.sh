#!/bin/sh

# Username and password may be provided via Docker compose file:
# epa/docker-compose.yaml
# 
# sysname can be arbitrary alphanumeric name, but if you want to keep it consistent,
#   use E-Series array name (see screenshots on where to find them)
#
# sysid should be array WWN (also, see screenshots on where to find it)
# 
# include can be space-separated list of measurements to collect:
#   disks, interface, systems, volumes, power, temp, major_event_log, failures
#   If not specified, all measurements are collected (default behavior)
# 
# Find other details with:
# python3 collector.py -h

# Check if help is requested
if [ "$1" = "-h" ] || [ "$1" = "--help" ] || [ "$1" = "help" ]; then
    exec python collector.py -h
fi

# Build the base command
CMD="python collector.py"

# Normal operation mode - requires SANtricity credentials
if [ -z "${USERNAME}" ] || [ -z "${PASSWORD}" ] || [ -z "${API}" ]; then
    echo "ERROR: Normal operation requires USERNAME, PASSWORD, and API"
    exit 1
fi

CMD="${CMD} -u ${USERNAME} -p ${PASSWORD} --api ${API}"

# Add API port if specified
if [ -n "${API_PORT}" ]; then
    CMD="${CMD} --api-port ${API_PORT}"
fi

# Disable TLS certificate verification if requested (lab/dev use only)
if [ -n "${TLS_VERIFY}" ] && [ "${TLS_VERIFY}" = "false" ]; then
    echo "WARNING: TLS_VERIFY=false - SSL certificate verification is DISABLED"
    CMD="${CMD} --no-verify-ssl"
fi

# Add include filter if specified
if [ -n "${INCLUDE}" ]; then
    echo "INCLUDE environment variable set: '${INCLUDE}'"
    CMD="${CMD} --include ${INCLUDE}"
else
    echo "INCLUDE environment variable not set, collecting all measurements"
fi

# Add collection interval if specified
if [ -n "${COLLECTION_INTERVAL}" ]; then
    echo "COLLECTION_INTERVAL environment variable set: '${COLLECTION_INTERVAL}'"
    CMD="${CMD} --intervalTime ${COLLECTION_INTERVAL}"
fi

# Add Prometheus port if specified
if [ -n "${PROMETHEUS_PORT}" ]; then
    echo "PROMETHEUS_PORT environment variable set: '${PROMETHEUS_PORT}'"
    CMD="${CMD} --prometheus-port ${PROMETHEUS_PORT}"
fi

# Add debug flag if specified
if [ -n "${DEBUG}" ] && [ "${DEBUG}" = "true" ]; then
    echo "DEBUG environment variable set: enabling debug logging"
    CMD="${CMD} --debug"
fi

CMD="${CMD} -i -s"

# Execute the command
echo "Executing: ${CMD}"
exec ${CMD}

