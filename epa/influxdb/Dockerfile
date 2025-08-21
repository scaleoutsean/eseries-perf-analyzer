ARG CONTAINER_INFLUXDB_TAG=1.11.8-alpine
ARG TAG=latest
ARG PROJ_NAME=ntap-grafana
FROM ${PROJ_NAME}/alpine-base:${TAG} AS builder
LABEL autodelete="true"

FROM influxdb:${CONTAINER_INFLUXDB_TAG}
ADD influxdb.conf /etc/influxdb
COPY --from=builder /etc/apk/repositories /etc/apk/repositories

EXPOSE 8086

CMD ["influxd", "-config", "/etc/influxdb/influxdb.conf"]
