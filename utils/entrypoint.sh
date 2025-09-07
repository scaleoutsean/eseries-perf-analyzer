#!/bin/bash

###############################################################################
# Synopsis:                                                                   #
# Entrypoint script for utils container in E-Series Performance Analyzer      #
#   version 4.0 and above.                                                    #
#                                                                             #
# Author: @scaleoutSean (Github)                                              #
# Repository: https://github.com/scaleoutsean/eseries-perf-analyzer           #
# License: the Apache License Version 2.0                                     #
###############################################################################


# Create InfluxDB environment setup script
mkdir -p /home/influx
cat > /home/influx/setup.sh << 'INFLUX_EOF'
#!/bin/bash
# InfluxDB3 Environment Setup Script
# Source this script to set up InfluxDB environment variables

shopt -s expand_aliases
export INFLUXDB3_HOST_URL="https://${INFLUX_HOST:-influxdb}:${INFLUX_PORT:-8181}"
export INFLUX_DB="${INFLUX_DB:-epa}"
export INFLUXDB3_TLS_CA="${INFLUXDB3_TLS_CA:-/home/influx/certs/ca.crt}"

# Load auth token from file if available
if [ -n "$INFLUXDB3_AUTH_TOKEN_FILE" ] && [ -f "$INFLUXDB3_AUTH_TOKEN_FILE" ]; then
    export INFLUXDB3_AUTH_TOKEN=$(cat "$INFLUXDB3_AUTH_TOKEN_FILE" | sed 's/\x1b\[[0-9;]*m//g' | tr -d '\n')
    # cat "$INFLUXDB3_AUTH_TOKEN_FILE"
    echo "Loaded InfluxDB auth token from $INFLUXDB3_AUTH_TOKEN_FILE"
    echo "Token: $INFLUXDB3_AUTH_TOKEN"
fi

# Set up convenient aliases for InfluxDB CLI
alias influx='/home/influx/.influxdb/influxdb3'
alias influx-cli='/home/influx/.influxdb/influxdb3'

# Add InfluxDB CLI to PATH
export PATH="/home/influx/.influxdb:$PATH"

echo "InfluxDB Environment configured:"
echo "  INFLUXDB3_HOST_URL: $INFLUXDB3_HOST_URL"
echo "  INFLUX_DB: $INFLUX_DB"
echo "  INFLUXDB3_TLS_CA: $INFLUXDB3_TLS_CA"
echo "  Token file: $INFLUXDB3_AUTH_TOKEN_FILE"
echo ""
echo "Available commands:"
echo "  influx --help                   # InfluxDB CLI help"
echo "  curl \$INFLUXDB3_HOST_URL/api/v3/...   # Direct API calls"
echo ""
echo "Example API calls:"
echo "  # List databases"
echo "  curl -k -H \"Authorization: Bearer \$INFLUXDB3_AUTH_TOKEN\" \\"
echo "    \"$INFLUXDB3_HOST_URL/api/v3/configure/database?format=json\""
echo ""
echo "  # Write data"
echo "  curl -k -H \"Authorization: Bearer \$INFLUXDB3_AUTH_TOKEN\" \\"
echo "    -H \"Content-Type: text/plain\" \\"
echo "    -d \"test,host=utils value=1\" \\"
echo "    \"$INFLUXDB3_HOST_URL/api/v3/write_lp?db=\$INFLUX_DB\""
INFLUX_EOF

chmod +x /home/influx/setup.sh
# Append aliases and auto-source setup.sh in .bashrc for interactive shells
cat >> /home/influx/.bashrc << 'EOF'
# Load InfluxDB environment on shell startup
[ -f /home/influx/setup.sh ] && source /home/influx/setup.sh
alias influx='/home/influx/.influxdb/influxdb3'
alias influx-cli='/home/influx/.influxdb/influxdb3 --tls-ca ./certs/ca.crt'
EOF

# Keep container running for debugging/cli use
tail -f /dev/null

