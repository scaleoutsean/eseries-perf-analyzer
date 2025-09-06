#!/bin/bash

###############################################################################
# Synopsis:                                                                   #
# Entrypoint script for utils container in E-Series Performance Analyzer      #
#   version 4                                                                 #
#                                                                             #
# Author: @scaleoutSean (Github)                                              #
# Repository: https://github.com/scaleoutsean/eseries-perf-analyzer           #
# License: MIT                                                                #
###############################################################################

CA_BUNDLE=${CA_BUNDLE:-/s3_certs/ca.crt}
echo "[DEBUG] Entrypoint starting."
echo "[DEBUG] AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID"
echo "[DEBUG] AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:0:4}... (redacted)"
echo "[DEBUG] S3_ENDPOINT=$S3_ENDPOINT"
echo "[DEBUG] CA_BUNDLE=$CA_BUNDLE"
echo "[DEBUG] BUCKET=$BUCKET"

mkdir -p "$CRED_DIR"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY

# Configure a profile so aws CLI will use the creds
aws configure set aws_access_key_id "$AWS_ACCESS_KEY_ID" --profile sfc || true
aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY" --profile sfc || true
aws configure set region us-east-1 --profile sfc || true

# Wait for S3 to respond (tries 12 times, 5s interval)
for i in $(seq 1 12); do
  aws --endpoint-url "$S3_ENDPOINT" --ca-bundle "$CA_BUNDLE" --profile sfc s3api list-buckets >wait_loop.log 2>&1
  if [ $? -eq 0 ]; then
    break
  fi
  echo "Waiting for S3 endpoint $S3_ENDPOINT (${i}/12)..."
  if [ $i -eq 1 ]; then
    echo "[DEBUG] Initial AWS CLI error:"
    cat wait_loop.log
  fi
  sleep 5
done
if ! aws --endpoint-url "$S3_ENDPOINT" --ca-bundle "$CA_BUNDLE" --profile sfc s3api list-buckets >/dev/null 2>&1; then
  echo "[ERROR] S3 endpoint $S3_ENDPOINT not available after wait loop. Last error:"
  cat wait_loop.log
  exit 1
fi
rm -f wait_loop.log

# Check bucket exists, create if missing
if ! aws --endpoint-url "$S3_ENDPOINT" --ca-bundle "$CA_BUNDLE" --profile sfc s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  echo "Creating bucket $BUCKET on $S3_ENDPOINT"
  aws --endpoint-url "$S3_ENDPOINT" --ca-bundle "$CA_BUNDLE" --profile sfc s3api create-bucket --bucket "$BUCKET" || {
    echo "Warning: create-bucket failed (might already exist or object ownership rules); continuing"
  }
else
  echo "Bucket $BUCKET already exists"
fi

# Persist credentials for other init steps
cat > "$CRED_DIR/credentials" <<EOF
AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
BUCKET=${BUCKET}
S3_ENDPOINT=${S3_ENDPOINT}
CA_BUNDLE=${CA_BUNDLE}
EOF

echo "Wrote $CRED_DIR/credentials"
echo "Bucket $BUCKET ready at $S3_ENDPOINT"

# Create InfluxDB environment setup script
mkdir -p /home/influxdb
cat > /home/influxdb/setup.sh << 'INFLUX_EOF'
#!/bin/bash
# InfluxDB3 Environment Setup Script
# Source this script to set up InfluxDB environment variables

export INFLUX_HOST="${INFLUX_HOST:-influxdb}"
export INFLUX_PORT="${INFLUX_PORT:-8181}"
export INFLUX_DB="${INFLUX_DB:-sfc}"
export INFLUXDB3_TLS_CA="${INFLUXDB3_TLS_CA:-/influxdb_certs/ca.crt}"

# Load auth token from file if available
if [ -n "$INFLUXDB3_AUTH_TOKEN_FILE" ] && [ -f "$INFLUXDB3_AUTH_TOKEN_FILE" ]; then
    export INFLUXDB3_AUTH_TOKEN=$(cat "$INFLUXDB3_AUTH_TOKEN_FILE" | sed 's/\x1b\[[0-9;]*m//g' | tr -d '\n')
    echo "Loaded InfluxDB auth token from $INFLUXDB3_AUTH_TOKEN_FILE"
fi

# Set up convenient aliases for InfluxDB CLI
alias influx='/home/influx/.influxdb/influx3'
alias influx-cli='/home/influx/.influxdb/influx3'

# Add InfluxDB CLI to PATH
export PATH="/home/influx/.influxdb:$PATH"

echo "InfluxDB Environment configured:"
echo "  INFLUX_HOST: $INFLUX_HOST"
echo "  INFLUX_PORT: $INFLUX_PORT"
echo "  INFLUX_DB: $INFLUX_DB"
echo "  INFLUXDB3_TLS_CA: $INFLUXDB3_TLS_CA"
echo "  Token file: $INFLUXDB3_AUTH_TOKEN_FILE"
echo ""
echo "Available commands:"
echo "  influx --help                   # InfluxDB CLI help"
echo "  curl \$INFLUX_URL/api/v3/...    # Direct API calls"
echo ""
echo "Example API calls:"
echo "  # List databases"
echo "  curl -k -H \"Authorization: Bearer \$INFLUXDB3_AUTH_TOKEN\" \\"
echo "    \"https://\$INFLUX_HOST:\$INFLUX_PORT/api/v3/configure/database?format=json\""
echo ""
echo "  # Write data"
echo "  curl -k -H \"Authorization: Bearer \$INFLUXDB3_AUTH_TOKEN\" \\"
echo "    -H \"Content-Type: text/plain\" \\"
echo "    -d \"test,host=utils value=1\" \\"
echo "    \"https://\$INFLUX_HOST:\$INFLUX_PORT/api/v3/write_lp?db=\$INFLUX_DB\""
INFLUX_EOF

chmod +x /home/influxdb/setup.sh

# Create a convenient shortcut script that sources the environment
cat > /usr/local/bin/influx-env << 'ENV_EOF'
#!/bin/bash
source /home/influxdb/setup.sh
ENV_EOF

chmod +x /usr/local/bin/influx-env

echo ""
echo "==============================================="
echo "InfluxDB environment setup available!"
echo "==============================================="
echo "To set up InfluxDB environment variables, run:"
echo "  source /home/influxdb/setup.sh"
echo "or:"
echo "  influx-env"
echo ""
echo "This will load InfluxDB environment variables and add the InfluxDB CLI to your PATH."
echo "==============================================="
echo ""

# Keep container running for debugging/cli use
tail -f /dev/null
