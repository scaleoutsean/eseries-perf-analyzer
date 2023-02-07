# Deploy InfluxDB v1 and Grafana v8 for EPA


- [Deploy InfluxDB v1 and Grafana v8 for EPA](#deploy-influxdb-v1-and-grafana-v8-for-epa)
  - [Assumptions](#assumptions)
  - [Sample configuration files](#sample-configuration-files)
  - [Create a namespace](#create-a-namespace)
  - [InfluxDB v1](#influxdb-v1)
    - [InfluxDB storage](#influxdb-storage)
    - [Other configuration, secrets and standing up InfluxDB](#other-configuration-secrets-and-standing-up-influxdb)
  - [Grafana v8](#grafana-v8)
  - [Connect Grafana to InfluxDB (deploy InfluxDB data source and Grafana dashboards)](#connect-grafana-to-influxdb-deploy-influxdb-data-source-and-grafana-dashboards)
    - [Automated approach with Ansible when Grafana and InfluxDB are in the same namespace](#automated-approach-with-ansible-when-grafana-and-influxdb-are-in-the-same-namespace)
    - [Automated approach with Ansible from your client, VM or other location](#automated-approach-with-ansible-from-your-client-vm-or-other-location)
    - [Manually add InfluxDB as Grafana Data Source](#manually-add-influxdb-as-grafana-data-source)
      - [Manually import Grafana dashboards](#manually-import-grafana-dashboards)
      - [Other ways to provision Grafana data sources and dashboards](#other-ways-to-provision-grafana-data-sources-and-dashboards)
  - [Wrap-up](#wrap-up)
  - [Video demo](#video-demo)


## Assumptions

- Recent Kubernetes such as v1.25
- EPA v3.2.0 (InfluxDB v1, Grafana v8, SANtricity OS 11.7)
- CSI plugin for persistent volumes
- Existing InfluxDB, Grafana in the same namespace used for monitoring: `epa`

## Sample configuration files 

These are for reference only. Please use own files and best practices in production and remember to adjust the namespace if necessary.

- 01-pvc-influxdb.yaml: production-style PVCs (three volumes) for InfluxDB. Maybe you want to increase the size of the largest volume to more than 10GB. Storage Class name can also be changed if you don't have the one used here.
- 02-pvc-grafana.yaml: optional PVC for Grafana. Storage Class name can be changed if you don't have the one used here.
- 03-svc-influxdb.yaml: InfluxDB service 
- 04-svc-grafana.yaml: Grafana service
- 05-configmap-grafana.yaml: Grafana config map
- 06-dep-grafana.yaml: Grafana deployment that uses configmap from 05-configmap-grafana.yaml and 02-pvc-grafana.yaml
- 07-dep-influxdb.yaml: deployment for InfluxDB; it uses three volumes created in 01-pvc-influxdb.yaml

**NOTE:** for deployment files, do not forget to edit the image location (local build, Docker Hub, private registry, etc.)!

## Create a namespace

In this repo all examples and YAML files use the `epa` namespace. Many seem to standardize on `monitoring`, but you may have production monitoring applications there, so I use `epa` instead. Search & replace `namespace: epa` in the provided YAML files to use a different namespace.

```sh
kubectl create namespace epa
```

## InfluxDB v1

EPA v3.2.0 uses InvluxDB v1.

Port 8086/tcp is used for client connections and should be open to all *external* collector and dbmanager clients as well as Grafana (if Grafana runs externally). 

Collector and dbmanager do not use authentication, so either create firewall rules to allow only external collector by IP address, or run collector and dbmanager in the same namespace as InfluxDB to eliminate the need for external access to InfluxDB.

### InfluxDB storage

One, two or three PVs (in increasing order of resilience) may be used for InfluxDB storage. According to [the official documentation for v1.8](https://docs.influxdata.com/influxdb/v1.8/concepts/file-system-layout/?t=Kubernetes#kubernetes-default-paths), data paths are as follows:

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

I because WAL and Meta aren't large, there isn't much disadvantage in using three separate PVCs, which is the approach taken by the sample YAML files. 

### Other configuration, secrets and standing up InfluxDB

Various configuration options for InfluxDB may be viewed [here](https://docs.influxdata.com/influxdb/v1.8/introduction/install/).

InfluxDB secrets can be complex or simple depending on needs. EPA collector has never used authentication (because it used to runs on the same network as InfluxDB), so we cannot simply create INFLUXDB_USER (that's why it's marked-out) without modifying collector and dbmanager scripts to add authentication. 

If you will run collector and dbmanger as they are, create proper firewall rules for the InfluxDB external IP (to allow only external collectors to connect to it), or run collector(s) and dbmanger in the same namespace.

`influxdb.yaml` contains service configuration that listens on port 8086/tcp.

```sh
git clone https://github.com/scaleoutsean/eseries-perf-analyzer/
cd eseries-perf-analyzer/epa
pwd
# /home/sean/eseries-perf-analyzer/epa

# build EPA containers
make build
# see new images
docker images

# go to K8s samples
cd ../kubernetes/samples
pwd
# /home/sean/eseries-perf-analyzer/kubernetes/samples

# create K8s secrets
kubectl -n epa create secret generic influxdb-creds \
  --from-literal=INFLUXDB_DB=eseries \
  --from-literal=INFLUXDB_ADMIN_USER=root \
  --from-literal=INFLUXDB_ADMIN_USER_PASSWORD=NetApp123 \
  --from-literal=INFLUXDB_HOST=influxdb  \
  --from-literal=INFLUXDB_HTTP_AUTH_ENABLED=false # \
  # --from-literal=INFLUXDB_READ_USER=grafana \
  # --from-literal=INFLUXDB_READ_USER_PASSWORD=grafana123readonlyUSER \
  # --from-literal=INFLUXDB_USER=monitor \
  # --from-literal=INFLUXDB_USER_PASSWORD=monitor123collector01 \
```

**NOTE** 

- EPA v3.0.0 does not have database authentication for collector and Grafana, because they used to run in the same docker-compose deployment. EPA v3.1.0 and v3.2.0 did not change that, so authentication options are marked out. If user authentication is used, dbmanager and collector will not be able to access InfluxDB. 
- For Grafana, is possible to create a read-only account here, but if automated deployment of InfluxDB data source is used authentication won't be set up. To work around that create a read-only account for Grafana here, configure data source with Ansible (see below), and then modify Grafana's WSP data source to use authentication. What that will do is prevent deletion of data from Grafana.

With `influxdb-creds` ready, next we create PVCs, service and finally deployment:

```sh
kubectl -n epa apply -f 01-pvc-influxdb.yaml
kubectl -n epa apply -f 03-svc-influxdb.yaml
# 07-dep-influxdb.yaml uses influxdb-creds created with kubectl (see above)
kubectl -n epa apply -f 07-dep-influxdb.yaml
# persistentvolumeclaim/influxdb-data-pvc created
# persistentvolumeclaim/influxdb-wal-pvc created
# persistentvolumeclaim/influxdb-meta-pvc created
# deployment.apps/influxdb created
# service/influxdb created

kubectl -n epa get services
# NAME       TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
# influxdb   LoadBalancer   10.109.24.223   <pending>     8086:32328/TCP   37s
```

As you can see there's no `EXTERNAL-IP` which means InfluxDB is not exposed to LAN or the Internet. This is fine if the rest of containers will run in the `epa` namespace. 

If you need to use InfluxDB from outside of Kubernetes (if either Grafana, or collector, or dbmanager will run externally), [add `EXTERNAL-IP`](https://kubernetes.io/docs/tutorials/stateless-application/expose-external-ip-address/) depending on your environment.

## Grafana v8

Grafana can be deployed in several ways. High-level choices:

- Use official Grafana instructions and container (DIY style)
- Use EPA Grafana container (built with `make build` above)

EPA Grafana is the same as official Grafana (Open Source), but it includes the config file `./epa/grafana/grafana.ini`. If you want to customize that file for your Grafana (to remove "phone home", for example), edit that file and from `./epa` run `make build` again. Remember to use the resulting image in `07-dep-grafana.yaml`.

If you want to use official image, see [the official instructions](https://grafana.com/docs/grafana/latest/setup-grafana/installation/kubernetes/) or [one](https://medium.com/starschema-blog/monitor-your-infrastructure-with-influxdb-and-grafana-on-kubernetes-a299a0afe3d2) [of](https://iceburn.medium.com/build-from-scratch-grafana-and-prometheus-on-minikube-228d4e9cfda0) the many community guides for version 8.

In both cases default credentials are the same: admin/admin can be used to log in.

In production, Grafana service would be behind a reverse proxy. There are too many ways to do that and that's out of scope here, so I'll just assume this was done the way you wanted.

```sh
kubectl -n epa apply -f 02-pvc-grafana.yaml
kubectl -n epa apply -f 04-svc-grafana.yaml
kubectl -n epa apply -f 05-configmap-grafana.yaml
kubectl -n epa apply -f 06-dep-grafana.yaml

kubectl -n epa get services
# NAME       TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)          AGE
# grafana    LoadBalancer   10.108.183.87   <pending>     3000:30104/TCP   46m
# influxdb   LoadBalancer   10.109.24.223   <pending>     8086:32328/TCP   37s
```

Like with InfluxDB, you need `EXTERNAL-IP` or port forwarding if you want to connect from the outside world.

With Grafana ready, we can add a InfluxDB v1 data source. There are 4-5 ways to do that. Let's start with the same approach used in EPA: Ansible.

## Connect Grafana to InfluxDB (deploy InfluxDB data source and Grafana dashboards)

We can reuse Ansible from EPA here, but the Ansible playbook was done for Docker Compose and we need it to work with Kubernetes. There are two ways:

- run EPA Ansible container in InfluxDB/Grafana namespace (if these share namespace) - no changes to Ansible YAML files required
- run Ansible from Docker (using EPA's Ansible container image) or OS shell (Ansible must be installed) anywhere where you can reach `EXTERNAL-IP` of InfluxDB and Grafana - LAN IPs for InfluxDB and Grafana are required here, so search & replace in Ansible YAML files is also required

Both approaches work the same as they do in EPA with Docker Compose: Ansible configures the default Data Source ("WSP"), adds another Data Source for internal InfluxDB metrics, and deploys the dashboards (four for E-Series, one for InfluxDB v1 internal metrics).

**NOTE:** Ansible adds a new data source ("WSP") and makes it the Grafana default. Make sure your other Grafana dashboards do not depend on there being some other default data source.

### Automated approach with Ansible when Grafana and InfluxDB are in the same namespace

For this we need to execute EPA Ansible container **in the Kubernetes namespace where InfluxDB and Grafana run**.

If EPA Grafana was built with `cd epa & make build` earlier, the Ansible container should be already ready to use. If not, go to the top-level `epa` directory and run `make build`. Use `docker images | grep ansible` to find the container name and version.

InfluxDB and Grafana must be reachable at `influxdb:8086` and `http://grafana:3000`, respectively, otherwise Ansible won't be able to connect.

```sh
# find the ansible container buit in ./epa with make build
docker images | grep ansible
# ntap-grafana/ansible:3.1

# run this in the same namespace where InfluxDB and Grafana are (example: epa)
kubectl run ansible --restart=Never --image=ntap-grafana/ansible:3.1 -n epa

# this image hasn't changed from upstream v3.0.0, so you can use v3.0.0 or v3.1 you already have it in your registry
# kubectl run ansible --restart=Never --image=regi.istry.lan/ntap-grafana/ansible:3.0 -n epa
# or (container image uploaded by me to Docker Hub)
# kubectl run ansible --restart=Never --image=docker.io/scaleoutsean/epa-ansible:v3.2.0 -n epa

# check that the ansible pod is running

kubectl get pods -n epa
# NAME                                   READY   STATUS    RESTARTS       AGE
# ansible                                1/1     Running   0              3s     <==== running!
# collector-dbmanager-6f577597c4-bhppx   1/1     Running   0              7m27s
# grafana-ff9ff46d4-nsnw6                1/1     Running   0              14m
# influxdb-f4bb6575d-z44wt               1/1     Running   3 (118m ago)   44h

# once it's stopped, you can remove it
kubectl delete pod ansible -n epa
```

Now Grafana should have two new Data Sources and EPA dashboards. If it doesn't, that means Ansible failed to connect to InfluxDB and Grafana in the `epa` namespace. You need to fix that and run the pod again.

If you want to use this approach but Grafana and InfluxDB are *not* in the same namespace, maybe they can be deployed to the same namespace, and Grafana can be exported after Ansible has completed its configuration. See below for other approaches.

### Automated approach with Ansible from your client, VM or other location

In the second approach we need to change Grafana address in several YAML files to be the same as external Grafana service address. I changed `http://grafana:3000` to `http://192.168.1.127:3000` in the following files.

- ./epa/ansible/tasks/dashboard_import.yml
- ./epa/ansible/tasks/grafana_backup.yml
- ./epa/ansible/tasks/plugin_tasks/influxdb_internal_monitoring/datasource.yml
- ./epa/ansible/tasks/grafana.yml

The same needs to be done for InfluxDB. I changed `influxdb:8086` to `192.168.1.127:8086` in the following locations:

- ./epa/ansible/tasks/plugin_tasks/influxdb_internal_monitoring/datastore.json
- ./epa/ansible/datastore.json

At this stage it's possible to run Ansible from a container (for which we'd have to build a new container image by running `make build` in the epa subdirectory) or - I think this is easier - we can install Ansible and run the Ansible playbook from the shell:

```sh
# we're in ./epa/ansible
pwd
# /home/sean/eseries-perf-analyzer/epa/ansible

# install Ansible as per the Ansible documentation

# run the playbook without container
ansible-playbook main.yml
```

### Manually add InfluxDB as Grafana Data Source

If you can't make Ansible work, you can try the manual approach. I strongly recommend *against* the manual approach for Grafana dashboards - it's a nightmare!

Add InfluxDB v1 source by replicating configuration from Grafana in EPA v3.2.0 created with docker-compose. This is to make sure that EPA dashboards can find Data Source by the expected name ("WSP").

If Grafana and InfluxDB are the same namespace, InfluxDB can be added as `http://influxdb:8086/` (screenshots here show InfluxDB exposed on a Class A network, which is what I tried).

A read-only InfluxDB account can be created for Grafana (done earlier for demo purposes when creating InfluxDB secrets: grafana/grafana123readonlyUSER) and then Basic Auth can be enabled in Grafana Data Sources. EPA by default doesn't use authentication for InfluxDB, so no need to enable Basic Auth if you didn't configure it in Influx.

With BasicAuth disabled (default in EPA, Ansible also deploys this way):

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

With BasicAuth enabled (using the same credentials created in InfluxDB section above, and the DB name `eseries`):

```json
{
  "name": "WSP",
  "isDefault": true,
  "type": "influxdb",
  "access": "proxy",
  "database": "eseries",
  "user": "grafana",
  "url": "http://influxdb:8086",
  "jsonData": {
    "httpMode": "GET"
  },
  "secureJsonData": {
    "password": "grafana123readonlyUSER"
  }
}
```

In my test environment InfluxDB was available at an `EXTERNAL-IP` and Grafana Data Source was added with Basic Auth like this ("WSP" comes from Web Services Proxy, the data source name inherited from upstream EPA v3.0.0).

![Create Grafana Data Source for InfluxDB v1](../../images/kubernetes-01-influxdb-datasource.png)

If authentication was not configured in the InfluxDB section (`kubectl -n epa create secret generic influxdb-creds`), or you don't want to use authentication for Grafana, it's unnecessary to enable Basic Auth and provide credentials for Grafana account on InfluxDB. But if your InfluxDB is open to LAN clients, it's better to protect it and use a read-only account in Grafana.

Also notice that EPA by default uses the `eseries` database. If Grafana connects to InfluxDB while the DB is still missing, Grafana will complain about the missing database (screenshot below). That's not a problem because the database will be created later (by collector or by dbmanager).

![Database missing until created](../../images/kubernetes-02-influxdb-datasource-influxdb-eseries-missing.png)

The InfluxDB API or CLI can be used create a database before that. Then Save & Test will show that Data Source is fully validated (below).

![Database available after created](../../images/kubernetes-03-influxdb-datasource-influxdb-eseries-present.png)

Either way is fine. It's easier to ignore this and let dbmanager automatically create initial data.

If possible, make the WSP data source your Default data source in Grafana. That seems to cause less problems when EPA dashboards are imported in various approaches.

#### Manually import Grafana dashboards

The EPA dashboards can be found in `./epa/plugins/eseries_monitoring/dashboards`, but importing them manually is another problem.

Visit `http://${GRAFANA_IP}:3000/dashboard/import` to import them. You'll probably have problems here and should take another look at Ansible instead.

At this time dashboard can be viewed, but without anything to see. If you get a blank page (like [this](../../images/kubernetes-04-grafana-dashboard-problem.png)), it's best to start the collector and then refresh a dashboard view. In this screenshot dbmanager we started earlier is sending data to InfluxDB.

![dbmanager data in Explorer](../../images/kubernetes-05-grafana-explore-dbmanager-data.png)

If Grafana > Explore shows nothing while collector is successfully sending data to InfluxDB, Data Source is probably misconfigured.

If Grafana > Explore shows E-Series data from Influx data source but dashboards show nothing, dashboards may be messed up or there's a mismatch between the name expected by the dashboards vs. the InfluxDB data source name that exists in Grafana. Fix data source name or change dashboards (perform a search & replace on the dashboard files).

#### Other ways to provision Grafana data sources and dashboards

Grafana also lets you use its provisioning features to automatically provision [data sources](https://grafana.com/docs/grafana/latest/administration/provisioning/#data-sources) and [dashboards](https://grafana.com/docs/grafana/latest/administration/provisioning/#reusable-dashboard-urls).

I found these to be buggy and frustratingly hard to use. 

In theory, all it takes is to build a Grafana container with the `/etc/grafana/provisioning/dashboards` path pre-populated with a dashboard source defnition (YAML) and EPA dashboards. This is how Grafana container subdirectory would look like before `docker build`:

```raw
.
├── Dockerfile
└── provisioning
    ├── dashboards
    │   ├── dashboards.yaml
    │   ├── system.json
    │   └── interface.json
    │   └── disk.json
    │   └── volume.json
    └── datasources
        └── influxd.yaml
```

dashboards.yaml would look something like this:

```yaml
apiVersion: 1
providers:
  - name: 'EPA'
    folder: ''
    type: file
    orgId: 1
    folderUid: ''
    allowUiUpdates: true
    updateIntervalSeconds: 30
    options:
      path: /etc/grafana/provisioning/dashboards
```

Grafana Dockerfile would copy this to the container with `ADD ./provisioning /etc/grafana/` and Grafana would load JSON files after startup. But I couldn't get this to work, maybe due to small errors in the exported EPA dashboard files or some other reason.

Maybe Grafana Helm charts work better. I haven't tried.

Recreating dashboards from scratch is possible, but could turn out to be time-consuming.

## Wrap-up

Now the correct functioning of Grafana and InfluxDB can be checked.

This screenshot shows dbmanager with a different container name to what's in YAML file. (The reason is it was rebuilt to check if it can send data to InfluxDB's External IP address, as explained earlier). Container names can be changed to anything that suits your environment, of course.

![EPA deployments in Kubernetes dashboard](../../images/kubernetes-06-dashboard.png)

In this section InfluxDB and Grafana were deployed to the same namespace (`epa`), exposed as services, and configured so that Grafana has access to InfluxDB databases and EPA dashboards.

## Video demo

- EPA 3.2.0 on Kubernetes: TODO
- [EPA 3.1.0 on Kubernetes](https://rumble.com/v25nep8-e-series-performance-analyzer-3.1.0-on-kubernetes.html) (3m16s) - uses YAML files and automated Data Source and dashboard deployment approach with Ansible container running in Kubernetes.

