
## InfluxDB

### SQL API

HEADER="Authorization: Bearer "`cat /influxdb_tokens/epa.token`

curl --cacert --cacert=/s3_certs/ca.crt --get https://influxdb:8181/api/v3/query_sql  --header "${HEADER}" --data-urlencode "db=epa" --data-urlencode "q=SELECT * FROM volumes LIMIT 2"

### CLI

TOKEN=`cat /influxdb_tokens/epa.token`
/home/influx/.influxdb/influxdb3 query -H https://influxdb:8181 --token "$TOKEN" --database "epa" "SHOW TABLES"
/home/influx/.influxdb/influxdb3 query -H https://influxdb:8181 --token "$TOKEN" --database "epa" "SHOW COLUMNS IN config_volumes"
/home/influx/.influxdb/influxdb3 query -H https://influxdb:8181 --token "$TOKEN" --database "epa" "SELECT * FROM interface LIMIT 1"
/home/influx/.influxdb/influxdb3 query -H https://influxdb:8181 --token "$TOKEN" --database "epa" "SELECT name FROM volumes LIMIT 3"




