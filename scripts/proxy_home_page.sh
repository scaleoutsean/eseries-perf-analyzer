#!/usr/bin/env bash 

# 
# Reads .env variables and generates a simple home page with links to Grafana and InfluxDB Explorer using ./docs/nginx/index.html.tpl as a template.
#
set -euo pipefail
ENV_FILE=".env"
INPUT_FILE="docs/nginx/index.html.tpl"
OUTPUT_FILE="data/nginx/index.html"
# Load environment variables from .env file
if [[ -f "$ENV_FILE" ]]; then

    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo "Error: $ENV_FILE file not found!"
    exit 1
fi
# Check required variables
REQUIRED_VARS=("PROXY_HOST" "PROXY_GRAFANA_PORT" "PROXY_INFLUXDB_PORT" "PROXY_EXPLORER_PORT")
for VAR in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!VAR:-}" ]]; then
        echo "Error: $VAR is not set in $ENV_FILE"
        exit 1
    fi
done
# Generate the home page by replacing placeholders in the template
sed -e "s/{{ PROXY_HOST }}/${PROXY_HOST}/g" \
    -e "s/{{ PROXY_GRAFANA_PORT }}/${PROXY_GRAFANA_PORT}/g" \
    -e "s/{{ PROXY_INFLUXDB_PORT }}/${PROXY_INFLUXDB_PORT}/g" \
    -e "s/{{ PROXY_EXPLORER_PORT }}/${PROXY_EXPLORER_PORT}/g" \
    "$INPUT_FILE" > "$OUTPUT_FILE"
echo "Generated $OUTPUT_FILE with links to Grafana and InfluxDB Explorer."

