# InfluxDB CLI and API 

## API

###HEADER="Authorization: Bearer `cat /home/influx/epa.token`"
curl --cacert /home/influx/certs/ca.crt --get https://influxdb:8181/api/v3/query_sql  --header "${HEADER}" --data-urlencode "db=epa" --data-urlencode "q=SELECT * FROM volumes LIMIT 2"

## CLI (influx is alias for influxdb3)

###TOKEN=`cat /home/influx/epa.token`
influx show databases
influxdb3 query --database "epa" "SHOW TABLES"
influxdb3 query --database "epa" "SHOW COLUMNS IN config_volumes"
influxdb3 query --database "epa" "SELECT * FROM interface LIMIT 1"
influxdb3 query --database "epa" "SELECT name FROM volumes LIMIT 3"
