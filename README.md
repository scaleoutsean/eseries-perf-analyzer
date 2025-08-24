# NetApp E-Series Performance Analyzer ("EPA")

- [NetApp E-Series Performance Analyzer ("EPA")](#netapp-e-series-performance-analyzer-epa)
  - [What is EPA](#what-is-epa)
  - [What E-Series metrics does EPA collect](#what-e-series-metrics-does-epa-collect)
  - [Requirements](#requirements)
  - [Quick start](#quick-start)
    - [CLI and systemd users](#cli-and-systemd-users)
    - [Docker Compose users](#docker-compose-users)
      - [Environment variables and configuration files](#environment-variables-and-configuration-files)
      - [Deploy](#deploy)
    - [Kubernetes](#kubernetes)
  - [Other procedures](#other-procedures)
    - [Execute containerized collector.py](#execute-containerized-collectorpy)
    - [Adjust firewall settings for InfluxDB and Grafana ports](#adjust-firewall-settings-for-influxdb-and-grafana-ports)
    - [Add or remove a monitored array](#add-or-remove-a-monitored-array)
    - [Update password of monitor account](#update-password-of-monitor-account)
    - [Grafana dashboards](#grafana-dashboards)
  - [FAQs](#faqs)
  - [Changelog](#changelog)


## What is EPA

This is a fork of the now-archived [E-Series Performance Analyzer](https://github.com/NetApp/eseries-perf-analyzer) v3.0.0. This fork's objectives:

- Continue development of an OSS monitoring solution for NetApp E-Series
- Disentangle E-Series Collector from the rest of EPA stac and make it easy to run it stand-alone and anywhere
- Remove SANtricity Web Services Proxy (WSP) dependency from Collector and remove WSP from EPA, so that one collector container or script captures data for one and only one E-Series array

EPA Collector collects metrics from E-Series and sends them to InfluxDB. 
Each collector uses own credentials and can (but doesn't have to) write data to the same InfluxDB database instance.

## What E-Series metrics does EPA collect

- System
- Volumes
- Disks
- Interfaces
- E-Series MEL events
- Environmental (temperature and power consumption)

Sample screenshots are available [here](./SCREENSHOTS.md).

## Requirements

- NetApp SANtricity OS: >= 11.80 recommended, older releases are not tested
- EPA Collector should work on any Linux with recent Python 3.10 or similar - you may run it as a script, systemd service, Docker/Podman/Nomad/K8s container, etc.
- The rest of EPA "stack" is standard OSS integrated in a stack for reference purposes. Users are encouraged to use own database and Grafana

## Quick start

### CLI and systemd users

```bash
git clone https://github.com/scaleoutsean/eseries-perf-analyzer/
cd eseries-perf-analyzer/epa/collector
# create and activate a venv if you want
pip install -r requirements.txt
python3 ./collector.py -h
```

Note that you can't do much with just the CLI - you need a DB where data can be sent. What you can do next?

- If SANtricity is reachable: try collection with `-n` switch: collect data but don't write to InfluxDB. Try `collector.py -n -i -b  --sysid WWN --sysname ARRAY_NAME -u monitor -p p@ss` or similar.
- If InfluxDB is reachable: create database first with `--createDB --dbName eseries`. Example: `python3 epa/collector/collector.py --createDb --dbName mydb --dbAddress influxdb:8086` (or `hostname:8086` if executing outside of Docker when eternal InfluxDB port is exposed)

### Docker Compose users

#### Environment variables and configuration files

Environment variables:

- `./epa/.env` has environment variables used by `./epa/docker-compose.yaml`. You may want to edit `TAG` if you make own versions or container version upgrades.
- Some can be found in the Docker Compose file itself

Collector arguments and switches:

- `USERNAME` - SANtricity account for collecting API metrics such as `monitor` (read-only access to SANtricity - create it in SANtricity)
- `PASSWORD` - SANtricity password for the collector account
- `SYSNAME` - SANtricity array name, such as `R26U25-EF600`. Get this from the SANtricity Web UI, but you can use your own. If you want to make the name identical to actual E-Series array name, [this mage](/images/sysname-in-santricity-manager.png) shows where to look it up
- `SYSID` - SANtricity WWN for the array, such as `600A098000F63714000000005E79C888`. See [this image](/images/sysid-in-santricity-manager.png) on where to find it in the SANtricity Web UI.
- `API` - SANtricity controller's IP address such as 6.6.6.6. Port number (`:8443`) is automatically set in Collector, and `https://` is not necessary either.
- `RETENTION_PERIOD` - data retention in InfluxDB, such as 52w (52 weeks)
- `DB_ADDRESS`
  - Use external IPv4 or FQDN of the InfluxDB host if InfluxDB is running in a different location
  - Use Docker's internal DNS name (`influxdb`) if InfluxDB is in the same Docker Compose as the Collector
- `DB_NAME` - database name, can be one per E-Series system, for Collector to use. Default (if not set): `eseries`. Collector creates database if it doesn't exist.
- `DB_PORT` - 8086 is the standard port for InfluxDB v1

Example of a collector service entry in`docker-compose.yml`:

```yaml
services:

  collector-R26U25-EF600:
    image: epa/collector:${TAG}
    # image: docker.io/scaleoutsean/epa-collector:3.4.0 # it exists, but best build your own
    container_name: R26U25-EF600
    mem_limit: 256m
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
      - DB_ADDRESS=7.7.7.7  # influxdb instead of IPv4 when running in same Compose or K8s namespace
      - DB_PORT=8086
      # Optional: Override default database name (eseries) on a per-collector basis
      # - DB_NAME=eseries
      # Optional: Create database and exit (true/1 = enable); remember to revert to 'false' after successful run
      # - CREATE_DB=false      
```

Note that, if you create multiple collectors in the same docker-compose.yaml, only *one* of `DB_NAME` (as each collector may have it different) will be applied in Grafana Data Source configuration. If you're in this situation simply configure just one `DB_NAME` first (you don't have to do anything if you don't mind to have the first DB instance named `eseries`) and then use InfluxDB CLI or the related instructions from the FAQs (on how to do it from collector.py) to create another DB and another InfluxDB Data Source to Grafana. Then you can start all Collector containers. 

You can also create additional database instances in InfluxDB from the CLI (instructions above), but you won't be able to if you modify Docker Compose to not expose InfluxDB externally. That's why it's easier to use the approach that runs collector.py in Docker - that will work for either Compose-internal or external InfluxDB.

#### Deploy

**NOTE:** EPA v3.4.0 uses "named" Docker volumes for both Grafana and InfluxDB since they both require a non-root user and Docker's "named" volumes make that easier. If you are concerned about disk space for InfluxDB (/var/lib/docker/...), you can change InfluxDB container's volumes in `./epa/docker-compose.yaml` to a sub-directory before you deploy.

Download and decompress latest release and enter the `epa` sub-directory:

```sh
git clone https://github.com/scaleoutsean/eseries-perf-analyzer/
cd eseries-perf-analyzer/epa
vim .env                 # you probably don't need to change anything here
vim docker-compose.yaml  # see collector service sample above; you may use 'DB_NAME' to set a different DB name for each collector

# one shot Hail Mary: docker compose -d up # includes 'utils' container
# or, step by step:

docker compose build

docker compose up -d influxdb
docker compose logs influxdb

docker compose up -d grafana
docker compose logs grafana

docker compose up grafana-init

docker compose up -d collector
docker compose logs collector

# not required, best to start it on-demand
# docker compose up -d utils

```

If you have any problems with Grafana Data Source, add InfluxDB v1 data source `EPA` (use `http://{DB_ADDRESS}:{DB_PORT}` and your DB name). If you have problems with dashboards, import them from `./epa/grafana-init/dashboards/`.

### Kubernetes

Kubernetes users should skim through this page to get the idea how EPA works, and then follow [Kubernetes README](kubernetes/README.md).

## Other procedures

### Execute containerized collector.py 

If you want to run containerized collector as CLI program rather than service, try this and add correct parameters from `docker-compose.yaml`. 

Mind the project/container name and version!

```sh
docker run --rm --network eseries_perf_analyzer \
  --entrypoint python3 \
  epa/collector:3.4.0 collector.py -h
# or, if you just want to view help
# docker run --rm epa/collector:3.4.0 -h
```

### Adjust firewall settings for InfluxDB and Grafana ports

Grafana is exposed over HTTP (3000/tcp) as per usual Grafana defaults (and credentials).

InfluxDB is accessible to external clients at 8086/tcp. The idea is to be able to run several collectors in various locations (closer to E-Series, for example) and send data to a centrally managed InfluxDB. If you want to remove external access from the InfluxDB container, remove `- 8086:8086` and the line with `ports` above it in `./epa/docker-compose.yaml` and restart the container.

### Add or remove a monitored array

Add another collector service (e.g. `collector-ef300c`) to `docker-compose.yaml`, build it and start it. You may use the same (existing) or own (new) InfluxDB database instance. Enter the `utils` container or use Collector to create it in advance. You may also just run collector with `--dbName` to have it created automatically.

To remove a collector that monitors an array, run `docker compose down <collector-name>`, enter the `utils` container to drop the database - if it's not shared with other collectors.

### Update password of monitor account

To update a monitor account's password, simply change it in `./epa/docker-compose.yaml`, stop and then start the collector.

```sh
# in ./epa directory
docker compose stop collector_ef600_01
vim docker-compose.yaml
docker compose start collector_ef600_01
```

### Grafana dashboards

As you clone the repository and enter it, they are in `./epa/grafana-init/dashboards`. 

You can import them to your own Grafana instance. If you use the included `./epa/docker-compose.yaml`, the dashboards may/should be deployed by the `grafana-init` container automatically.

## FAQs

Find them [here](./FAQ.md) or check [Discussions](https://github.com/scaleoutsean/eseries-perf-analyzer/discussions) for questions that aren't in the FAQ document.

## Changelog

- 3.4.0 (August 24, 2025)
  - Remove `dbmanager` container and its JSON configuration file (one less container to worry about)
  - Add "create database" feature to Collector to replace dbmanager
  - Minor update of version tags for various images (InfluxDB, Python, Alpine)
  - Docker Compose with InfluxDB 1.11.8 necessitates `user` key addition and change to InfluxDB volume ownership
  - Complete removal of the pre-fork bloat (epa/Makefile, epa/ansible epa/blackduck and the rest of it)
  - Merge two docker-compose.yaml files into one (`epa/docker-compose.yaml`)
  - Add `grafana-init` container to replace what epa/ansible used to do in a more complicated way
  - Add `utils` container with InfluxDB v1 client for easy management of InfluxDB  
  - Remove "internal images" build feature that epa/Makefile was using - builds are now much faster and easier to maintain
  - Small error handling improvements in EPA Collector noted in Issues
  - Add checks and fixes for handling inconsistent API responses from SANtricity API that may have caused dropped inserts in InfluxDB in some situations
  - Multiple fixes related to built-in dashboards (Grafana data source set to `EPA`, `WSP` has been removed, dashboards can be imported without issues) 
  - Dashboards are now imported to "EPA" folder. Find them in Grafana with Dashboards > Browse
  - Remove direct import of `urllib3` and lets `requests` deal with it (and requests now defaults to v2.5.0). Prior versions of EPA use `urllib3` v1 which has minor vulnerability that doesn't impact EPA which connects to trusted SANtricity API endpoint over trusted network
  - See upgrade-related Q&A in the [FAQs](./FAQ.md). There are no new features and apart from the weak `urllib3` vulnerability there's no reason to install this if your EPA < 3.4.0 is running fine

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
