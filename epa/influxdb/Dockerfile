ARG CONTAINER_INFLUXDB_TAG=latest
FROM influxdb:${CONTAINER_INFLUXDB_TAG}

ADD influxdb.conf /etc/influxdb

EXPOSE 8086

CMD ["influxd", "-config", "/etc/influxdb/influxdb.conf"]
