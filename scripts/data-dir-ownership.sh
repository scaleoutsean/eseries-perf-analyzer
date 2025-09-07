#!/usr/bin/bash
#

# if we're in scripts/, go up one directory
if [ "$(basename "$PWD")" == "scripts" ]; then
    cd ..
fi
# if we're not in the root directory, exit with error
if [ ! -f "docker-compose.yml" ]; then
    echo "Error: Please run this script from the root directory of the project"
    exit 1
fi

# if ./data/influxdb_tokens or ./data/influxdb_credentials exist, change ownership to current user
if [ -d ../data/influxdb_tokens ]; then
    echo "Changing ownership of ../data/influxdb_tokens to $(id -u):$(id -g)"
    sudo -E chown -R $(id -u):$(id -g) ../data/influxdb_tokens
else
    echo "Directory ../data/influxdb_tokens does not exist; creating it"
    mkdir -p ../data/influxdb_tokens
fi

if [ -d ../data/influxdb_credentials ]; then
    echo "Changing ownership of ../data/influxdb_credentials to $(id -u):$(id -g)"
    sudo -E chown -R $(id -u):$(id -g) ../data/influxdb_credentials
else
    echo "Directory ../data/influxdb_credentials does not exist; creating it"
    mkdir -p ../data/influxdb_credentials
fi
