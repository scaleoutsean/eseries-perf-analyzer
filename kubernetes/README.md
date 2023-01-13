## E-Series Performance Analyzer on Kubernetes

Assumptions:

- Kubernetes v1.25
- EPA v3.1.0 (InfluxDB v1, Grafana v8, SANtricity OS 11.7)
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

According to [the official documentation for v1.8](https://docs.influxdata.com/influxdb/v1.8/concepts/file-system-layout/?t=Kubernetes#kubernetes-default-paths), data paths are as follows:

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

Configuration options for InfluxDB may be viewed [here](https://docs.influxdata.com/influxdb/v1.8/introduction/install/).

InfluxDB secrets can be complex or simple depending on needs. EPA collector has never used authentication (because it used to runs on the same network as InfluxDB), so we cannot simply create INFLUXDB_USER (that's why it's marked-out) without modifying collector and dbmanager. 

If you cannot modify collector and dbmanger, create proper firewall rules for InfluxDB external IP, or run collector(s) and dbmanger in the same namespace.

`influxdb.yaml` contains service configuration that listens on port 8086/tcp. Remove that if there's no or modify it as you please.

```yml 
kubectl create secret generic influxdb-creds \
  --from-literal=INFLUXDB_DB=eseries \
  --from-literal=INFLUXDB_READ_USER=grafana \
  --from-literal=INFLUXDB_READ_USER_PASSWORD=grafana123readonlyUSER \
  --from-literal=INFLUXDB_ADMIN_USER=root \
  --from-literal=INFLUXDB_ADMIN_USER_PASSWORD=NetApp123 \
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

To build and deploy these containers:

- edit config.json and run "make build" to build containers
- edit dbmanager*.yaml and collector*.yaml to tell Kubernetes where to get the container image (internal registry, etc.)
- for each E-Series system, make a copy of sample collector file and create per-array YAML file(s). **NOTE:** similarly to docker-compose, if collector runs in the same namespace as InfluxDB, `DB_ADDRESS` can be `influxdb`.

```sh
cp collector-collector-sample.yml collector-${SYSNAME}.yml
vim collector-${SYSNAME}.yml
kubectl apply -f collector-${SYSNAME}.yaml

kubectl apply -f collector-dbmanager.yaml
```

dbmanager creates tags in InfluxDB's eseries database. These help EPA's ready-made Grafana dashboards show arrays in a drop down list. dbmanager can be started before or after collector(s). 

We need just one dbmanager container per InfluxDB, so we can run it in the same namespace as InfluxDB.

```sh
kubectl get pods
# NAME                                      READY   STATUS    RESTARTS   AGE
# collector-dbmanager-5b5b6945c8-zpf64      1/1     Running   0          45s
# collector-r24u04-e2824-5ffd5886-tmnpl     1/1     Running   0          4s
# collector-r26u25-ef600-74c67fc88d-qzbv5   1/1     Running   0          22s
# grafana-8966fdf6b-2kxnv                   1/1     Running   0          3h58m
# influxdb-f4bb6575d-z44wt                  1/1     Running   0          176m
```

Observe container logs to see if there are any issues. Collector and dbmanager should be sending data to InfluxDB.

Even without E-Series present, dbmanager in v3.1.0 works because all it does is read config.json and push the array names to InfluxDB. Let's see:

```sh
$ kubectl logs collector-dbmanager-5b5b6945c8-zpf64
2023-01-13 13:51:11,491 - collector - INFO - Reading config.json...
2023-01-13 13:51:11,501 - collector - INFO - Uploading folders to InfluxDB: [{'measurement': 'folders', 'tags': {'folder_name': 'All Storage Systems', 'sys_name': 'R26U25-EF600'}, 'fields': {'dummy': 0}}, {'measurement': 'folders', 'tags': {'folder_name': 'All Storage Systems', 'sys_name': 'R24U04-E2824'}, 'fields': {'dummy': 0}}]
2023-01-13 13:51:11,545 - collector - INFO - Update loop evaluation complete, awaiting next run...
2023-01-13 13:51:11,545 - collector - INFO - Time interval: 300.0000 Time to collect and send: 00.0538 Iteration: 1
```

### Grafana v8

Use [the official instructions](https://grafana.com/docs/grafana/latest/setup-grafana/installation/kubernetes/) or [one](https://medium.com/starschema-blog/monitor-your-infrastructure-with-influxdb-and-grafana-on-kubernetes-a299a0afe3d2) [of](https://iceburn.medium.com/build-from-scratch-grafana-and-prometheus-on-minikube-228d4e9cfda0) the many community guides for version 8.

Grafana can be setup to use Kubernetes secrets, similarly to how we did it with InfluxDB, but I haven't done that here and admin/admin can be used to log in.

In production Grafana would be behind a reverse proxy, but there are too many combinations and that's out of scope of this document in any case, so I'll just assume this was done the way you want it. Feel free to modify grafana.yaml if you can't find any better examples.

```sh
kubectl apply -f grafana.yaml

kubectl get services
# NAME       TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
# grafana    LoadBalancer   10.108.183.87   <pending>     3000:30104/TCP   46m
# influxdb   LoadBalancer   10.109.24.223   <pending>     8086:32328/TCP   37s
```

With Grafana ready, we can add InfluxDB v1 as data source.

You may want to disable anonynmous access (it is enabled by default and read-only) on first login.

#### Add InfluxDB as Grafana Data Source

Add InfluxDB v1 source by replicating configuration from Grafana in EPA v3.1.0 created with docker-compose.  This is to make sure that EPA dashboards can find Data Source by the expected name ("WSP").

If Grafana and InfluxDB are the same namespace, InfluxDB can be added as `http://influxdb:8066/`. The Grafana user can be created as a read-only InfluxDB user (which we did earlier for demo purposes when creating InfluxDB secrets).

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

![Create Grafana Data Source for InfluxDB v1](../images/kubernetes-01-influxdb-datasource.png)

Also notice that EPA by default uses the `eseries` database. If Grafana can connect to InfluxDB while the DB is missing, Grafana will complain about the missing database but that's not a problem because the database is created later (by collector).

![Database missing until created](../images/kubernetes-02-influxdb-datasource-influxdb-eseries-missing.png)

Alternatively, use the Influx API or CLI to create the database. Then Save & Test will show that Data Source is working.

![Database available after created](../images/kubernetes-03-influxdb-datasource-influxdb-eseries-present.png)

It's easier to let collector do it automatically.

#### Import Grafana dashboards

Grafana needs a PV to keep dashboards, settings and other data, so provision it with a 1GiB PV (done in grafana.yaml).

Visit `http://${GRAFANA_IP}:3000/dashboard/import` and login. Find the dashboards in `./epa/plugins/eseries_monitoring/dashboards` and import them. 

At this time dashboard can be visited, but they will be empty. If you see a blank page (like [this](../images/kubernetes-04-grafana-dashboard-problem.png)), it's best to start a collector and see if data will be sent to InfluxDB, and then refresh a dashboard view. In in this screenshot we can see that dbmanager started earlier is sending data to InfluxDB.

![dbmanager data in Explorer](../images/kubernetes-05-grafana-explore-dbmanager-data.png)

If Grafana > Explore shows nothing while collector is sending data to InfluxDB, Data Source is probably misconfigured.

If Grafana > Explore shows E-Series data from Influx data source but dashboards show nothing, dashboards may be messed up or there's a mismatch between the name expected by the dashboards vs. the InfluxDB data source name that exists in Grafana. Fix data source name or change dashboards (perform a search & replace on the dashboard files).

### Restore default context to kubectl 

```sh
kubectl config set-context --current --namespace=default
```
