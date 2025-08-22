# NetApp E-Series Performance Analyzer ("EPA")

- [NetApp E-Series Performance Analyzer ("EPA")](#netapp-e-series-performance-analyzer-epa)
  - [What is this thing](#what-is-this-thing)
  - [What E-Series metrics does EPA collect](#what-e-series-metrics-does-epa-collect)
  - [Requirements](#requirements)
  - [Quick start](#quick-start)
    - [CLI users](#cli-users)
    - [Docker Compose users:](#docker-compose-users)
    - [Environment variables and configuration files](#environment-variables-and-configuration-files)
    - [Adjust firewall settings for InfluxDB and Grafana ports](#adjust-firewall-settings-for-influxdb-and-grafana-ports)
    - [Add or remove a monitored array](#add-or-remove-a-monitored-array)
    - [Update password of a monitor account](#update-password-of-a-monitor-account)
    - [Grafana dashboards](#grafana-dashboards)
  - [Sample Grafana screenshots](#sample-grafana-screenshots)
  - [FAQs](#faqs)
  - [Changelog](#changelog)


## What is this thing

This is a friendly fork of [E-Series Performance Analyzer aka EPA](https://github.com/NetApp/eseries-perf-analyzer) v3.0.0 (see its README.md for additional information) created with the following objectives:

- Disentangle E-Series Collector from the rest of EPA and make it easy to run it anywhere (shell, Docker/Docker Compose, Kubernetes, Nomad)
- Remove SANtricity Web Services Proxy (WSP) dependency from Collector and remove WSP from EPA, so that one collector container or script captures data for one and only one E-Series array

In terms of services, collectors collects metrics from E-Series and sends them to InfluxDB.

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

- NetApp SANtricity OS: >= 11.80 recommended, older releases are not tested
- CLI: collector should work on any Linux with recent Python 3.10 or similar

## Quick start

### CLI users

```bash
git clone https://github.com/scaleoutsean/eseries-perf-analyzer/
cd eseries-perf-analyzer/epa/collector
pip install -r requirements.txt
python3 ./collector.py -h
```

Note that you can't do much with just the CLI - you need a DB where data can be sent. But you can test the CLI with `-n` which collects data but doesn't send to InfluxDB. Try `collector.py -n -i -b  --sysid WWN --sysname ARRAY_NAME` or similar.

### Docker Compose users:

Download and decompress latest release and enter the `epa` sub-directory:

```sh
git clone https://github.com/scaleoutsean/eseries-perf-analyzer/
cd eseries-perf-analyzer/epa
vim .env
vim docker-compose.yaml
docker-compose build
````

Now that the containers have been built, three steps remain:
- Start `influxdb`
- Create a database (or several) for EPA Collector
- Start `grafana`
- Create Grafana Data Source and attempt to import dashboards

InfluxDB first:

```bash
docker compose up -d influxdb
docker comopse logs influxdb

docker compose up -d utils
docker compose ps 
```

Now we have InfluxDB and the `utils` container running. Before we start EPA Collector, we should have a database instance to be able to insert data to InfluxDB.

We create one from the `utils` container. 

```bash
# enter the container
docker exec -u 0 -it utils /bin/sh
# Inside of the utils container
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'SHOW DATABASES'
# Create database (or several). EPA defaults to "eseries"
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'CREATE DATABASE eseries'
# Show again. 
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'SHOW DATABASES'
# If OK, exit
exit
```

Proceed with Grafana, `grafana-init` and finally start EPA Collector.

```bash
docker compose up -d grafana
docker compose logs grafana

docker compose up grafana-init

docker compose up -d collector
docker compose logs collector
```


Kubernetes users should skim through this page to get the idea how EPA works, and then follow [Kubernetes README](kubernetes/README.md).

### Environment variables and configuration files

`./epa/.env` has some environment variables used by ./epa/docker-compose.yaml. You may want to edit `TAG` if you make own versions.
Collector arguments and switches
- `USERNAME` - SANtricity account for collecting API metrics such as `monitor` (read-only access to SANtricity - create it in SANtricity)
- `PASSWORD` - SANtricity password for the collector account
- `SYSNAME` - SANtricity array name, such as `R26U25-EF600`. Get this from the SANtricity Web UI, but you can use your own. If you want to make the name identical to actual E-Series array name, [this mage](/images/sysname-in-santricity-manager.png) shows where to look it up
- `SYSID` - SANtricity WWN for the array, such as `600A098000F63714000000005E79C888`. See [this image](/images/sysid-in-santricity-manager.png) on where to find it in the SANtricity Web UI.
- `API` - SANtricity controller's IP address such as 6.6.6.6. Port number (`:8443`) is automatically set in Collector, and `https://` is not necessary either.
- `RETENTION_PERIOD` - data retention in InfluxDB, such as 52w (52 weeks)
- `DB_ADDRESS`
  - Use external IPv4 or FQDN of the InfluxDB host if InfluxDB is running in a different location
  - Use Docker's internal DNS name (`influxdb`) if InfluxDB is in the same Docker Compose as the Collector

Example of `docker-compose.yml` with a collector for one array:

```yaml
services:

  collector-R26U25-EF600:
    image: epa/collector:${TAG}
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

### Adjust firewall settings for InfluxDB and Grafana ports

The original EPA v3.0.0 exposes the SANtricity WSP (8080/tcp) and Grafana (3000/tcp) to the outside world.

This fork does not use WSP. 

Grafana is the same (exposed at 3000/tcp), and InfluxDB is exposed externally at 8086/tcp. The idea is to be able to run several collectors in various locations (closer to E-Series, for example) and send data to a centrally managed InfluxDB. If you want to remove external access from the InfluxDB container, remove `8086:8086` and the `ports` line above it in epa/docker-compose.yaml and restart the container.

### Add or remove a monitored array

Add another collector service (e.g. `collector-ef300c`) to `docker-compose.yaml`, build it and start it. You may use the same (existing) or own (new) InfluxDB database instance. Enter the `utils` container to create it. 

To remove a collector that monitors an array, run `docker compose down <collector-name>`, enter the `utils` container to drop the database (if not shared with other collectors).

### Update password of a monitor account

To update the monitor account's password, simply change it in `./epa/docker-compose.yaml`, stop and then start the collector.

### Grafana dashboards

As you clone the repo, they are in `epa/grafana-init/dashboards`. 

You can import them to your own Grafana instance. If you use the included `./epa/docker-compose.yaml`, the dashboards may/should be deployed by the `grafana-init` container automatically.

## Sample Grafana screenshots

Power (PSU) metrics are collected and stored in InfluxDB, but no dashboard has a panel with it. You may add it yourself.

- System view

![E-Series System](/images/sample-screenshot-epa-collector-system.png)

- Array interfaces

![E-Series Array Interfaces.png](/images/sample-screenshot-epa-collector-interfaces.png)

This screenshot shows *aggregate* values for all arrays (useful in HPC environments where workloads span across multiple arrays). Further below there are other charts with individual metrics.

- Physical disks

![E-Series Physical Disks.png](/images/sample-screenshot-epa-collector-disks.png)

- Physical disks - SSD wear level (%)

![E-Series SSD Wear Level](/images/sample-screenshot-epa-collector-disks-ssd-wear-level.png)

In order to collect this data, an E-Series array with a recent SANtricity OS (> 11.80, for example) and at least one SSD is required. Note that before v3.4.0, EPA collector used to fetch `percentEnduranceUsed` but now it fetches `spareBlocksRemainingPercent` because this one I've actually seen drop below 100% while the former one showed suspicious results in the samples I've seen.

- Logical volumes

![E-Series Volumes.png](/images/sample-screenshot-epa-collector-volumes.png)

- Environmental indicators - total power consumption (W) and temperature (C)

![E-Series Power and Temperature](/images/sample-screenshot-epa-collector-environmental.png)

Like SSD wear level, these metrics are collected since v3.3.0, but you need to create new panels if you want to visualize them in Grafana. See the FAQs for query examples.

## FAQs

Find them [here](FAQ.md) or check [Discussions](https://github.com/scaleoutsean/eseries-perf-analyzer/discussions) for questions that aren't in the FAQ document.

## Changelog

- 3.4.0 (Auguust 22, 2025)
  - Add 'utils' container with InfluxDB v1 client for easy management of InfluxDB
  - Remove `dbmanager` container and its JSON configuration file (one less container to worry about)
  - Minor update of version tags for various images (InfluxDB, Python, Alpine)
  - Docker Compose with InfluxDB 1.11.8 necessitates `user` key addition and change to InfluxDB volume ownership
  - Minor update of version tag for Python and Alpine in Collector
  - Complete removal of the pre-fork bloat (epa/Makefile, epa/ansible epa/blackduck and the rest of it)
  - Merge two docker-compose.yaml files into one (epa/docker-compose.yaml)
  - Add `grafana-init` container to replace what epa/ansible used to do in a more complicated way
  - Remove "internal images" build feature - builds are much faster and easier to maintain
  - Small error handling improvements in EPA Collector noted in Issues
  - Multiple fixes related to built-in dashboards (Grafana data source set to `EPA`, `WSP` has been removed, dashboards can be imported without issues) 

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
