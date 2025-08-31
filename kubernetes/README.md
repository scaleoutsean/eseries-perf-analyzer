# Deploy EPA collector(s)


- [Deploy EPA collector(s)](#deploy-epa-collectors)
  - [Assumptions](#assumptions)
  - [Deployment decisions](#deployment-decisions)
  - [Create a namespace and deploy InfluxDB and Grafana](#create-a-namespace-and-deploy-influxdb-and-grafana)
    - [Create a namespace](#create-a-namespace)
    - [Deploy InfluxDB version 1 and Grafana version 8](#deploy-influxdb-version-1-and-grafana-version-8)
  - [Prepare configuration files and deploy EPA Collector](#prepare-configuration-files-and-deploy-epa-collector)
    - [collector(s)](#collectors)
  - [Result](#result)

If you'd prefer to watch a 3 minute deployment video rather than read a lot of text, see it [here](samples/README.md#video-demo).

## Assumptions

- Recent Kubernetes 
- EPA v3.5.0 (InfluxDB v1, Grafana v8, SANtricity OS 11.80)
- CSI plugin for persistent volumes
- Existing InfluxDB, Grafana in the same namespace used for monitoring: `epa`

## Deployment decisions

Collector doesn't expose any service ports and doesn't use TLS certificates since all containers (or at least InfluxDB) can run in the same namespace.

The main thing to decide is where to run collectors: in the same namespace, in the same Kubernetes cluster, or externally and closer to each E-Series array (in which case InfluxDB 8086/tcp must be exposed at `EXTERNAL-IP` and (should be) secured by firewall rules).

Another concern is whether you want to encrypt the monitor account password (used by collector). If the SANtricity (read-only) monitor-type account is used, the consequence of its password being exposed is that someone could see your E-Series metrics, capacity and such - in other words, a very limited impact. Additionally, each collector can run in a different location, be secured by respective E-Series "owner", and use a different password. The risk is low and that's why collector still stores credentials in deployment's ENV variables. But collector deployment YAML can be modified and password stored elsewhere similarly to what we do for InfluxDB.

## Create a namespace and deploy InfluxDB and Grafana

### Create a namespace

Examples and YAML files use the `epa` namespace. Many how-to's seem to standardize on `monitoring`, but you may have production monitoring applications there so I use `epa` instead. Use the right namespace for *your* environment. If you don't have a namespace, you can create one:

```sh
kubectl create namespace epa
```

### Deploy InfluxDB version 1 and Grafana version 8

You may deploy InfluxDB v1 (v1.8, for example) and Grafana version 8 any way you want. Just make sure that:

- InfluxDB is reachable by Collector and by Grafana 
- Grafana is reachable from your browser

You can find plenty of details about these deployments and services in the [samples](samples/README.md) directory, but the configuration of these services is out of scope here - please use community guides or the official documentation to figure it out.

Even if you know how to deploy Grafana, pay attention to that README file in the samples directory because it shows how to create data source and import EPA dashboards (which have the data source name hard-coded). If you want to create own dashboards or import EPA dashboards on your own, then you can skip it.

## Prepare configuration files and deploy EPA Collector 

### collector(s)

Because the JSON example above uses two arrays, two sample YAML files (02 and 03) are provided because each array uses its own collector. 

Change at least the following:

- Enter your SANtricity API endpoint IPv4 (`API`; port 8443 is assumed), a `SYSNAME` that should match the name of the array, `SYSID` which is WWN for the array (see the [main README](../README.md)), and username/password pair for the SANtricity API user (best use the `monitor` account because that one is read-only and has limited permissions). Use the same `DB_ADDRESS` for all collectors that store to the same  server.

```yaml
data:
  API: "5.5.5.5"
  SYSNAME: "R26U25-EF600" # note uppercase letters - may be easier to read in Grafana 
  SYSID: "600A098000F63714000000005E791234"
  DB_ADDRESS: "7.7.7.7"
  USERNAME: "monitor"
  PASSWORD: "monitor123"
```

- In all places where `r26u25-ef600` appears (container names and whatnot), search & replace that string with your `SYSNAME`, so that you can tell one collector container from another.

- Change the image source if you don't want to use the one from Docker Hub

Then deploy each configuration file, or just one if you have one array: 

```sh
kubectl -n epa apply -f 02-epa-collector-EF600.yaml
kubectl -n epa apply -f 03-epa-collector-E2824.yaml
```

## Result

One InfluxDB, one Grafana, and one or more Collectors:

```sh
kubectl -n epa get pods
# NAME                                      READY   STATUS    RESTARTS   AGE
# collector-r24u04-e2824-5ffd5886-tmnpl     1/1     Running   0          4s
# collector-r26u25-ef600-74c67fc88d-qzbv5   1/1     Running   0          22s
# grafana-8966fdf6b-2kxnv                   1/1     Running   0          3h58m
# influxdb-f4bb6575d-z44wt                  1/1     Running   0          176m
```

Go to Grafana > Explore to see if the InfluxDB v1 datab source is available to Grafana.

