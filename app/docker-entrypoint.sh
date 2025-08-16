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

