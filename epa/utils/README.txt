utils container is a helper image (with curl, wget, vim); runs as user 'appuser'.

Entrypoint exports INFLUX_HOST/INFLUX_PORT if influxdb.conf (used by influxdb container) exists.

Start interactive shell in container on demand if not started with Docker Compose: 
docker run --rm -it --entrypoint /bin/sh ntap-grafana/utils:latest

Run as root inside the utils container: 
docker exec -u 0 -it utils /bin/sh

Run persistent test container on demand: 
docker run -d --name influxdb-utils-test --entrypoint tail ntap-grafana/utils:latest -f /dev/null

# list databases (InfluxDB v1 CLI)
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'SHOW DATABASES'

# create database (this helps avoid running dbmanager container) - change the DB name in command and no dashes in DB names!
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'CREATE DATABASE eseries'

# drop / DELETE database 
# influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'CREATE DATABASE N-A-M-E'

# list measurements for a database (InfluxDB v1 CLI) - change DB name to whatever DB name you have in collector container(s)
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "${DB:-eseries}" -execute 'SHOW MEASUREMENTS'

# same via HTTP API (curl) - change DB name to your DB name
curl "http://${INFLUX_HOST:-influxdb}:${INFLUX_PORT:-8086}/query?db=${DB:-eseries}&q=SHOW%20MEASUREMENTS"

### Sample queries

# Check SSD endurance data 
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "eseries" -execute 'SELECT sys_name, sys_tray, sys_tray_slot, spareBlocksRemainingPercent FROM disks ORDER BY time DESC LIMIT 2'

# See what actual values are being stored
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "eseries" -execute 'SELECT spareBlocksRemainingPercent FROM disks LIMIT 2'

# Check the interface measurement
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "eseries" -execute 'SELECT * FROM interface LIMIT 3'

