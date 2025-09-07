#!/usr/bin/bash
# Ensure correct ownership of data directories for current user

# if we're in scripts/, go up one directory
if [ "$(basename "$PWD")" == "scripts" ]; then
    cd ..
fi

# if we're not in the root directory and ./data directory does not exist, exit with error
if [ ! -f "docker-compose.yml" ] && [ ! -d "data" ]; then
    echo "Error: Please run this script from the root directory of the project"
    exit 1
fi

# if ./data/influxdb_tokens or ./data/influxdb_credentials exist, change ownership to current user

for dir in data/influxdb_tokens data/influxdb_credentials; do
    if [ -d "$dir" ]; then
        echo "Ensuring ownership of $dir to $(id -u):$(id -g)"
        sudo chown -R "$(id -u):$(id -g)" "$dir"
    else
        echo "Directory $dir does not exist, creating it and setting ownership to $(id -u):$(id -g)"
        mkdir -p "$dir"
        echo "Setting ownership of $dir to $(id -u):$(id -g)"
        sudo chown -R "$(id -u):$(id -g)" "$dir"
    fi
done
