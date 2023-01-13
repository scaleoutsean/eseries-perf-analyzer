## E-Series Performance Analyzer on Kubernetes

Assumptions:

- Kubernetes v1.28
- EPA v3.1.0 (InfluxDB v1, Grafana v8, SANtricity OS 11.74)
- CSI plugin for persistent volumes
- InfluxDB, collectors, dbmanager and Grafana in the same namespace, `epa`

### Namespace

Examples and YAML files use the `epa` namespace.

Search & replace `epa` in YAML files to use a different namespace.

```sh
kubectl create namespace epa
# "lock" kubectl to this namespace
kubectl config set-context --current --namespace=epa
```

### InfluxDB v1

EPA v3.1.0 uses InvluxDB v1.

Port 8086/tcp is used for client connections and should be open to all *external* collector and dbmanager clients as well as Grafana. Collectors do not use authentication so either create firewall rules or run collectors in the same namespace as InfluxDB to eliminate the need for external ingress to InfluxDB.

This walk-through doesn't run external collectors, so it is not required to expose InfluxDB.

One, two or three PVs (in increasing order of resilience) may be used for InfluxDB storage.

Default data paths are:

- Data: /var/lib/influxdb/data/
- WAL:  /var/lib/influxdb/wal/
- Metastore: /var/lib/influxdb/meta/

Filesystem overview:

```raw
/var/lib/influxdb/
                  data/
                        TSM directories and files
                  wal/
                        WAL directories and files
                  meta/
                        meta.db
```

Permissions:

```raw
.../influxdb/       755
.../influxdb/data/  755
.../influxdb/meta/  755
.../influxdb/wal/   700
```

[Source](https://docs.influxdata.com/influxdb/v1.8/concepts/file-system-layout/?t=Kubernetes#kubernetes-default-paths)

Configuration options are available [here](https://docs.influxdata.com/influxdb/v1.8/introduction/install/).

InfluxDB secrets can be complex or simple depending on situation. INFL

Below a service that listens on port 8086/tcp will be created. Modify as you please.

Find a way to expose port 8086 if your collector or dbmanager will run externally.

```yml 
kubectl create secret generic influxdb-creds \
  --from-literal=INFLUXDB_DB=eseries \
  --from-literal=INFLUXDB_READ_USER=readonly \
  --from-literal=INFLUXDB_READ_USER_PASSWORD=grafana123readonlyUSER \
  --from-literal=INFLUXDB_ADMIN_USER=root \
  --from-literal=INFLUXDB_ADMIN_USER_PASSWORD=NetApp123123 \
  --from-literal=INFLUXDB_HOST=influxdb  \
  --from-literal=INFLUXDB_HTTP_AUTH_ENABLED=false \
  # --from-literal=INFLUXDB_USER=monitor \
  # --from-literal=INFLUXDB_USER_PASSWORD=monitor123collector01 \

kubectl apply -f influxdb.yaml 
# persistentvolumeclaim/influxdb-data-pvc created
# persistentvolumeclaim/influxdb-wal-pvc created
# persistentvolumeclaim/influxdb-meta-pvc created
# deployment.apps/influxdb created
# service/influxdb created

kubectl get services
# NAME       TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
# influxdb   LoadBalancer   10.109.24.223   <pending>     8086:32328/TCP   37s
```

### collector and dbmanager

These containers don't need any service ports, TLS certificates and such. They can run in the same namespace as InfluxDB.

Main things to decide:

- where to keep the monitor account password. Collector needs read-only access E-Series, so it's probably okay to use Kubernetes Secrets for that.
- whether to run collectors - in the same namespace, in the same cluster, or externally (in which ase InfluxDB requires externally available 8086/tcp)

Collector sends data to InfluxDB.

To build and deploy these containers we need to:

- edit config.json and run "make build" to build containers
- for each E-Series system, make a copy of sample collector file

```sh
cp collector-collector-sample.yml collector-${SYSNAME}.yml
vim collector-${SYSNAME}.yml
kubectl apply -f collector-${SYSNAME}.yaml
```

dbmanager creates tags in InfluxDB's eseries database. These help EPA's ready-made Grafana dashboards show arrays in a drop down list. dbmanager can be started before or after collector(s). 

We need just one dbmanager container per InfluxDB, so we can run it in the same namespace as InfluxDB.

```sh
kubectl apply -f collector-dbmanager.yaml
```

Observe these container logs to see if there are any issues. They should be sending data to InfluxDB.

### Grafana v8

Use [the official instructions](https://grafana.com/docs/grafana/latest/setup-grafana/installation/kubernetes/) or [one](https://medium.com/starschema-blog/monitor-your-infrastructure-with-influxdb-and-grafana-on-kubernetes-a299a0afe3d2) [of](https://iceburn.medium.com/build-from-scratch-grafana-and-prometheus-on-minikube-228d4e9cfda0) the many community guides for version 8.

This example exposes Grafana on node port (http://${node}:3000). This is probaly **not** how you want to expose it, but it can work.

```sh
kubectl apply -f grafana.yaml

kubectl get services
# NAME       TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
# grafana    LoadBalancer   10.108.183.87   <pending>     3000:30104/TCP   46m
# influxdb   LoadBalancer   10.109.24.223   <pending>     8086:32328/TCP   37s
```

With Grafana ready, we can add InfluxDB v1 as data source.

You may want to disable anonynmous access (it is enabled by default and read-only) in Grafana.

#### Add Grafana data source

Add InfluxDB v1 source by replicating configuration from Grafana in EPA v3.1.0 created with docker-compose. 

This is to make sure dashboards can find the data source.

If Grafana and InfluxDB are the same namespace, InfluxDB can be added as http://influxdb:8066/. The Grafana user can be created as a read-only InfluxDB user.

```json
{
  "name":"WSP",
  "label": "WSP",
  "type": "influxdb",
  "url":"http://influxdb:8086",
  "access":"proxy",
  "basicAuth": false,
  "isDefault": true,
  "database":"eseries"
}
```

In my test environment InfluxDB Data Source was added like so ("WSP" comes from Web Services Proxy, the name from upstream EPA). Notice that if authentication was not configured (in InfluxDB secrets), it would not be necessary to configure it for the source.

![Create Grafana Data Source for InfluxDB v1](./images/kubernetes-01-influxdb-datasource.png)

Also notice that EPA by default uses the `eseries` database. If Grafana can connect to InfluxDB, but the DB is missing, this is good enough because the database is created later (by collector).

![Database missing until created](./images/kubernetes-02-influxdb-datasource-influxdb-eseries-missing.png)

Alternatively, use the Influx API or CLI to create the database. Then Save & Test will show that Data Source is working.

![Database available after created](./images/kubernetes-03-influxdb-datasource-influxdb-eseries-present.png)

#### Import Grafana dashboards

Grafana needs a PV to keep dashboards, settings and such, so provision it with a PV.

Visit http://${GRAFANA_IP}:3000/dashboard/import. Find dashboards in `./epa/plugins/eseries_monitoring/dashboards` and import them. 

At this time dashboard can be visited, but they will be empty. If you see a blank page (like [this](./images/kubernetes-04-grafana-dashboard-problem.png)), it's best to start a collector and see if data will be sent to InfluxDB, and then refresh a dashboard view.

If Grafana > Explore shows nothing while collector is sending data to InfluxDB, Data Source is probably misconfigured.

If Grafana > Explore shows E-Series data from Influx data source but dashboards show nothing, dashboards may be messed up or there's a mismatch between the name expected by the dashboards vs. the InfluxDB data source name that exists in Grafana. Fix data source name or change dashboards (perform a search & replace on the dashboard files).

### Restore default context to kubectl 

```sh
kubectl config set-context --current --namespace=default
```
