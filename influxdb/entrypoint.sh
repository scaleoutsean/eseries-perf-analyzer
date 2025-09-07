#!/bin/sh

###############################################################################
# Synopsis:                                                                   #
# Entrypoint script for InfluxDB container in E-Series Performance Analyzer   #
#   version 4.0 and above.                                                    #
#                                                                             #
# Author: @scaleoutSean (Github)                                              #
# Repository: https://github.com/scaleoutsean/eseries-perf-analyzer           #
# License: the Apache License Version 2.0                                     #
###############################################################################

# Function to generate admin token after InfluxDB starts

generate_tokens() {
  echo "Waiting for InfluxDB to be ready for token generation..."
  sleep 5  # Give InfluxDB time to start
  
  # Set up token file path
  TOKEN_FILE="${TOKEN_FILE:-/home/influx/tokens/epa.token}"
  
  # Create directory if it doesn't exist
  mkdir -p "$(dirname "$TOKEN_FILE")"   
  
  # Check if we can write to the token directory
  if [ ! -w "$(dirname "$TOKEN_FILE")" ]; then
    echo "ERROR: Cannot write to token directory $(dirname "$TOKEN_FILE")"
    echo "Please ensure the directory exists and has proper permissions"
    echo "You may need to run: sudo chown -R $(id -u):$(id -g) $(dirname "$TOKEN_FILE")"
    return 1
  fi

  # Set CLI to use HTTPS with the correct hostname that matches the certificate
  export INFLUXDB3_HOST_URL="https://influxdb:8181"
  
  # Check if token file exists and is valid
  if [ -f "$TOKEN_FILE" ] && [ -s "$TOKEN_FILE" ]; then
    echo "EPA token file exists, testing if it's still valid..."
    EXISTING_TOKEN=$(cat "$TOKEN_FILE" | sed 's/\x1b\[[0-9;]*m//g')
    
    # Test the existing token with a simple command
    TOKEN_TEST=$(/home/influx/.influxdb/influxdb3 show databases --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$EXISTING_TOKEN" 2>&1 || true)
    
    if echo "$TOKEN_TEST" | grep -q "error\|invalid\|cannot authenticate\|401"; then
      echo "Existing EPA token is invalid, will create new one..."
      CREATE_NEW_TOKEN=true
    else
      echo "Existing EPA token is valid, no need to recreate."
      CREATE_NEW_TOKEN=false
    fi
  else
    echo "No existing EPA token file found, will create new one..."
    CREATE_NEW_TOKEN=true
  fi
  
  if [ "$CREATE_NEW_TOKEN" = "true" ]; then
    echo "Attempting to create admin token..."
    # Try to create the admin token
    ADMIN_TOKEN_OUTPUT=$(/home/influx/.influxdb/influxdb3 create token --admin --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" 2>&1)
    echo "Admin token creation attempt:"
    echo "$ADMIN_TOKEN_OUTPUT"
    
    # Write raw output to file for debugging
    # echo "$ADMIN_TOKEN_OUTPUT" > "${TOKEN_FILE}.raw"
    
    # Extract the admin token from CLI output (strip ANSI codes first)
    ADMIN_TOKEN=$(echo "$ADMIN_TOKEN_OUTPUT" | sed 's/\x1b\[[0-9;]*m//g' | sed -n '/^Token:/s/^Token: //p')
    
    if [ -z "$ADMIN_TOKEN" ]; then
      echo "Failed to extract admin token from output."
      echo "Writing dummy token as fallback"
      echo "dummy-token-failed" > "$TOKEN_FILE"
      chmod 640 "$TOKEN_FILE"
      return
    fi
    
    echo "Admin token obtained successfully."
    
    # Save admin token for future administrative operations
    echo -n "$ADMIN_TOKEN" > "${TOKEN_FILE}.admin"
    chmod 640 "${TOKEN_FILE}.admin"
    
    # Now create the EPA token using the admin token
    echo "Creating EPA token..."
    TOKEN_RESPONSE=$(/home/influx/.influxdb/influxdb3 create token --admin --name "epa" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
    echo "EPA token creation response: $TOKEN_RESPONSE"
    
    # Extract the EPA token
    EPA_TOKEN=$(echo "$TOKEN_RESPONSE" | grep -o "apiv3_[A-Za-z0-9_-]*" | head -1)
    
    if [ -n "$EPA_TOKEN" ]; then
      echo -n "$EPA_TOKEN" > "$TOKEN_FILE"
      chmod 640 "$TOKEN_FILE"
      echo "New EPA token saved to $TOKEN_FILE"
    else
      echo "Failed to extract EPA token from response:"
      echo "$TOKEN_RESPONSE"
      echo "dummy-token-extraction-failed" > "$TOKEN_FILE"
      chmod 640 "$TOKEN_FILE"
    fi
  fi
  
  # Create the 'epa' database using the admin token (if we have one)
  if [ -n "$ADMIN_TOKEN" ]; then
    echo "Creating 'epa' database..."
    CREATE_DB_RESPONSE=$(/home/influx/.influxdb/influxdb3 create database "epa" --host "https://influxdb:8181" --tls-ca "${INFLUXDB3_TLS_CA}" --token "$ADMIN_TOKEN" 2>&1)
    echo "Database creation response: $CREATE_DB_RESPONSE"
    
    if echo "$CREATE_DB_RESPONSE" | grep -q "created successfully\|already exists"; then
      echo "Database 'epa' is ready"
    else
      echo "Warning: Database creation may have failed - check response above"
    fi
  else
    echo "Skipping database creation - admin token only available during new token creation"
  fi
  
  echo "Token generation completed"
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


