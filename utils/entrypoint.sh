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

CA_BUNDLE=${CA_BUNDLE:-/home/influx/ca.crt}
echo "[DEBUG] Entrypoint starting."
echo "[DEBUG] AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID"
echo "[DEBUG] AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:0:4}... (redacted)"
echo "[DEBUG] S3_ENDPOINT=$S3_ENDPOINT"
echo "[DEBUG] CA_BUNDLE=$CA_BUNDLE"
echo "[DEBUG] BUCKET=$BUCKET"

mkdir -p "$CRED_DIR"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY

# Configure a profile so aws CLI will use the creds
aws configure set aws_access_key_id "$AWS_ACCESS_KEY_ID" --profile epa || true
aws configure set aws_secret_access_key "$AWS_SECRET_ACCESS_KEY" --profile epa || true
aws configure set region us-east-1 --profile epa || true

# Wait for S3 to respond (tries 12 times, 5s interval)
for i in $(seq 1 12); do
  aws --endpoint-url "$S3_ENDPOINT" --ca-bundle "$CA_BUNDLE" --profile epa s3api list-buckets >wait_loop.log 2>&1
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
if ! aws --endpoint-url "$S3_ENDPOINT" --ca-bundle "$CA_BUNDLE" --profile epa s3api list-buckets >/dev/null 2>&1; then
  echo "[ERROR] S3 endpoint $S3_ENDPOINT not available after wait loop. Last error:"
  cat wait_loop.log
  exit 1
fi
rm -f wait_loop.log

# Check bucket exists, create if missing
if ! aws --endpoint-url "$S3_ENDPOINT" --ca-bundle "$CA_BUNDLE" --profile epa s3api head-bucket --bucket "$BUCKET" >/dev/null 2>&1; then
  echo "Creating bucket $BUCKET on $S3_ENDPOINT"
  aws --endpoint-url "$S3_ENDPOINT" --ca-bundle "$CA_BUNDLE" --profile epa s3api create-bucket --bucket "$BUCKET" || {
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
mkdir -p /home/influx
cat > /home/influx/setup.sh << 'INFLUX_EOF'
#!/bin/bash
# InfluxDB3 Environment Setup Script
# Source this script to set up InfluxDB environment variables

shopt -s expand_aliases
export INFLUXDB3_HOST_URL="${INFLUX_HOST:-https://influxdb:8181}"
export INFLUX_DB="${INFLUX_DB:-epa}"
export INFLUXDB3_TLS_CA="${INFLUXDB3_TLS_CA:-/home/influxdb/ca.crt}"

# Load auth token from file if available
if [ -n "$INFLUXDB3_AUTH_TOKEN_FILE" ] && [ -f "$INFLUXDB3_AUTH_TOKEN_FILE" ]; then
    export INFLUXDB3_AUTH_TOKEN=$(cat "$INFLUXDB3_AUTH_TOKEN_FILE" | sed 's/\x1b\[[0-9;]*m//g' | tr -d '\n')
    echo "Loaded InfluxDB auth token from $INFLUXDB3_AUTH_TOKEN_FILE"
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
alias influx-cli='/home/influx/.influxdb/influxdb3'
EOF

# Keep container running for debugging/cli use
tail -f /dev/null

