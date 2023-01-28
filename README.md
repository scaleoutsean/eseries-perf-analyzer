# NetApp E-Series Performance Analyzer ("EPA")

- [NetApp E-Series Performance Analyzer ("EPA")](#netapp-e-series-performance-analyzer-epa)
  - [What is this thing](#what-is-this-thing)
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
  - [Tips and Q\&A](#tips-and-qa)
  - [Changelog](#changelog)


## What is this thing

This is a friendly fork of [E-Series Performance Analyzer aka EPA](https://github.com/NetApp/eseries-perf-analyzer) v3.0.0 (see its README.md for additional information) created with the following objectives:

- Disentangle E-Series Collector from the rest of EPA and make it easy to run it anywhere (shell, Docker/Docker Compose, Kubernetes, Nomad)
- Remove SANtricity Web Services Proxy (WSP) dependency so that one collector container or script captures data for one and only one E-Series array

In terms of services, collectors collects metrics from E-Series and sends them to InfluxDB. dbmanager doesn't do much at this time - it periodically sends array names as folder tags to InfluxdDB.

![E-Series Performance Analyzer](/images/epa-eseries-perf-analyzer.png)

Each of the light-blue rectangles can be in a different location (host, network, Kubernetes namespace, etc.). But if you want to consolidate, that's still possible.

Changelog and additional details are at the bottom of this page.

## Requirements

- SANtricity OS >= 11.70 (11.74 is recommended; 11.52 and 11.74 have been tested and work, 11.6[0-9] not yet)
- Docker CE 20.10.22 (recent Docker CE or Podman should work)
- Docker Compose v1 or v2 (both v1 and v2 should work)
  - In EPA v3.1.0 and v3.2.0 Makefile in the `epa` directory may require Docker Compose v1
- Ubuntu 22.04 (other recent Linux OS on the AMD64 or ARM64 architecture should work)

These requirements are soft but this is a community fork without a variety of hardware and software to use in testing and debugging.

## Quick start

Docker Compose users:


- Clone and enter the `epa` subdirectory:
```sh
git clone https://github.com/scaleoutsean/eseries-perf-analyzer/
cd eseries-perf-analyzer/epa
```
- in the `epa` subdirectory, run `make run` to build and run InfluxDB and Grafana
  - Unless these containers need a change or update, going back to this folder is generally not necessary
- go to the `collector` sub-directory edit `docker-compose.yml` and `config.json`: `SYSNAME` docker-compose.yml must be present and identical to `name` value(s) in `config.json`). Then run `docker-compose build && docker-compose up`
  - When E-Series arrays are added or removed, edit the same files and run `docker-compose build && docker-compose down && docker-compose up` to update

Kubernetes users should skim through this page to get the idea how this works, and then work by [Kubernetes README](kubernetes/README.md).

## Slow start

It is suggested to start with Docker Compose. There's also a [Kubernetes](kubernetes)-specific folder.

- Older existing EPA (v3.0.0, v3.1.0), images, volumes and services may cause container name, volume and port conflicts. Either use a new VM or find the existing (old) deployment and run `make stop; docker-compose down; make rm` to stop and remove old EPA pre-v3.2.0 containers before building new ones. Data (InfluxDB and Grafana) can be left in place.
- Clone this repository to a new location
- Descend to the `epa` directory, run `make run` to download, build and start InfluxDB v1 and Grafana v8. You may move the pre-existing InfluxDB folder to the EPA directory if you want to keep the data. Both services will listen on all public VM interfaces, so configure your firewall accordingly.
- Go to the `collector` directory, edit two files (`config.json` and `docker-compose.yml`) and run `docker-compose build` to create collector and dbmanager containers and then `docker-compose up` to start them.

```sh
git clone github.com/scaleoutsean/eseries-perf-analyzer
cd eseries-perf-analyzer
# make and run Grafana and InfluxDB
cd epa; make run
cd ..; cd collector
# Enter name of E-Series array (or arrays) to show in Grafana drop-down list.
# This file will be copied to dbmanager container with "docker-comose build".
vim config.json
# Edit docker-compose file leave dbmanager unchanged. Collector containers should reflect config.json:
#     container_name, specifically , must be the same as array name in config.json.
vim docker-compose.yml
# We are still in the ./collector subdirectory.
# InfluxDB and Grafana are already running. Start collector(s) and dbmanager:
docker-compose up
# Check Grafana and if OK, hit CTRL+C, restart with:
docker-compose up -d
# If not OK, CTRL+C and "docker-compose down". 
# Then review config.json and docker-compose.yml.
# collector.py and db_manager.py can be started from the CLI for easier troubleshooting.
```

### Environment variables and configuration files

- `./epa/.env` has some env data used by its Makefile for InfluxDB and Grafana. Use `make` to start, stop, clean, remove, and restart these two
- `./collector` is simpler: use `docker-compose` to build/start/stop/remove collector and dbmanager containers
- When editing `./collector/docker-compose.yml`, provide the following for each E-Series array:
  - `USERNAME` - SANtricity account for monitoring such as `monitor` (read-only access to SANtricity)
  - `PASSWORD` - SANtricity password for the account used to monitor
  - `SYSNAME` - SANtricity array name, such as R26U25-EF600 - get this from the SANtricity Web UI, but you can use your own - just keep it consistent with the name in `./collector/config.json`. If you want to make the name identical to actual E-Series array name, [this image](/images/sysname-in-santricity-manager.png) shows where to look them up
  - `SYSID` - SANtricity WWN for the array, such as 600A098000F63714000000005E79C888 - see [this image](/images/sysid-in-santricity-manager.png) on where to find it.
  - `API` - SANtricity controller's IP address such as 6.6.6.6
  - `RETENTION_PERIOD` - data retention in InfluxDB, such as 52w (52 weeks)
  - `DB_ADDRESS` - external IPv4 of InfluxDB (if the host IP where InfluxDB is running is remote that could be something like 7.7.7.7, if collector and InfluxDB are on the same host then 127.0.0.1, or if they're in the same Kubernetes namespace then `influxdb`)

What are the correct values for `API`, `SYSNAME` and `SYSID`? The `API` addresses are IPv4 addresses (or FQDNs) used to connect to the E-Series Web management UI. You can see them in the browser when you manage an E-Series array. For `SYSNAME` and `SYSID`, see the image links just above.

For consistency's sake it is recommended that `SYSNAME` in EPA is the same as the actual E-Series system name, but it doesn't have to be. It can consist of arbitrary alphanumeric characters (and `_` and `-`; if interested please check the Docker Compose documentation). Just make sure the array names in `./collector/docker-compose.yml` and `./collector/config.json` are consistent; otherwise array metrics and events may get collected, but drop-down lists with array names in Grafana dashboards won't match so the dashboards will be empty.

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

`SYSNAME` from docker-comopose.yml should be the same as `name` in `config.json` used by dbmanager. Here the `name` matches `environment:SYSNAME` value in `docker-compose.yml` above.

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

To protect InfluxDB service open 8086/tcp to IP's or FQDNs where collector, dbmanager and Grafana run.

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

The array name has not changed, so it wasn't necessary to edit `./collector/config.json` and rebuild `./collector/dbmanager`, so running `docker-compose build` wasn't necessary.

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

## Sample Grafana screenshots

This fork's dashboards are identical to upstream v3.0.0, but upstream repository has no screenshots - in fact they're hard to find on the Internet - so a sample of each dashboard is provided below.

- System view

![E-Series System](/images/sample-screenshot-epa-collector-system.png)

- Array interfaces

![E-Series Array Interfaces.png](/images/sample-screenshot-epa-collector-interfaces.png)

This screenshot shows *aggregate* values for all arrays (useful in HPC environments where workloads span across multiple arrays). Further below there are other charts with individual metrics.

- Physical disks

![E-Series Physical Disks.png](/images/sample-screenshot-epa-collector-disks.png)

- Logical volumes

![E-Series Volumes.png](/images/sample-screenshot-epa-collector-volumes.png)

- Physical disks - SSD wear level (%)

![E-Series SSD Wear Level](/images/sample-screenshot-epa-collector-disks-ssd-wear-level.png)

This is the second example with physical disks and it's highlighted because this data is collected by collector, but not shown in dashboards. In order to collect this data, an E-Series array with a recent SANtricity OS (11.74, for example) and at least one SSD is required. Visualization can then be done by duplicating one of the existing disk charts and modifying to show "percentEnduranceUsed" values. This screenshot shows that SSD wear level metrics are collected from just one of two arrays.

## Tips and Q&A

Below details are mostly related to this fork. For upstream details please check their read-me file.

**Q:** Why do I need to fill in so many details in Collector's YAML file?

**A:** It's a one time activity that lowers the possibility of making a mistake.

**Q:** It's not convenient for me to have multiple storage admins edit `./collector/docker-compose.yml` 

**A:** The whole point of this fork (and separating collector from the rest) is that centralization can be avoided, so when there's no one "storage team" that manages all arrays, each admin can have their own collector and rotate (and protect) passwords as they see fit.

**Q:** How to modify collector Docker image? 

**A:** Any way you want. Example: `cp -pr ./collector/collector ./collector/mycollector-v1`, edit container config in the new location, build the container in the new directory using `docker build -t ${NEW_NAME} .`, change `./collector/docker-compose.yml` to use the new Docker image (under `epa/mycollector-v1`), change `./collector/config.json` to make sure dbmanager is aware of the new array name (`SYSNAME`). Finally, run `docker-compose build && docker-compose up $mycollector`. You may modify collector's Makefile to add the new directory.

**Q:** This looks complicated!

**A:** If you can't handle it, you don't even have to use containers. Install InfluxDB *any way you can/want*, and run collector and dbmanager from the CLI (use `python3 ./collector/collector/collector.py -h` and similar for db_manager.py to see how). Create a data source (InfluxDB) for Grafana, import EPA's dashboards or create your own.

**Q:** Why can't we have one config.json for all monitored arrays?

**A:** There may be different people managing different arrays. Each can run their own collector and not spend more than 5 minutes to learn what they need to do to get this to work. Each can edit their Docker environment parameters (say, change the password in docker-compose.yaml) without touching InfluxDB and Grafana. dbmanager (config.json) is the only "centralized" service which needs to maintain the list of array names that are being sent to InfluxDB and container no credentials (see `config.json`).

**Q:** If I have three arrays, two VMs with collectors and these send data to one InfluxDB, do I need to run 1, 2 or 3 dbmanager containers?

**A:** Just one dbmanager is needed if you have one InfluxDB. 

**Q:** What does dbmanager actually do?

**A:** It sends the list of monitored arrays (`SYSNAME`s) to InfluxDB, that's all. This is used to create a drop-down list of arrays in EPA's Grafana dashboards. Prior to v3.1.0 EPA got its list of arrays from the Web Services Proxy so it "knew" which arrays are being monitored. In EPA v3.1.0 and v3.2.0 collector containers may be running in several places and none of them would know what other collectors exist out there. dbmanager maintains a list of all monitored arrays and periodically pushes it to InfluxDB, while dropping other folders (array names which no longer need to be monitored). If you have a better idea or know that's unnecessary, feel free to submit a pull request. InfluxDB v1 is old and this approach is simple and gets the job done.

**Q:** I have an existing intance of the upstream EPA v3.0.0. Can I add more E-Series arrays without using WSP?

**A**: It could be done, but it's complicated because db_manager.py now drops folder tags for arrays it's not aware of so it'd be too much trouble. Best remove existing EPA and deploy EPA >= v3.1.0. You may be able to retain all InfluxDB data if you used just default folders in WSP and did not change array names (i.e. `SYSNAME` and `SYSID` remain the same as they were in v3.0.0). Grafana dashboards haven't been changed and I won't change them in any future v3, but if you've customized them or added your own, make a backup and make sure it can be restore it to the new deployment before old Grafana is deleted.

**Q:** How can I customize Grafana's options?

**A**: EPA doesn't change Grafana in any way, so follow the official documentation. If ./epa/grafana/grafana.ini is replaced by ./epa/grafana/grafana.ini.alternative that may provide better privacy (but it also disables notifications related to security and other updates).

**Q:** What if I run my own InfluxDB v1.8 and Grafana v8? Can I use this Collector without EPA?

**A**: Yes. That's another reason why I made collector.py a stand-alone script without dependencies on the WSP. Just build this fork of EPA and collector container, and then run just collector's docker-compose (no need to run `make run` in the `epa` subdirectory since you already have InfluxDB and Grafana). Or use `collector` and `dbmanager` from the CLI, without containers.

**Q:** Where's my InfluxDB data?

**A:** It is in the `epa/influx-database` sub-directory and created on first successful run of EPA (`make run`). 

**Q:** Where's my Grafana data? I see nothing when I look at the dashboards!

**A:** It uses a local Docker volume, see `epa/docker-compose.yml`. Grafana data can't be seen in dahboards until collector successfully runs, and sends data to the `eseries` database in InfluxDB. `dbmanager` also must run to create Influx "folders" (kind of tags) that let you select arrays in EPA's Grafana dashboards. Login to InfluxDB or go to Grafana > Explore to see if Grafana can access InfluxDB and see any data in it. Sometimes data is accessible to Grafana, but collector or dbmanager are misconfigured so dashboards show nothing. Other times the collector has a typo in the password or IP address and can't even access E-Series.

**Q:** If I use my own Grafana, do I need to recreate EPA dashboards from scratch?

**A:** It is possible to create an InfluxDB data source named "WSP" (name hard-coded in EPA dashboards) and import dashboards from `epa/plugins/eseries_monitoring/dashboards` - see the Kubernetes README for additional information. Grafana 9 users need to do the same, but may also have to [make minor edits](https://github.com/grafana/grafana/discussions/45230) to EPA's Grafana 8 dashboards.

**Q:** How much memory does each collector container need? 

**A:** It my testing, much less than 32 MiB. It'd take 32 arrays to use 1GiB of RAM (with 32 collector containers).

**Q:** How much memory does the dbmanager container need? 

**A:** We need just one container per InfluxDB and it needs less than 20 MiB. 32 MiB or 64 MiB is more than enough.

**Q:** How to run collector and dbmanager from the CLI? 

**A:** Run `db_manager.py - h` and `collector.py -h`. Example for the latter:

```sh
python3 ./collector/collector/collector.py \
  -u ${USERNAME} -p ${PASSWORD} \
  --api ${API} \
  --dbAddress ${DB_ADDRESS}:8086 \
  --retention ${RETENTION_PERIOD} \
  --sysname ${SYSNAME} --sysid ${SYSID} \
  -i -s
```

**Q:** What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails? 

**A:** You will notice it quickly because you'll stop getting metrics. Then fix the controller or change the setting to use the other controller and restart collector. It is also possible to use `--api 5.5.5.1 5.5.5.2` to round-robin collector requests to two controllers. If one fails you should get 50% less frequent metric delivery to Grafana, and get a hint. Or, set `API=5.5.5.1 5.5.5.2` in docker-compose.yaml. This hasn't been tested a lot, but it appears to work.

**Q:** Can the E-Series' WWN change?

**A:** Normally it can't, but it's theoretically [possible](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/E-Series_SANtricity_Software_Suite/WWNs_changed_after_offline_replacement_of_tray_0). Should that happen you'd have to update your configuration and restart collector container affected by this change.


## Changelog

- 3.2.0 (Jan 30, 2023):
  - No changes to Grafana container, Grafana charts, and InfluxDB container
  - collector and dbmanager are now completely independent of containers built by InfluxDB and Grafana Makefile
  - New Kubernetes folder with Kubernetes-related instructions and sample YAML files
  - Collector and dbmanager can be built for AMD64 and ARM64 architecture

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
