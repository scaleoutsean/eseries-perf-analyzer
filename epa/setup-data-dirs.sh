#!/bin/bash

# EPA Setup Script - Creates data directories with proper ownership
# InfluxDB: 1500:1500, Grafana: 472:472
#
# Repository: https://github.com/scaleoutSean/eseries-perf-analyzer
# License: MIT
# (c) 2025, scaleoutSean, https://github.com/scaleoutSean
# All rights reserved.

set -e

echo "Setting up EPA data directories..."

# Create data directories
echo "Creating data directories..."
mkdir -p data/influxdb data/grafana data/grafana-dashboards

# Set ownership for InfluxDB (user ID 1500)
echo "Setting InfluxDB ownership (1500:1500)..."
sudo chown -R 1500:1500 data/influxdb

# Set ownership for Grafana (user ID 472) 
echo "Setting Grafana ownership (472:472)..."
sudo chown -R 472:472 data/grafana data/grafana-dashboards

# Verify permissions
echo ""
echo "Verification:"
ls -la data/

echo ""
echo "Setup complete! You can now run:"
echo "  docker compose up -d"
echo ""
echo "Or start InfluxDB first:"
echo "  docker compose up -d influxdb"
echo "  sleep 10"
echo "  docker compose up -d"
