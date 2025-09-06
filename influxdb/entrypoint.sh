#!/bin/sh

###############################################################################
# Synopsis:                                                                   #
# Entrypoint script for InfluxDB 3 Core container in SolidFire Collector      #
#   version 2.1 and above.                                                    #
#                                                                             #
# Author: @scaleoutSean (Github)                                              #
# Repository: https://github.com/scaleoutsean/sfc                             #
# License: the Apache License Version 2.0                                     #
###############################################################################


# Entrypoint for influxdb3-core: loads S3 credentials if present, then execs influxdb3

echo "[DEBUG]    echo "SFC token already exists, attempting to delete and recreate..."
    DELETE_RESPONSE=$(echo "yes" | influxdb3 token delete --token-name "sfc" --host "$SERVER_URL" --token "$ADMIN_TOKEN" 2>&1)
    echo "Delete response: $DELETE_RESPONSE"DE_ID=$NODE_ID"

# Load credentials file if present
if [ -f "${S3_CREDENTIALS_FILE:-/influxdb_credentials/credentials}" ]; then
  set -a
  . "${S3_CREDENTIALS_FILE:-/influxdb_credentials/credentials}"
  set +a
fi

# Ensure NODE_ID is set (Compose wins if present)
if [ -z "$NODE_ID" ]; then
  NODE_ID="s169"
fi
export NODE_ID

echo "[DEBUG] NODE_ID=$NODE_ID"
echo "[DEBUG] Environment dump:"
env


curl -v --cacert /home/influxdb3/certs/ca.crt https://s3:7070/
# 
ls -l /home/influxdb3/certs/ca.crt
echo ""
echo ""
sleep 1

# Export TLS CA certificate path for InfluxDB
export INFLUXDB3_TLS_CA="${INFLUXDB3_TLS_CA:-/home/influxdb3/certs/ca.crt}"

# Also set common SSL environment variables that HTTP clients use
export SSL_CERT_FILE="${INFLUXDB3_TLS_CA}"
export CURL_CA_BUNDLE="${INFLUXDB3_TLS_CA}"
export REQUESTS_CA_BUNDLE="${INFLUXDB3_TLS_CA}"

echo "[DEBUG] SSL environment variables:"
echo "INFLUXDB3_TLS_CA=$INFLUXDB3_TLS_CA"
echo "SSL_CERT_FILE=$SSL_CERT_FILE"
echo "CURL_CA_BUNDLE=$CURL_CA_BUNDLE"

# Function to generate tokens after InfluxDB starts
generate_tokens() {
  echo "Waiting for InfluxDB to be ready for token generation..."
  sleep 5  # Give InfluxDB time to start
  
  # Set up token file path
  TOKEN_FILE="${TOKEN_FILE:-/influxdb_tokens/sfc.token}"
  
  # Create directory if it doesn't exist
  mkdir -p "$(dirname "$TOKEN_FILE")"
   

  # Set CLI to use HTTPS with the correct hostname that matches the certificate
  export INFLUXDB3_HOST_URL="https://influxdb:8181"
  
  # Don't try to list tokens initially - we don't have a valid token yet
  echo "Starting token generation process..."

  echo "Attempting to create admin token (works if none exists)..."
  # First try to create the admin token (works if none exists)
  ADMIN_TOKEN_OUTPUT=$(/home/influx/.influxdb/influxdb3 create token --admin --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" 2>&1)
  echo "Admin token creation attempt:"
  echo "$ADMIN_TOKEN_OUTPUT"
  
  # Extract the admin token from CLI output
  ADMIN_TOKEN=$(echo "$ADMIN_TOKEN_OUTPUT" | grep "^Token:" | cut -d' ' -f2)
  
  echo "DEBUG: ADMIN_TOKEN='$ADMIN_TOKEN'"
  echo "DEBUG: Checking for 'token name already exists' in output"
  echo "DEBUG: grep result:"
  echo "$ADMIN_TOKEN_OUTPUT" | grep "token name already exists" || echo "DEBUG: No match found"
  
  if [ -z "$ADMIN_TOKEN" ] && echo "$ADMIN_TOKEN_OUTPUT" | grep -q "token name already exists"; then
    echo "DEBUG: Condition matched - entering regenerate block"
    echo "Admin token already exists, using regenerate via recovery endpoint..."
    # Use regenerate to get the existing admin token
    ADMIN_TOKEN_OUTPUT=$(echo "yes" | /home/influx/.influxdb/influxdb3 create token --admin --regenerate --host "https://influxdb:8182" --tls-ca "${INFLUXDB3_TLS_CA}" 2>&1)
    echo "Admin token regeneration:"
    echo "$ADMIN_TOKEN_OUTPUT"
    # Extract token from regenerate output (different format)
    ADMIN_TOKEN=$(echo "$ADMIN_TOKEN_OUTPUT" | grep "^Token:" | cut -d' ' -f2)
    # If that doesn't work, try alternative extraction methods
    if [ -z "$ADMIN_TOKEN" ]; then
      # Try extracting from the HTTP header line
      ADMIN_TOKEN=$(echo "$ADMIN_TOKEN_OUTPUT" | grep "Authorization: Bearer" | sed 's/.*Authorization: Bearer //')
    fi
    echo "DEBUG: Extracted ADMIN_TOKEN from regenerate: '$ADMIN_TOKEN'"
  fi
  
  if [ -n "$ADMIN_TOKEN" ]; then
    # Show first 20 characters of token for verification (sh-compatible)
    ADMIN_TOKEN_PREFIX=$(echo "$ADMIN_TOKEN" | cut -c1-20)
    echo "Admin token obtained successfully: ${ADMIN_TOKEN_PREFIX}..."
    echo "Now creating named SFC token..."
    
    # Check if token file already exists and is valid
    if [ -f "$TOKEN_FILE" ] && [ -s "$TOKEN_FILE" ]; then
      echo "SFC token file exists, testing if it's still valid..."
      EXISTING_TOKEN=$(cat "$TOKEN_FILE" | sed 's/\x1b\[[0-9;]*m//g')
      
      # Test the existing token
      echo "DEBUG: Testing token with simple connection test..."
      echo "DEBUG: Token preview: $(echo "$EXISTING_TOKEN" | cut -c1-20)..."
      TOKEN_TEST=$(/home/influx/.influxdb/influxdb3 query "SELECT 1" --database "sfc" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$EXISTING_TOKEN" 2>&1 || true)
      echo "DEBUG: Token test result: $TOKEN_TEST"
      
      if echo "$TOKEN_TEST" | grep -q "1\|success" && ! echo "$TOKEN_TEST" | grep -q "error\|invalid\|cannot authenticate"; then
        echo "Existing SFC token is valid, preserving it to avoid breaking active collectors..."
        echo "Token file: $TOKEN_FILE (preserved)"
        # Skip token creation/recreation completely
      else
        echo "Existing SFC token is invalid, will create new one..."
        CREATE_NEW_TOKEN=true
      fi
    else
      echo "No existing SFC token file found, will create new one..."
      CREATE_NEW_TOKEN=true
    fi
    
    # Only create/recreate token if needed
    if [ "$CREATE_NEW_TOKEN" = "true" ]; then
      # First try to create the token
      TOKEN_RESPONSE=$(/home/influx/.influxdb/influxdb3 create token --admin --name "sfc" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
      echo "SFC token creation response: $TOKEN_RESPONSE"
      
      # If creation failed because token exists, try to delete and recreate
      if echo "$TOKEN_RESPONSE" | grep -q "token name already exists"; then
        echo "SFC token already exists in InfluxDB, attempting to delete and recreate..."
        DELETE_RESPONSE=$(echo "yes" | /home/influx/.influxdb/influxdb3 delete token --token-name "sfc" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
        echo "Delete response: $DELETE_RESPONSE"
        
        # Try creating again
        TOKEN_RESPONSE=$(/home/influx/.influxdb/influxdb3 create token --admin --name "sfc" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
        echo "SFC token recreation response: $TOKEN_RESPONSE"
      fi
      
      # Extract and save the new token (extract only the actual token part)
      SFC_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o "apiv3_[A-Za-z0-9_-]*" | head -1)
      if [ -n "$SFC_TOKEN" ]; then
        echo -n "$SFC_TOKEN" > "$TOKEN_FILE"
        echo "New SFC token saved to $TOKEN_FILE (without newline)"
      else
        echo "Failed to extract token from response:"
        echo "$TOKEN_RESPONSE"
        echo "dummy-token-extraction-failed" > "$TOKEN_FILE"
      fi
    fi
  else
    echo "Failed to obtain admin token"
    echo "DEBUG: ADMIN_TOKEN_OUTPUT was:"
    echo "$ADMIN_TOKEN_OUTPUT"
    echo "Writing dummy token as fallback"
    echo "dummy-token-failed" > "$TOKEN_FILE"
  fi
  
  # Create the 'sfc' database using the admin token (if we have one)
  if [ -n "$ADMIN_TOKEN" ]; then
    echo "Creating 'sfc' database..."
    CREATE_DB_RESPONSE=$(/home/influx/.influxdb/influxdb3 create database "sfc" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
    echo "Database creation response: $CREATE_DB_RESPONSE"
    
    if echo "$CREATE_DB_RESPONSE" | grep -q "successfully created" || echo "$CREATE_DB_RESPONSE" | grep -q "already exists"; then
      echo "Database 'sfc' is ready"
    else
      echo "Warning: Database creation may have failed - check response above"
    fi
    
    # Also save the admin token for reference
    if [ -f /tmp/admin_token.json ] && grep -q '"token"' /tmp/admin_token.json; then
      echo "Admin token also available in /tmp/admin_token.json"
    fi
  else
    echo "Skipping database creation - no admin token available"
  fi
  
  echo "Updated token list:"
  /home/influx/.influxdb/influxdb3 show tokens
  
  echo "Token generation completed"
  
  # Setup downsampling triggers based on configuration
  echo "Setting up intelligent downsampling triggers..."
  setup_downsampling_triggers
}

setup_downsampling_triggers() {
  # Wait for InfluxDB to be fully ready
  echo "Waiting for InfluxDB to be ready for trigger setup..."
  sleep 10
  
  echo "Setting up intelligent downsampling triggers..."
  
  # Create SFC-optimized volume performance trigger (example for volume_performance)
  echo "Creating DS triggers for volume_performance: 14d->5m, 30d->1h, 60d->1d..."
  /home/influx/.influxdb/influxdb3 create trigger \
    "sfc_volume_5m_auto" \
    --database "sfc" \
    --plugin-filename "sfc_intelligent_downsampler.py" \
    --trigger-spec "cron:0 */10 * * * *" \
    --trigger-arguments "source_measurement=volume_performance,target_measurement=volume_performance_5m_auto,window_period=5m,older_than=14d" \
    --host "https://influxdb:8181" \
    --tls-ca "${INFLUXDB3_TLS_CA}" \
    --token "$ADMIN_TOKEN" 2>&1 | tee /tmp/trigger_setup.log
  /home/influx/.influxdb/influxdb3 create trigger \
    "sfc_volume_1h_auto" \
    --database "sfc" \
    --plugin-filename "sfc_intelligent_downsampler.py" \
    --trigger-spec "cron:0 0 * * * *" \
    --trigger-arguments "source_measurement=volume_performance_5m_auto,target_measurement=volume_performance_1h_auto,window_period=1h,older_than=30d" \
    --host "https://influxdb:8181" \
    --tls-ca "${INFLUXDB3_TLS_CA}" \
    --token "$ADMIN_TOKEN" 2>&1 | tee -a /tmp/trigger_setup.log
  /home/influx/.influxdb/influxdb3 create trigger \
    "sfc_volume_1d_auto" \
    --database "sfc" \
    --plugin-filename "sfc_intelligent_downsampler.py" \
    --trigger-spec "cron:0 0 2 * * *" \
    --trigger-arguments "source_measurement=volume_performance_1h_auto,target_measurement=volume_performance_1d_auto,window_period=1d,older_than=60d" \
    --host "https://influxdb:8181" \
    --tls-ca "${INFLUXDB3_TLS_CA}" \
    --token "$ADMIN_TOKEN" 2>&1 | tee -a /tmp/trigger_setup.log

  echo "Downsampling trigger setup completed"
}

setup_default_trigger() {
  echo "Default trigger setup disabled - using intelligent downsampling triggers instead"
  # Note: This function is kept for backward compatibility but no longer creates triggers
  # The intelligent downsampling setup handles all trigger creation via setup_downsampling_triggers()
}

# Start token generation in the background
generate_tokens &

# Start influxdb3 with local file storage instead of S3 to avoid write performance issues
exec /home/influx/.influxdb/influxdb3 serve \
  --node-id="$NODE_ID" \
  --object-store="file" \
  --data-dir="/var/lib/influxdb3" \
  --tls-key="${TLS_KEY}" \
  --tls-cert="${TLS_CERT}" \
  --tls-minimum-version="${TLS_MIN_VERSION:-tls-1.3}" \
  --http-bind="${HTTP_BIND:-0.0.0.0:8181}" \
  --wal-flush-interval="${WAL_FLUSH_INTERVAL:-30s}" \
  --admin-token-recovery-http-bind="0.0.0.0:8182" \
  --plugin-dir="/tmp/plugins"


