# NetApp E-Series Performance Analyzer ("EPA")

- [NetApp E-Series Performance Analyzer ("EPA")](#netapp-e-series-performance-analyzer-epa)
  - [What is this thing](#what-is-this-thing)
  - [What E-Series metrics does EPA collect](#what-e-series-metrics-does-epa-collect)
  - [Requirements](#requirements)
  - [Quick start](#quick-start)
  - [Slow start](#slow-start)
    - [Environment variables and configuration files](#environment-variables-and-configuration-files)
    - [Adjust firewall settings for InfluxDB and Grafana ports](#adjust-firewall-settings-for-influxdb-and-grafana-ports)
    - [Add or remove a monitored array](#add-or-remove-a-monitored-array)
    - [Update password of a monitor account](#update-password-of-a-monitor-account)
  - [Walk-through](#walk-through)
    - [Using public Docker images](#using-public-docker-images)
  - [Sample Grafana screenshots](#sample-grafana-screenshots)
  - [FAQs](#faqs)
  - [Changelog](#changelog)


## What is this thing

This is a friendly fork of [E-Series Performance Analyzer aka EPA](https://github.com/NetApp/eseries-perf-analyzer) v3.0.0 (see its README.md for additional information) created with the following objectives:

- Disentangle E-Series Collector from the rest of EPA and make it easy to run it anywhere (shell, Docker/Docker Compose, Kubernetes, Nomad)
- Remove SANtricity Web Services Proxy (WSP) dependency from Collector and remove WSP from EPA, so that one collector container or script captures data for one and only one E-Series array

In terms of services, collectors collects metrics from E-Series and sends them to InfluxDB. dbmanager doesn't do much at this time - it periodically sends array names as folder tags to InfluxdDB.

![E-Series Performance Analyzer](/images/epa-eseries-perf-analyzer.png)

Each of the light-blue rectangles can be in a different location (host, network, Kubernetes namespace, etc.). But if you want to consolidate, that's still possible.

Change log and additional details are at the bottom of this page and in the Releases tab.

## What E-Series metrics does EPA collect

- System
- Volumes
- Interfaces
- E-Series MEL events
- Environmental (temperature and power consumption)

## Requirements

- NetApp SANtricity OS: >= 11.70 (11.80 is recommended; 11.52, 11.74, 11.80 have been tested and work, 11.6[0-9] not yet)
- Containers:
  - Docker: Docker CE 20.10.22 (recent Docker CE or Podman should work) and Docker Compose v1 or v2 (both v1 and v2 should work) 
  - Kubernetes: dbmanager and collector should work on any
  - Nomad: dbmanager and collector should work on any
- CLI: 
  - dbmanager and collector should work on any Linux with recent Python 3, possibly other Operating Systems
- Architecture: dbmanager and collector work on (at least) AMD64 and ARM64 systems that support Python 3

These requirements are soft but this is a community fork without a variety of hardware and software to use in testing and debugging.

## Quick start

Docker Compose users:

- Download and decompress latest release and enter the `epa` subdirectory:
```sh
git clone https://github.com/scaleoutsean/eseries-perf-analyzer/
cd eseries-perf-analyzer/epa
```
- the `epa` subdirectory: enter it, and use `make run` to build and run InfluxDB and Grafana
  - Unless these containers need a change or update, going back to this folder is generally not necessary
- the `collector` subdirectory: go one level up from `epa`, and enter the `collector` sub-directory 
  - edit `docker-compose.yml` and `config.json`: `SYSNAME` in docker-compose.yml must be present and identical to `name` value(s) in `config.json` 
  - run `docker-compose build && docker-compose up` to start dbmanager and collector(s)
  - if/when E-Series arrays are added or removed, edit the same files and run `docker-compose build && docker-compose down && docker-compose up` to update

Kubernetes users should skim through this page to get the idea how EPA works, and then follow [Kubernetes README](kubernetes/README.md).

## Slow start

It is suggested to get EPA working in Docker Compose, unless you're good at Kubernetes. There's also a [Kubernetes](kubernetes)-specific folder.

- Older existing EPA (v3.0.0, v3.1.0), images, volumes and services may cause container name, volume and port conflicts. Either use a new VM or find the existing (old) deployment and run `make stop; docker-compose down; make rm` to stop and remove old EPA pre-v3.2.0 containers before building new ones. Data (InfluxDB and Grafana) can be left in place.
- For latest (which may be broken or buggy) clone this repository to a new location; for more tested, download from Releases
- Descend to the `epa` directory, run `make run` to download, build and start InfluxDB v1 and Grafana v8. You may move the pre-existing InfluxDB folder to the EPA directory if you want to keep the data. Both services will listen on all public VM interfaces, so configure your firewall accordingly.
- Go to the `collector` directory, edit two files (`config.json` and `docker-compose.yml`) and run `docker-compose build` to create collector and dbmanager containers and then `docker-compose up` to start them.

```sh
git clone github.com/scaleoutsean/eseries-perf-analyzer
cd eseries-perf-analyzer
# make and run Grafana and InfluxDB
cd epa; make run
# go to the collector subdirectory
cd ..; cd collector
# Enter names of E-Series array (or arrays) to show in Grafana drop-down list.
# "docker-comose build" will copy this file to dbmanager.
vim config.json
# Edit docker-compose file leave dbmanager unchanged. Collector containers should reflect config.json:
#     container_name, specifically , must be the same as storage array name in config.json.
vim docker-compose.yml
# We are still in the ./collector subdirectory. InfluxDB and Grafana are already running. 
# Build and start collector(s) and dbmanager:
docker-compose build
docker-compose up
# Check Grafana and if OK, hit CTRL+C, restart with:
docker-compose up -d
# If not OK, CTRL+C and "docker-compose down". 
# Then review config.json and docker-compose.yml.
# collector.py and db_manager.py can be started from the CLI for easier troubleshooting without containers.
# 
# you can use the utils container to check the DB
# docker exec -it influxdb-utils-test /bin/sh
# cat README.txt # shows CLI examples
```

### Environment variables and configuration files

- `./epa/.env` has some env data used by its Makefile for InfluxDB and Grafana. Use `make` to start, stop, clean, remove, and restart these two containers
- `./collector` is simpler: use `docker-compose` to build/start/stop/remove collector and dbmanager containers and don't forget `config.json`
- When editing `./collector/docker-compose.yml`, provide the following for each E-Series array:
  - `USERNAME` - SANtricity account for monitoring such as `monitor` (read-only access to SANtricity)
  - `PASSWORD` - SANtricity password for the account used to monitor
  - `SYSNAME` - SANtricity array name, such as `R26U25-EF600` - get this from the SANtricity Web UI, but you can use your own - just keep it consistent with the name in `./collector/config.json`. If you want to make the name identical to actual E-Series array name, [this image](/images/sysname-in-santricity-manager.png) shows where to look it up
  - `SYSID` - SANtricity WWN for the array, such as 600A098000F63714000000005E79C888 - see [this image](/images/sysid-in-santricity-manager.png) on where to find it in the SANtricity Web UI.
  - `API` - SANtricity controller's IP address such as 6.6.6.6. Port number (`:8443`) is automatically set in scripts
  - `RETENTION_PERIOD` - data retention in InfluxDB, such as 52w (52 weeks)
  - `DB_ADDRESS` - external IPv4 of the InfluxDB host. If the host IP where InfluxDB is running is remote that could be something like 7.7.7.7. If dbmanager, collector and InfluxDB are on the same host then it can be 127.0.0.1; if they're in the same Kubernetes namespace then `influxdb`, etc.

Where to find the `API` value(s)? `API` address (or addresses) are IPv4 addresses (or FQDNs) used to connect to the E-Series Web management UI. You can see them in the browser when you manage an E-Series array. 

For consistency's sake it is recommended that `SYSNAME` in EPA is the same as the actual E-Series system name, but it doesn't have to be - it can consist of arbitrary alphanumeric characters (and `_` and `-`; if interested please check the Docker Compose documentation). Just make sure the array names in `./collector/docker-compose.yml` and `./collector/config.json` are identical; otherwise array metrics and events may get collected, but drop-down lists with array names in Grafana dashboards won't match so the dashboards will be empty even though the InfluxDB is not.

Example of `docker-compose.yml` with collector for one array:

```yaml
services:

  collector-R26U25-EF600:
    image: ntap-grafana-plugin/eseries_monitoring/collector:latest
    container_name: R26U25-EF600
    mem_limit: 64m
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-file: "5"
        max-size: 10m
    environment: 
      - USERNAME=monitor
      - PASSWORD=monitor123
      - SYSNAME=R26U25-EF600
      - SYSID=600A098000F63714000000005E79C888
      - API=6.6.6.6
      - RETENTION_PERIOD=26w
      - DB_ADDRESS=7.7.7.7
      - DB_PORT=8086
```

`SYSNAME` from `./collector/docker-comopose.yml` should be the same as `name` in `config.json` used by dbmanager. Here the `name` matches `environment:SYSNAME` value in `docker-compose.yml` above.

```json
{
    "storage_systems": [
        {
            "name": "R26U25-EF600"
        }
    ]
}
```

`dbmanager` doesn't do much and doesn't yet make use of `RETENTION_PERIOD` (just leave that value alone for now). Only `DB_ADDRESS` parameter need to be correct, and the name(s) in `config.json` need to match `SYSNAME` in `docker-compose.yml`.

```yaml
version: '3.6'
services:
  collector-dbmanager:
    image: ntap-grafana-plugin/eseries_monitoring/dbmanager:latest
    container_name: dbmanager
    mem_limit: 32m
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-file: "5"
        max-size: 10m
    environment: 
      - RETENTION_PERIOD=52w
      - DB_ADDRESS=6.6.6.6
      - DB_PORT=8086
```

### Adjust firewall settings for InfluxDB and Grafana ports

The original EPA v3.0.0 exposes the SANtricity WSP (8080/tcp) and Grafana (3000/tcp) to the outside world.

This fork does not use WSP. Grafana is the same (3000/tcp), but InfluxDB is now exposed externally at 8086/tcp. The idea is to be able to run several collectors in various locations (closer to E-Series, for example) and send data to a centrally managed InfluxDB.

To protect InfluxDB service open 8086/tcp to IP addresses or FQDNs where collector, dbmanager and Grafana run. If runs as one app on the same host or within Docker Compose/Kubernetes/Nomad, then no adjustments should be necessary.

### Add or remove a monitored array

To add a new SANtricity array, we don't need to do anything in the `epa` subdirectory.

- Go to `./collector`
- Edit `docker-compose.yml` - if you copy-paste, make sure you get the variables and `container_name` right!
- Edit `config.json` to add a matching record for the new array
- `docker-compose down`
- `docker-compose build`
- `docker-compose up -d`

To remove an array, remove it from `config.json` and `docker-compose.yml` and do the last three `docker-compose` steps the same way.

### Update password of a monitor account

To change the monitor account password for one particular collector, say the one used for array `R11U01-EF300`, change it on the array first, find this array in `docker-compose.yml`, change the password value in the `PASSWORD=` row for the array, run `docker-compose down R11U01-EF300` followed by `docker-compose up R11U01-EF300`.

The array name has not changed, so it wasn't necessary to edit `./collector/config.json` and rebuild `./collector/dbmanager`, and running `docker-compose build` wasn't necessary either.

## Walk-through

- Build and run InfluxDB and Grafana:

```sh
$ cd epa

$ make build 

$ docker images 
REPOSITORY                                           TAG               IMAGE ID       CREATED              SIZE
ntap-grafana-plugin/eseries_monitoring/python-base   latest            9d5f8085ab4a   51 seconds ago       50.1MB
<none>                                               <none>            510d1a737cad   52 seconds ago       12.9MB
ntap-grafana-plugin/eseries_monitoring/alpine-base   latest            85a1ebbfbc5e   54 seconds ago       7.05MB
ntap-grafana/influxdb                                3.2               4c650d02806a   55 seconds ago       173MB
ntap-grafana/ansible                                 3.2               94ee4e4a0405   About a minute ago   398MB
<none>                                               <none>            bd3051fd74a4   About a minute ago   621MB
ntap-grafana/python-base                             3.2               5216517bec73   2 minutes ago        50.1MB
<none>                                               <none>            e9b76094f71d   2 minutes ago        12MB

$ make run    # runs: docker-compose up -d in the epa directory

$ # expect to see two containers listening on external ports - InfluxDB and Grafana

$ docker ps -a | grep '0.0.0.0'
95dd8ec86b82   ntap-grafana/grafana:3.0    0.0.0.0:3000->3000/tcp, :::3000->3000/tcp   grafana
f00b858c0728   ntap-grafana/influxdb:3.0   0.0.0.0:8086->8086/tcp, :::8086->8086/tcp   influxdb
```

- Login to Grafana with admin/admin, change admin password and optionally disable anonymous read-only access. At this point you're not supposed to see anything in the EPA dashboards

- Go to top-level `collector` directory to build Collector-related containers

```sh
$ pwd
/home/sean/eseries-perf-analyzer/collector

$ # edit docker-compose.yml and config.json

$ cat docker-compose.yml | grep name
    container_name: dbmanager
    container_name: R26U25-EF600
    container_name: R24U04-E2824

$ # ensure container names in docker-compose.yml and system names in config.json are consistent

$ cat config.json
{
    "storage_systems": [
        {
            "name": "R26U25-EF600"
        },
        {
            "name": "R24U04-E2824"
        }
    ]
}

$ docker-compose build
```

- This `build` operation builds two containers, collector & dbmanager
- There should be two new container images (collector & dbmanager) used by two or more containers (here three, because there's one dbmanager and two arrays)

```sh
$ docker ps -a | grep monitoring
CONTAINER ID   IMAGE                                               NAMES
9d725fa1a756   ntap-grafana-plugin/eseries_monitoring/collector    R24U04-E2824
1048f321d631   ntap-grafana-plugin/eseries_monitoring/collector    R26U25-EF600
61d3cb5e83bc   ntap-grafana-plugin/eseries_monitoring/dbmanager    dbmanager
```

- Stop and remove any existing collectors and dbmanager. Start new (or updated) containers:

```sh
$ pwd
/home/sean/eseries-perf-analyzer/collector

$ # MIND the location! Don't do this in /home/sean/eseries-perf-analyzer/epa and wipe your Grafana and InfluxDB.

$ docker-compose down && docker-compose up
```

### Using public Docker images

Remember to edit Docker image location if you want to use local images or images from local registry. You may also use public images such as: 

- docker.io/scaleoutsean/epa-dbmanager:v3.2.0
- docker.io/scaleoutsean/epa-collector:v3.2.0

If the version you're looking for is not available, please build your own images.

## Sample Grafana screenshots

This fork's dashboards are identical to upstream v3.0.0, but upstream repository has no screenshots - in fact they're hard to find on the Internet - so a sample of each dashboard is provided below.

New metrics gathered by this EPA fork have *not* been added to the dashboards.

- System view

![E-Series System](/images/sample-screenshot-epa-collector-system.png)

- Array interfaces

![E-Series Array Interfaces.png](/images/sample-screenshot-epa-collector-interfaces.png)

This screenshot shows *aggregate* values for all arrays (useful in HPC environments where workloads span across multiple arrays). Further below there are other charts with individual metrics.

- Physical disks

![E-Series Physical Disks.png](/images/sample-screenshot-epa-collector-disks.png)

- Physical disks - SSD wear level (%)

![E-Series SSD Wear Level](/images/sample-screenshot-epa-collector-disks-ssd-wear-level.png)

This is the second example for the same subsystem (physical disks) and it's highlighted because this data is collected by collector, but not shown in dashboards. In order to collect this data, an E-Series array with a recent SANtricity OS (11.74, for example) and at least one SSD is required. Visualization can then be done by duplicating one of the existing disk charts and modifying it to show "percentEnduranceUsed" values. This screenshot shows that SSD wear level metrics are collected from just one of two arrays.

- Logical volumes

![E-Series Volumes.png](/images/sample-screenshot-epa-collector-volumes.png)

- Environmental indicators - total power consumption (W) and temperature (C)

![E-Series Power and Temperature](/images/sample-screenshot-epa-collector-environmental.png)

Like SSD wear level, these metrics are collected since v3.3.0, but you need to create new panels if you want to visualize them in Grafana. See the FAQs for query examples.

## FAQs

Find them [here](FAQ.md) or check [Discussions](https://github.com/scaleoutsean/eseries-perf-analyzer/discussions) for questions that aren't in the FAQ document.

## Changelog

- 3.4.0 (Auguust 21, 2025)
  - Docker chores: change 'docker-compose' to 'docker compose' in several scripts, update Dockerfile syntax
  - Add 'utils' container with InfluxDB v1 client for easier management of InfluxDB
  - Update version tag for InfluxDB container image to 1.11.8
  - Minor improvements to epa/Makefile and epa/.env to avoid build errors when .env not sourced

- 3.3.1 (June 1, 2024):
  - Dependency update (requests library)

- 3.3.0 (April 15, 2024):
  - collector now collects *controller shelf*'s total power consumption metric (sum of PSUs' consumption) and temperature sensors' values 
  - Security-related updates of various components

- 3.2.0 (Jan 30, 2023):
  - No new features vs. v3.1.0
  - No changes to Grafana container, Grafana charts, and InfluxDB container
  - collector and dbmanager are now completely independent of containers built by InfluxDB and Grafana Makefile 
  - New Kubernetes folder with Kubernetes-related instructions and sample YAML files
  - collector and dbmanager can work on both AMD64 and ARM64 systems

- 3.1.0 (Jan 12, 2023):
  - No changes to Grafana dashboards
  - Updated Grafana v8 (8.5.15), Python Alpine image (3.10-alpine3.17) and certifi (2022.12.7)
  - Remove SANtricity Web Services Proxy (WSP) and remove WSP-related code from collector 
  - Make InfluxDB listen on public (external) IP address, so that collectors from remote locations can send data in
  - Add the ability to alternate between two E-Series controllers to collector (in upstream v3.0.0 the now-removed WSP would do that)
  - Add collection of SSD wear level for flash media (panel(s) haven't been added, it's up to the user to add them if they need 'em)
  - Expand the number of required arguments in `collector.py` to avoid unintentional mistakes
  - Collector can run in Kubernetes and Nomad
  - Add dbmanager container for the purpose of uploading array configuration to InfluxDB (and potentially other DB-related tasks down the road)
  - Add simple Makefile for collector containers (collector itself, and dbmanager)
  - Old unit tests are no longer maintained
