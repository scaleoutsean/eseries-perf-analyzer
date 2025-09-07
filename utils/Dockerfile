FROM debian:trixie-slim
ENV HOME=/home/influx
ENV PATH="/home/influx/.influxdb:${PATH}"
ENV INFLUXDB3_BUILD_VERSION=${INFLUXDB3_BUILD_VERSION:-3.4.0}
LABEL maintainer="@scaleoutSean"

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
    sha256sum -c influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz.sha256 && \
    rm influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz.sha256 && \
    tar -xf influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz --strip-components=1 -C /home/influx/.influxdb && \
    rm influxdb3-core-${INFLUXDB3_BUILD_VERSION}_linux_amd64.tar.gz

# create influx system user and group, and fix permissions
RUN groupadd --system influx || true && \
    useradd --system --home-dir /home/influx --shell /bin/bash --create-home --gid influx influx || true && \
    chown -R influx:influx /home/influx
# set home environment to ensure Bash uses correct .bashrc
ENV HOME=/home/influx

# Copy CLI and API command examples for online reference
COPY README.md /home/influx/README.md

# copy entrypoint and set executable permissions as root
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Ensure any interactive bash shell loads InfluxDB env and alias
RUN echo "shopt -s expand_aliases" >> /etc/bash.bashrc && \
    echo "alias influx='influxdb3'" >> /etc/bash.bashrc && \
    echo "[ -f /home/influx/setup.sh ] && source /home/influx/setup.sh" >> /etc/bash.bashrc

# Switch to non-root and start entrypoint
USER influx
WORKDIR /home/influx
ENTRYPOINT ["/entrypoint.sh"]

