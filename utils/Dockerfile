FROM debian:trixie-slim
LABEL maintainer="@scaleoutSean"

# Set default InfluxDB3 version (can be overridden at build time)
ARG INFLUXDB3_BUILD_VERSION=3.4.0
ENV INFLUXDB3_BUILD_VERSION=${INFLUXDB3_BUILD_VERSION}

# Add InfluxDB to PATH for all users
ENV PATH="$PATH:/home/influx/.influxdb"

# Install python and awscli
RUN apt-get update && \
    apt-get install -y curl python3 python3-pip ca-certificates wget && \
    rm -rf /usr/lib/python3.13/EXTERNALLY-MANAGED && \
    pip3 install --no-cache-dir awscli && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/influx/.influxdb && \
    cd /home/influx/.influxdb && \
    curl -sSL "https://dl.influxdata.com/influxdb/releases/influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz" -O && \
    curl -sSL "https://dl.influxdata.com/influxdb/releases/influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz.sha256" -O && \
    sha256sum -c "influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz.sha256" && \
    rm influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz.sha256 && \
    tar -xf influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz --strip-components=1 -C /home/influx/.influxdb && \
    rm influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
