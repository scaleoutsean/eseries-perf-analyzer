#!/bin/bash

# EPA Setup Script - Creates data directories with proper ownership
# Grafana: 472:472
#
# Repository: https://github.com/scaleoutSean/eseries-perf-analyzer
# License: MIT
# (c) 2025, scaleoutSean, https://github.com/scaleoutSean
# All rights reserved.

set -e

echo "Setting up EPA data directories..."

# Create data directories
echo "Creating data directories..."
mkdir -p data/vm data/grafana data/grafana-dashboards certs/grafana

# Set ownership for Grafana (user ID 472) 
echo "Setting Grafana ownership (472:472)..."
sudo chown -R 472:472 data/grafana data/grafana-dashboards certs/grafana

# Verify permissions
echo ""
echo "Verification:"
ls -la data/

echo ""
echo "Directory creation complete! See README.md for other instructions." 
echo ""

