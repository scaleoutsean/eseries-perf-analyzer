#!/bin/sh

# Docker/Kubernetes Entrypoint for E-Series Performance Analyzer Collector
#
# (c) 2025 scaleoutSean (Github)
# License: MIT
#
# This entrypoint is designed for containerized deployments using environment variables.
# Configuration is provided via ENV vars in docker-compose.yaml or Kubernetes manifests.
# 
# For CLI usage with config files, run the collector directly:
# python3 collector.py --config ef600-config.yaml
# Or: python3 -m app --config ef600-config.yaml
#
# System name (sysname) and system ID (sysid/WWN) are auto-detected by Colletor 
# from the API. No need to provide them manually as it was done in EPA v3.
#
# Required environment variables for containerized mode:
# - INFLUX_HOST: InfluxDB server hostname (e.g., influxdb)
# - INFLUX_PORT: InfluxDB server port (e.g., 8181)
# - INFLUX_DB: InfluxDB database name (e.g., epa)
# - INFLUXDB3_AUTH_TOKEN_FILE: Path to InfluxDB authentication token file
# - API: Comma-separated list of E-Series API endpoints (e.g., 10.0.0.1,10.0.0.2)  
# - USERNAME: E-Series management username (e.g., admin)
# - PASSWORD: E-Series management password
#
# Optional environment variables:
# - INFLUXDB3_TLS_CA: Path to CA certificate file for TLS verification
# - TLS_VALIDATION: TLS validation mode (strict, normal, none) - default: strict
# - INTERVAL_TIME: Collection interval in seconds - default: 60
# - THREADS: Number of collection threads - default: 4
# - LOG_LEVEL: Log level (DEBUG, INFO, WARNING, ERROR) - default: INFO
# - MAX_ITERATIONS: Maximum iterations before exit - default: 0 (infinite)

# Check for --config argument and reject it in containerized mode
for arg in "$@"; do
    case $arg in
        --config)
            echo "ERROR: --config is not supported in containerized mode"
            echo "Use environment variables in docker-compose.yaml or Kubernetes manifests"
            echo "For CLI usage with config files, run the collector directly outside containers"
            exit 1
            ;;
    esac
done

# Build command line arguments from environment variables
ARGS=""

# Build InfluxDB URL from INFLUX_HOST and INFLUX_PORT
if [ -n "$INFLUX_HOST" ] && [ -n "$INFLUX_PORT" ]; then
    INFLUX_URL="https://$INFLUX_HOST:$INFLUX_PORT"
    ARGS="$ARGS --influxdbUrl $INFLUX_URL"
fi

# InfluxDB database name
if [ -n "$INFLUX_DB" ]; then
    ARGS="$ARGS --influxdbDatabase $INFLUX_DB"
fi

# Read InfluxDB token from file if specified
if [ -n "$INFLUXDB3_AUTH_TOKEN_FILE" ] && [ -f "$INFLUXDB3_AUTH_TOKEN_FILE" ]; then
    TOKEN=$(cat "$INFLUXDB3_AUTH_TOKEN_FILE" | tr -d '\n\r')
    if [ -n "$TOKEN" ]; then
        ARGS="$ARGS --influxdbToken $TOKEN"
    fi
fi

# E-Series API endpoints and credentials
if [ -n "$API" ] && [ -n "$USERNAME" ] && [ -n "$PASSWORD" ]; then
    # Convert comma-separated API list to space-separated for --api argument
    API_LIST=$(echo "$API" | tr ',' ' ')
    ARGS="$ARGS --api $API_LIST -u $USERNAME -p $PASSWORD"
fi

# Optional arguments
if [ -n "$INFLUXDB3_TLS_CA" ]; then
    ARGS="$ARGS --tlsCa $INFLUXDB3_TLS_CA"
fi
if [ -n "$TLS_VALIDATION" ]; then
    ARGS="$ARGS --tlsValidation $TLS_VALIDATION"
fi
if [ -n "$INTERVAL_TIME" ]; then
    ARGS="$ARGS --intervalTime $INTERVAL_TIME"
fi
if [ -n "$THREADS" ]; then
    ARGS="$ARGS --threads $THREADS"
fi
if [ -n "$LOG_LEVEL" ]; then
    ARGS="$ARGS --loglevel $LOG_LEVEL"
fi
if [ -n "$MAX_ITERATIONS" ]; then
    ARGS="$ARGS --maxIterations $MAX_ITERATIONS"
fi
if [ -n "$COLLECTOR_LOG_LEVEL" ]; then
    ARGS="$ARGS --loglevel $COLLECTOR_LOG_LEVEL"
fi
if [ -n "$COLLECTOR_LOG_FILE" ] && [ "$COLLECTOR_LOG_FILE" != "None" ]; then
    ARGS="$ARGS --logfile $COLLECTOR_LOG_FILE"
fi

# Change to the app directory and run the collector
cd /home/app

# Debug output (only if LOG_LEVEL is DEBUG)
if [ "$LOG_LEVEL" = "DEBUG" ]; then
    echo "DEBUG: Executing: python -m app $ARGS $*"
fi

exec python -m app $ARGS "$@"

