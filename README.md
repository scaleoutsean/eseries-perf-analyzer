# NetApp E-Series Performance Analyzer ("EPA")

- [NetApp E-Series Performance Analyzer ("EPA")](#netapp-e-series-performance-analyzer-epa)
  - [What is EPA](#what-is-epa)
    - [Should you use EPA, ESC or NetApp Harvest?](#should-you-use-epa-esc-or-netapp-harvest)
  - [Collected data](#collected-data)
  - [Requirements](#requirements)
  - [Quick start](#quick-start)
    - [CLI and systemd users](#cli-and-systemd-users)
    - [Docker Compose users](#docker-compose-users)
      - [Environment variables and configuration files](#environment-variables-and-configuration-files)
      - [Deploy](#deploy)
    - [Kubernetes](#kubernetes)
  - [Other procedures](#other-procedures)
    - [Execute containerized `collector.py` from CLI](#execute-containerized-collectorpy-from-cli)
    - [Adjust firewall settings for InfluxDB and Grafana ports](#adjust-firewall-settings-for-influxdb-and-grafana-ports)
    - [Add or remove a monitored array](#add-or-remove-a-monitored-array)
    - [Update password of monitor account](#update-password-of-monitor-account)
    - [Grafana dashboards](#grafana-dashboards)
    - [Prometheus metrics freshness](#prometheus-metrics-freshness)
  - [FAQs](#faqs)
  - [Changelog](#changelog)

## What is EPA

EPA 3 is fork of the now-archived [E-Series Performance Analyzer](https://github.com/NetApp/eseries-perf-analyzer) v3.0.0. This fork's objectives:

- Continue development of an open monitoring solution for NetApp E-Series
- Disentangle E-Series Collector from the rest of EPA stack and make it easy to run it stand-alone, anywhere
- Remove SANtricity Web Services Proxy (WSP) dependency from Collector and remove WSP from EPA, so that one collector container or script captures data for one and only one E-Series array

EPA Collector collects metrics from E-Series and sends them to InfluxDB.

Each collector uses own credentials and may (but doesn't have to) write data to the same InfluxDB database or database instance.

### Should you use EPA, ESC or NetApp Harvest?

[E-Series SANtricity Collector aka ESC](https://github.com/scaleoutsean/eseries-santricity-collector) is what I planned to release as EPA 4, but now has its own repository. Its focus on gathering configuration details makes it more complex and sensitive to hardware and software differences between different E-Series systems, which is one of the reasons why it has its own home. If you have more than one E-Series system to manage and some developer skills, ESC may be a good choice for you.

You can use all three at the same time, any of them, or none.

- Harvest may be the best choice for users with ONTAP or StorageGRID systems. It's "good enough" for generic use with E-Series, especially if you already deploy it for other NetApp storage or want dashboards included.
- EPA is simpler to use, lighter on resources, and more flexible (can run from shell, requires no build process or containers, features can be added or changed without waiting for next scheduled Harvest release).
- ESC is more focused on E-Series and (in my opinion) more suitable for E-Series power users. It likely gathers more E-Series configuration data than Harvest and MCP-related features were included via MCP in InfluxDB UI before Harvest had them.

## Collected data

- Performance metrics
  - System
  - Volumes
  - Disks
  - Interfaces
  - SSD Flash Cache (on hybrid E-Series with SSD Cache enabled)
- Log and environment
  - E-Series MEL events
  - Failures
  - Temperature sensors
  - Power supply unit consumption
- Configuration
  - Volumes
  - Disks
  - Hosts
  - Disk groupings (RAID or DDP)

Users may use `--include` (space-delimited metrics) to limit the type of data collected and constrain InfluxDB data growth. Only Performance metrics and failures may be exported via Prometheus.

Sample screenshots are available [here](./SCREENSHOTS.md).

## Requirements

- NetApp SANtricity OS: >= 11.90R5 and <=12.00 recommended. Older releases may work (for the most part), but are not tested and bugs exclusive to releases years old won't be fixed
- EPA Collector should work on any Linux with recent Python 3.12 or newer - you may run it as a script, systemd service, Docker/Podman/Nomad/K8s container, etc.
- The rest of EPA "stack" is standard OSS integrated in a stack for reference purposes. Users are encouraged to use own database and Grafana (instance and dashboards)

## Quick start

**NOTE:** `master` branch may be ahead of Releases. You may download and decompress a recent release from [Releases](https://github.com/scaleoutsean/eseries-perf-analyzer/releases) instead.

### CLI and systemd users

Pick a version, clone and use it.

```bash
TAG="v3.5.5"
git clone --depth 1 --branch ${TAG} https://github.com/scaleoutsean/eseries-perf-analyzer/
cd eseries-perf-analyzer/epa/collector
# create and activate a venv if you want
pip install -r requirements.txt
python3 ./collector.py -h
```

Note that you can't do much with just the CLI - you need a DB where data can be sent. What can we do next?

- If SANtricity is reachable: try collection with `-n` switch: collect data but don't write to InfluxDB. Example:
  ```sh
  ./collector.py -n -i -b  --sysid WWN --sysname ARRAY_NAME -u monitor -p p@ss
  ```
- Gather volume and Flash Cache metrics and expose only via Prometheus (InfluxDB is not used), save responses to `/tmp/`:
  ```sh
   PASS="fakePass"
  ./collector.py -n --api 1.2.3.4 --sysname e4012 --username monitor --password ${PASS} --output prometheus --sysid 6d039ea0009317330000000066f433d1 --max-iterations 3 --capture /tmp/ --showStorageNames --showFlashCache --include flashcache volumes
  ```

### Docker Compose users

#### Environment variables and configuration files

Environment variables:

- `./epa/.env` has environment variables used by `./epa/docker-compose.yaml`. You may want to edit `TAG` if you make own versions or container version upgrades.
- Some important variables are in the Docker Compose file itself

Collector arguments and switches:

- `USERNAME` - SANtricity account for collecting API metrics such as `monitor` (read-only access to SANtricity - create it in SANtricity)
- `PASSWORD` - SANtricity password for the collector account
- `SYSNAME` - SANtricity array name, such as `R26U25-EF600`. Get this from the SANtricity Web UI, but you can use your own. If you want to make the name identical to actual E-Series array name, [this mage](/images/sysname-in-santricity-manager.png) shows where to look it up
- `SYSID` - SANtricity WWN for the array, such as `600A098000F63714000000005E79C888`. See [this image](/images/sysid-in-santricity-manager.png) on where to find it in the SANtricity Web UI
- `API` - SANtricity controller's IP address such as 6.6.6.6. Do not include `https://`
- `API_PORT` - SANtricity port number is automatically set to default (`8443`) if not specified
- `RETENTION_PERIOD` - data retention in InfluxDB, such as 52w (52 weeks)
- `DB_ADDRESS`
  - Use external IPv4 or FQDN of the InfluxDB host if InfluxDB is running in a different location
  - Use Docker's internal DNS name (`influxdb`) if InfluxDB is in same Docker Compose as Collector
- `DB_NAME` - database name, can be one per E-Series system, for Collector to use. Default (if not set): `eseries`. Collector creates database if it doesn't exist
- `DB_PORT` - `8086` is the default port for InfluxDB v1 used by Collector if not specified
- `OUTPUT` - send to `influxdb`, `prometheus`, or (default) `both`
- `TLS_VERIFY` - verifies SANtricity API server's TLS certificate; `true` is recommended, but won't work if container can't verify; it will work from CLI/bare metal if OS truststore has the CA TLS
- `PROMETHEUS_PORT` - used if `OUTPUT` isn't `influxdb` and default is 8080. Make sure Collector exposes with with open external port if you need to access it externally

Example of a collector service entry in`docker-compose.yml`:

```yaml
services:

  collector-EF600:
    image: epa/collector:${TAG}
    # image: docker.io/scaleoutsean/epa-collector:3.5.5 # it exists, but best build your own
    container_name: collector-EF600
    mem_limit: 256m
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-file: "5"
        max-size: 10m
    # ports:
      # - 8080:8080         # open only if you need Prometheus and OUTPUT is set to either "both" or "prometheus"
      # - 8081:8080         # second collector in the same Docker Compose 
    environment: 
      - USERNAME=monitor
      - PASSWORD=monitor123
      - SYSNAME=R26U25-EF600
      - SYSID=600A098000F63714000000005E79C888
      - API=5.5.5.5 6.6.6.6 # it's OK to set only one
      - RETENTION_PERIOD=8w
      - DB_ADDRESS=7.7.7.7  # use 'influxdb' instead of IPv4/FQDN when running in same Compose or K8s namespace
      - DB_PORT=8086
      - TLS_VERIFY=false # true is recommended
      # Optional: Override default database name (eseries) on a per-collector basis
      # - DB_NAME=eseries
      # Optional: Create database and exit (true/1 = enable); remember to revert to 'false' after successful run
      # - CREATE_DB=false
      # Optional: Set output destination (both|influxdb|prometheus). Default: both
      - OUTPUT=influxdb
      # Optional: Set Prometheus port (default: 8080)
      - PROMETHEUS_PORT=8080
```

Note that, if you create multiple collectors in the same docker-compose.yaml, only *one* of `DB_NAME` (as each collector may have it different) will be applied in Grafana Data Source configuration. If you're in this situation simply configure just one `DB_NAME` first (you don't have to do anything if you don't mind to have the first DB instance named `eseries`) and then use InfluxDB CLI or the related instructions from the FAQs (on how to do it from `collector.py`) to create another DB and another InfluxDB Data Source to Grafana. Then you can start all Collector containers.

You can also create additional database instances in InfluxDB from the CLI (instructions above), but you won't be able to if you modify Docker Compose to not expose InfluxDB externally. That's why it's easier to use the approach that runs `collector.py` in Docker - that will work for either Compose-internal or external InfluxDB.

#### Deploy

**NOTE:** EPA v3.4.0 uses "named" Docker volumes for both Grafana and InfluxDB since they both require a non-root user and Docker's "named" volumes were supposed to make that easier. But it wasn't easier. It was worse. v3.5.0 reverts to bind-style in the `./epa` directory. You may edit your volume configuration any way you want in `./epa/docker-compose.yaml`.

Download and decompress latest release and enter the `epa` sub-directory:

```sh
TAG="v3.5.5"
git clone --depth 1 --branch ${TAG} https://github.com/scaleoutsean/eseries-perf-analyzer/
cd eseries-perf-analyzer/epa
vim .env                 # you probably don't need to change anything here unless you prefer .env over docker-compose.yml
vim docker-compose.yml  # see collector service sample above; you may use 'DB_NAME' to set a different DB name
./setup-data-dirs.sh     # (in epa subdirectory) creates directories for InfluxDB and Grafana and applies correct ownership

# fast
# docker compose -d up # includes 'utils' container, but not Grafana dashboards
# or, slower, step by step:

docker compose build

docker compose up -d influxdb
docker compose logs influxdb

docker compose up -d grafana
docker compose logs grafana

docker compose up -d collector
docker compose logs collector

# not required, but if you won't build own dashboards, you may deploy the pre-made ones
# docker compose --profile init up grafana-init
# sample dashboards can also be imported from disk in Grafana UI (see the FAQs)

# not required, best to start it on-demand when you need it; see README.txt inside container
# docker compose up -d utils

```

If you have any problems with Grafana Data Source, add InfluxDB v1 data source `EPA` (use `http://{DB_ADDRESS}:{DB_PORT}` and your DB name). If you have problems with dashboards, import them from `./epa/grafana-init/dashboards/` (see below).

### Kubernetes

Kubernetes users should skim through this page to get the idea how EPA works, and then follow the [Kubernetes README](kubernetes/README.md).

## Other procedures

### Execute containerized `collector.py` from CLI

If you want to run containerized collector as a CLI program rather than Docker service, try this and add correct parameters from `docker-compose.yaml`.

Mind the project/container name and version!

```sh
DOCKER_TAG="3.5.5"
docker run --rm --network eseries_perf_analyzer \
  --entrypoint python3 \
  epa/collector:${DOCKER_TAG} collector.py -h
# or, if you just want to view help
# docker run --rm epa/collector:${DOCKER_TAG} -h
```

Example run for limited database population:

```sh
DOCKER_TAG="3.5.5"
docker run -e INCLUDE="power temp" epa/collector:${DOCKER_TAG}
```

### Adjust firewall settings for InfluxDB and Grafana ports

Grafana is exposed over HTTP (3000/tcp) as per usual Grafana defaults (and credentials).

InfluxDB is accessible to external clients at 8086/tcp. The idea is to be able to run several collectors in various locations (closer to E-Series, for example) and send data to a centrally managed InfluxDB. If you want to remove external access from the InfluxDB container, remove `- 8086:8086` and the line with `ports` above it in `./epa/docker-compose.yaml` and restart the container. Influx RPC port 8088 is supposed to be accessible only to trusted users (e.g. the `utils` container), so do not expose it externally.

### Add or remove a monitored array

Add another collector service (e.g. `collector-ef300c`) to `docker-compose.yaml`, build it and start it. You may use the same (existing) or own (new) InfluxDB database instance. Enter the `utils` container or use Collector to create it in advance. You may also just run collector with `--dbName` to have it created automatically.

**NOTE:** pay attention to Prometheus ports if you use them. Multiple collectors in same Docker Compose need different external ports for Prometheus exporter.

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

You can import them to your own Grafana instance. If you use the included `./epa/docker-compose.yaml`, you may deploy them from the `epa` directory like so:

```sh
docker compose --profile init up grafana-init -d
```

### Prometheus metrics freshness

You should see it in Collector logs, but here's a simple test to check the freshness of Prometheus records client-side (assuming the default 8080 port):

```sh
$ curl -v http://localhost:8080/metrics 2>&1 | grep -E "(Date:|Last-Modified:|< HTTP)"
< HTTP/1.0 200 OK
< Date: Mon, 01 Sep 2025 10:49:02 GMT
$ date
Mon Sep  1 10:49:05 AM UTC 2025
```

Example:

```raw
# HELP eseries_active_failures_total Number of active failures
# TYPE eseries_active_failures_total gauge
eseries_active_failures_total{failure_type="nonPreferredPath",object_ref="1",object_type="notOnPreferredPath",sys_id="600A098000F63714000000005E79B17B",sys_name="EF570"} 1.0
```

Example alert rule:

```raw
- alert: ESeriesStorageFailure
  expr: eseries_active_failures_total > 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "E-Series failure detected on {{ $labels.sys_name }}"
    description: "{{ $labels.failure_type }} failure on {{ $labels.object_type }} ({{ $labels.object_ref }})"
```

## FAQs

Find them [here](./FAQ.md) or check [Discussions](https://github.com/scaleoutsean/eseries-perf-analyzer/discussions) for questions that aren't in the FAQ document.

## Changelog

- 3.5.5 (April 27, 2026)
  - Address Grafana dashboard initialization issues in `grafana-init`, fix mappings
  - Address various linting errors in the python collector
  - Update InfluxDB to 1.12.4-alpine
  - Fix minor aesthetic issues in several dashboards (Controllers, Other, SSD Flash Cache)
  - EPA 3 GHCR container image releases now tagged with version (e.g. `:3.5.5`) since version 4 is also available
  - Existing EPA 3 users probably shouldn't upgrade

- 3.5.4 (April 6, 2026)
  - Upgrade Grafana from last v8 release to v12.4.1, update existing dashboards to work with v12
  - Minor update to InfluxDB (from 1.12.2 to 1.12.3) and requests library (2.33.1)
  - Collector Python base image update to `python:3.15.0a7-alpine3.23` (fewer base image vulnerabilities)
  - Test stack with SANtricity 12.00 and 11.95
  - Add `TLS_VERIFY` option to EPA collector and Docker Compose environment variables
  - Make Prometheus service port configurable
  - Parse ports from Fibre Channel host objects
  - Add SSD Flash Cache metrics and example dashboard
  - Collect snapshot and volume count, and repository volumes' total capacity
  - Bug fixes and improvements (better handling of unavailable metrics, drop repository volumes from volume collection, avoid duplicate upload of reference dashboards, re-fix SSD wear level stats (11.90 and 12.00, SAS and NVMe SSDs), initiator count, volume capacity)

- 3.5.3 (January 20, 2026)
  - Add Prometheus alerts for downed interfaces
  - Add optional "point-in-time" volume performance metrics (default: off) for use cases where default (rolling 5 minute average) is not enough. Enable with `--realtime`
  - Minor bug fixes and improvements (including GHCR container builds)

- 3.5.2 (October 8, 2025)
  - Update dependencies (container base image to 3.14-alpine3.22 and requests library v2.32.5)

- 3.5.1 (October 8, 2025)
  - Export unresolved system failures as Prometheus alerts
  - Upgrade InfluxDB to latest and greatest v1.12.2

- 3.5.0 (September 2, 2025)
  - Add several array configuration objects: hosts, volumes, disk groupings, drives. Now the monitoring of hardware configuration and - more importantly - disk group/pool and volume capacity should be easy. Existing EPA 3 users with tight DB disk space upgrading to 3.5.0+ should use `--include` and add `config_` collectors only gradually until they're sure their DB can handle it
  - InfluxDB: expose RPC service on Docker-internal network for convenient access from the utilities container
  - Collector: improve database down-sampling/pruning for records older than 30d. No real testing has been done (it'll take 31d to find out), but it's unlikely to be worse than in earlier releases. Still, 3.5.0+ collects a lot more with `config_` measurements added, so monitor the size of your `influxdb` volume in Docker
  - Add experimental Prometheus exporter (enabled by default; disable with `--output influxdb`). Docker Compose has Prometheus port closed by default
  - Grafana: sample dashboard for `config_` measurements added to /epa/grafana-init/dashboards/
  - Collector: add Prometheus client for export of only performance-related measurements. It is on by default, but can be disabled. When enabled, it requires open host firewall and/or expose Docker Compose port
  - Collector: various small improvements and small fixes discovered in testing  
  - Docker Compose: raise maximum InfluxDB RAM to 4GB (docker-compose.yaml) as EPA may need to handle more data
  - Docker Compose: "named" InfluxDB and Grafana volumes have been moved to directory-style volumes in the `epa` directory (although you can change that) because "named" didn't behave better
  
- 3.4.2 (August 29, 2025)
  - Change Docker Compose network type to `bridge` for automated setup/tear-down by Docker
  - Fix missing `--include <all-measurements>` resulted in nothing being collected
  - Add `--debug` switch to make troubleshooting bugs like the one with `--include` easier

- 3.4.1 (August 27, 2025)
  - Add volume group tag to physical disks (lets you filter disks by (RAID) group or (DPP) pool)
  - Add `--include <measurement>` for filtered writes to InfluxDB (non-included measurement(s) doesn't get written). Default: include everything

- 3.4.0 (August 24, 2025)
  - Remove `dbmanager` container and its JSON configuration file (one less container to worry about)
  - Add "create database" feature to Collector to replace `dbmanager`
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
