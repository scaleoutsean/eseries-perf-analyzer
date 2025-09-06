ARG INFLUXDB3_EXPLORER_VERSION
FROM influxdata/influxdb3-ui:${INFLUXDB3_EXPLORER_VERSION}

# Copy CA certificate and add to system trust store (try both Alpine and Ubuntu approaches)
COPY ./certs/_master/ca.crt /usr/local/share/ca-certificates/sfc-ca.crt

RUN (update-ca-certificates || true) && \
    (apk update && apk add ca-certificates && update-ca-certificates || true) && \
    # Ensure CA is in both common locations
    mkdir -p /etc/ssl/certs && \
    cp /usr/local/share/ca-certificates/sfc-ca.crt /etc/ssl/certs/sfc-ca.crt && \
    # For Node.js apps - set NODE_EXTRA_CA_CERTS environment variable
    echo "export NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/sfc-ca.crt" >> /etc/profile

ENV NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/sfc-ca.crt

# The rest uses the original entrypoint
