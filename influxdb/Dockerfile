FROM debian:bookworm-slim
LABEL maintainer="@scaleoutSean"

# Set default InfluxDB3 version (can be overridden at build time)
ARG INFLUXDB3_BUILD_VERSION=3.4.0
ENV INFLUXDB3_BUILD_VERSION=${INFLUXDB3_BUILD_VERSION}

# Install dependencies for InfluxDB3 and plugin processing
RUN apt-get update && \
    apt-get install -y wget ca-certificates curl tar netcat-openbsd python3 python3-yaml && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy CA cert to container
# COPY certs/_master/ca.crt /home/influx/certs/ca.crt
# RUN chmod 774 /home/influx/certs/ca.crt
RUN mkdir -p /home/influx/certs /home/influx/tokens/
# Create influx user and home directory
RUN useradd -m -d /home/influx -s /bin/bash influx

# Set working directory
WORKDIR /home/influx

# =====================================================
# InfluxDB3 Core Installation
# =====================================================
RUN mkdir -p /home/influx/.influxdb && \
    cd /home/influx/.influxdb && \
    echo "Downloading InfluxDB3 Core ${INFLUXDB3_BUILD_VERSION}..." && \
    curl -sSL "https://dl.influxdata.com/influxdb/releases/influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz" -O && \
    curl -sSL "https://dl.influxdata.com/influxdb/releases/influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz.sha256" -O && \
    sha256sum -c "influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz.sha256" && \
    tar -xf "influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz" --strip-components=1 -C /home/influx/.influxdb && \
    ls -l /home/influx/.influxdb && \
    rm "influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz"* && \
    echo "InfluxDB3 Core installed successfully"

# Add InfluxDB to PATH for all users
ENV PATH="$PATH:/home/influx/.influxdb"

# =====================================================
# Embedded Plugin Architecture - "Stored Procedures"  
# =====================================================
# Use InfluxDB's bundled Python to create plugin virtual environment
# This makes plugins available as stored procedures within InfluxDB

RUN mkdir -p /tmp/plugins/official /tmp/plugins/sfc && \
    cd /tmp/plugins && \
    echo "Setting up Python virtual environment using InfluxDB's bundled Python..." && \
    /home/influx/.influxdb/python/bin/python3 -m venv .venv && \
    echo "Installing Python dependencies for plugins..." && \
    /tmp/plugins/.venv/bin/pip install requests toml schedule numpy pandas && \
    cd /tmp/plugins/official && \
    echo "Downloading official InfluxDB3 plugins..." && \
    curl -sSL "https://raw.githubusercontent.com/influxdata/influxdb3_plugins/main/influxdata/downsampler/downsampler.py" -o downsampler.py 2>/dev/null || \
    curl -sSL "https://raw.githubusercontent.com/influxdata/downsampler/main/downsampler.py" -o downsampler.py 2>/dev/null || \
    echo "WARNING: Could not download official downsampler plugin" && \
    echo "Official plugins download attempt completed"

# Display embedded plugin summary
RUN echo "=== EPA InfluxDB3 Embedded Plugin Summary ===" && \
    echo "Plugin directory: /tmp/plugins" && \
    ls -la /tmp/plugins/ && \
    echo "Official plugins:" && \
    ls -la /tmp/plugins/official/ 2>/dev/null || echo "Official plugins directory not found" && \
    echo "EPA plugins:" && \
    ls -la /tmp/plugins/sfc/ 2>/dev/null || echo "EPA plugins directory not found" && \
    echo "Embedded plugin architecture ready"

# Copy downsampling configuration
COPY influxdb/downsampling-config.yaml /tmp/plugins/downsampling-config.yaml

COPY influxdb/entrypoint.sh /home/influx/entrypoint.sh
RUN chmod +x /home/influx/entrypoint.sh

USER influx

EXPOSE 8181
