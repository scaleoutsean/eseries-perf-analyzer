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
# python3 -m app.collector --config ef600-config.yaml
#
# System name (sysname) and system ID (sysid/WWN) are auto-detected by Colletor 
# from the API. No need to provide them manually as it was done in EPA v3.
#
# Required environment variables for containerized mode:
# - INF_URL: InfluxDB server URL (e.g., https://influxdb:8181)
# - INF_DATABASE: InfluxDB database name (e.g., eseries)
# - INF_TOKEN: InfluxDB authentication token
# - API: Comma-separated list of E-Series API endpoints (e.g., 10.0.0.1,10.0.0.2)  
# - USERNAME: E-Series management username (e.g., admin)
# - PASSWORD: E-Series management password
#
# Optional environment variables:
# - TLS_CA: Path to CA certificate file for TLS verification
# - TLS_VALIDATION: TLS validation mode (strict, normal, none) - default: strict
# - INTERVAL_TIME: Collection interval in seconds - default: 60
# - THREADS: Number of collection threads - default: 4
# - DRIVES_COLLECTION_INTERVAL: Drive data collection interval in seconds - default: 604800 (1 week)
# - CONTROLLER_COLLECTION_INTERVAL: Controller data collection interval in seconds - default: 3600 (1 hour)

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

exec python collector.py "$@"

