utils container is a helper image (with curl, wget, vim); runs as user 'appuser'.

Entrypoint exports INFLUX_HOST/INFLUX_PORT if influxdb.conf (used by influxdb container) exists.

Start interactive shell in container on demand if not started with Docker Compose: 
docker run --rm -it --entrypoint /bin/sh ntap-grafana/utils:latest

Run as root inside container: 
docker exec -u 0 -it <container> /bin/sh

Run persistent test container on demand: 
docker run -d --name influxdb-utils-test --entrypoint tail ntap-grafana/utils:latest -f /dev/null

# list databases (InfluxDB v1 CLI)
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'SHOW DATABASES'

# create database (this helps avoid running dbmanager container) - change the DB name in command and no dashes in DB names!
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'CREATE DATABASE me_series'

# list measurements for a database (InfluxDB v1 CLI) - change DB name to whatever DB name you have in collector container(s)
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "${DB:-eseries}" -execute 'SHOW MEASUREMENTS'

# same via HTTP API (curl)
curl "http://${INFLUX_HOST:-influxdb}:${INFLUX_PORT:-8086}/query?db=${DB:-mydb}&q=SHOW

