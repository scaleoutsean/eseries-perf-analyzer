utils: helper image (curl, wget, vim); runs as user 'appuser'.

Interactive shell: 
docker run --rm -it --entrypoint /bin/sh ntap-grafana/utils:latest

Persistent test container: 
docker run -d --name influxdb-utils-test --entrypoint tail ntap-grafana/utils:latest -f /dev/null

Entrypoint exports INFLUX_HOST/INFLUX_PORT if influxdb.conf exists.

Run as root inside container: 
docker exec -u 0 -it <container> /bin/sh

# list databases (InfluxDB v1 CLI)
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'SHOW DATABASES'

# create database (can help you avoid running dbmanager container) - change DB name in command!
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'CREATE DATABASE me-series'

# list measurements for a database (InfluxDB v1 CLI)
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "${DB:-mydb}" -execute 'SHOW MEASUREMENTS'

# same via HTTP API (curl)
curl "http://${INFLUX_HOST:-influxdb}:${INFLUX_PORT:-8086}/query?db=${DB:-mydb}&q=SHOW