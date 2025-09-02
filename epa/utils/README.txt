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
# influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'DROP DATABASE D-B-N-A-M-E'

# list measurements for a database (InfluxDB v1 CLI) - change DB name to whatever DB name you have in collector container(s)
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "${DB:-eseries}" -execute 'SHOW MEASUREMENTS'

# same via HTTP API (curl) - change DB name to your DB name
curl "http://${INFLUX_HOST:-influxdb}:${INFLUX_PORT:-8086}/query?db=${DB:-eseries}&q=SHOW%20MEASUREMENTS"

# drop table (measurement)
# influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'DROP MEASUREMENT my-measurement'

### Sample queries

# Check SSD endurance data 
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "eseries" -execute 'SELECT sys_name, sys_tray, sys_tray_slot, spareBlocksRemainingPercent FROM disks ORDER BY time DESC LIMIT 2'

# See what actual values are being stored
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "eseries" -execute 'SELECT spareBlocksRemainingPercent FROM disks LIMIT 2'

# Check the interface measurement
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -database "eseries" -execute 'SELECT * FROM interface LIMIT 3'

## Backup and restore examples (needs manual Docker volume addition for target/source directory) 

# Full backup
# Note that host and port are provided together, and the port number is 8088, not 8086
docker exec utils influxd backup -portable -host influxdb:8088 /dump/

# Copy backup out of utils container (although the best approach is to mount ./dump:/dump in the utils container before backup, and eliminate this step) 
docker cp utils:/dump ./dump/

# Specific database backup (when you have eseries data mounted in influxdb, e.g. ./dump:/dump)
docker exec utils influxd backup -portable -host influxdb:8088 -database eseries /dump/

# Restore by starting utils (or influxdb) container with ./dump:/dump volume mounted:
# Inside of a container, make sure the DB does not exist and then restore it
influxd restore -host influxdb:8088 -db eseries -portable /dump/
# From the outside using the utils container, prefix the above with "docker exec utils"

