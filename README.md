# NetApp E-Series Performance Analyzer ("EPA") without SANtricity Web Services Proxy ("WSP")

## What is this thing

This is a friendly fork of [E-Series Performance Analyzer aka EPA](https://github.com/NetApp/eseries-perf-analyzer) v3.0.0 (see its README.md for additional information) created with the following objectives:

- Disentangle E-Series Collector from the rest of EPA and make it easy to run it anywhere (shell, Docker/Docker Compose, Kubernetes, Nomad)
- Remove SANtricity Web Services Proxy (WSP) dependency so that one collector script captures data for one and only one E-Series array

Additionally, minor differences include:

- Updated Grafana v8 (8.5.15), and Alpine OS image for Python 3.10 (3.10-alpine3.17)
- Expanded number of required arguments in `collector.py` to avoid unintentional mistakes
- Collector container no longer shares Docker network with the two (InfluxDB, Grafana) EPA containers because the assumption is Collector probably runs on a different host or accesses InfluxDB over public host network
- Unit tests and Makefile in the EPA directory for collector plugin no longer work
- The SANtricity Web Services Proxy container has been removed in this fork's version v3.0.1. Fork v3.0.0 still has WSP (newer version than upstream v3.0.0!), but it doesn't run (it can be started independently and used on port 8443/tcp by those who need it).

## How to use this fork

### Requirements

- SANtricity OS >= 11.52 (soft; 11.52 and 11.74 have been tested 11.6* not yet)
- Docker CE 20.10.22 (soft; recent Docker CE or Podman should work)
- Docker Compose (soft; both v1 and v2 should work)
- Ubuntu 22.04 (soft; other recent Linux OS should work)

### Summary

- `epa`: Build and run InfluxDB and Grafana in the `epa` sub-directory. These containers are from the original EPA and include Grafana dashboards.
- `collector`: in the `collector` sub-directory, build and run collector(s) (one per E-Series array) and a "helper" container called `dbmanager` (one per InfluxDB).
- The makefiles currently still require Docker Compose v1

### Build containers and create configuration files

- Older existing EPA, images, volumes and service ports may cause container name and port conflicts. Either use a new VM or run `make stop; docker-compose down; make rm` to stop and remove old containers before building new ones. Data (InfluxDB and Grafana) can be left in place.
- Clone the repository
- Descend to the `epa` directory, run `make run` to download, build and start InfluxDB v1 and Grafana v8. Both will listen on all public VM interfaces so set up firewall accordingly.
- Go to `collector` directory, edit two files (`config.json` and `docker-compose.yml`) and run `make build` to create containers and `docker-compose up` to start them.

```sh
git clone github.com/scaleoutsean/eseries-perf-analyzer
cd eseries-perf-analyzer
# Go to the epa folder
cd epa; make run
# Go back to top level and then to the collector folder
cd ..; cd collector
# Enter name of E-Series array (or arrays) to show in Grafana drop-down list.
# This file will be copied to ./collector/dbmanager/config.json when "make run" is executed.
# You can also copy it manually or edit it in place if you don't want to use Makefile. 
vim config.json
# Edit docker-compose file leave dbmanager unchanged. Collector containers should reflect config.json:
#     container_name, specifically , must be the same as array name in config.json.
vim docker-compose.yml
# We are still in ./collector subdirectory.
# InfluxDB and Grafana are already running, start collector(s) and dbmanager:
docker-compose up
# Check Grafana and if OK, hit CTRL+C, restart with:
docker-compose up -d
# If not OK, CTRL+C and "docker-compose down". 
# Then review config.json and docker-compose.yml.
# collector.py and db_manager.py can be started from the CLI for easier troubleshooting.
```

- `./epa/.env` has some env data used by its Makefile for InfluxDB and Grafana. Use `make` to start, stop, clean, remove, and restart these two.
- `./collector`'s values are hard-coded into its Makefile. Use `docker-compose` to start/stop/remove collector and dbmanager containers.

- When editing `./collector/docker-compose.yml`, provide the following for each E-Series array:
  - `USERNAME` - SANtricity account for monitoring such as `monitor` (read-only access to SANtricity)
  - `PASSWORD` - SANtricity password for the account used to monitor
  - `SYSNAME` - SANtricity array name, such as R26U25-EF600 - get this from the SANtricity Web UI, but you can use your own - just keep it consistent with the name in `./collector/config.json`! An example can be viewed [in this image](/images/sysname-in-santricity-manager.png)
  - `SYSID` - SANtricity WWN for the array, such as 600A098000F63714000000005E79C888 - an example can be viewed [here](/images/sysid-in-santricity-manager.png)
  - `API` - SANtricity controller's IP address such as 6.6.6.6
  - `RETENTION_PERIOD` - data retention in InfluxDB, such as 52w (52 weeks)
  - `DB_ADDRESS` - external IPv4 of host where EPA is running, such as 7.7.7.7, to connect to InfluxDB
- Where to find the correct values for API, SYSNAME and SYSID? The API addresses are IPv4 addresses (or FQDNs) used to connect to the E-Series Web management UI. You can see them in the browser when you manage an E-Series array. For SYSNAME and SYSID see the image links just above
  - For consistency's sake it is recommended that SYSNAME in EPA is the same as the actual E-Series system name, but it doesn't have to be. It can consist of arbitrary alphanumeric characters (and `_` and `-`, if I remember correctly - if interested please check the Docker Compose documentation). Just make sure the array names in `./collector/docker-compose.yml` and `./collector/config.json` are consistent, or otherwise array metrics and events may get collected, but the name won't appear in array drop-down list in Grafana dashboard

- `container_name` to match the name in `./collector/config.json`:

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

- Matching SYSNAME/name in `config.json` is replicated by Collector's `make build` to `./collector/dbmanager/config.json`:

```json
{
    "storage_systems": [
        {
            "name": "R26U25-EF600"
        }
    ]
}
```

- To customize collector container images, the directory with collector's Docker files (`./collector/collector`) could be copied to multiple sub-directories (`./collector/$SYSNAME`), and docker-compose.yml could add containers with service names such as `collector-$SYSNAME` (where `$SYSNAME` is System Name given to each E-Series array).

- `dbmanager` doesn't do much and doesn't yet make use `RETENTION_PERIOD` (just leave that value alone for now). Only `DB_ADDRESS` and syntax/names of `config.json` need to be correct.

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

The original EPA exposes the SANtricity WSP (8080/tcp) and Grafana (3000/tcp) to the outside world.

This fork does not have WSP. Grafana is the same (3000/tcp), but InfluxDB is now exposed on port 8086/tcp. The idea is you may run Collectors in various locations (closer to E-Series, for example) outside of the InfluxDB VM and send data to InfluxDB.

To protect InfluxDB service, you may use your OS settings to open 8086/tcp to hosts where Collector will run. Collector and dbmanager do not need open inbound ports - both only connect to InfluxDB.

## Add or remove a monitored array

To add a SANtricity array, we don't need to do anything in the `epa` subdirectory.

- Go to `./collector`
- Edit `docker-compose.yml` - if you copy-paste, make sure you get the variables and `container_name` right!
- Edit `config.json` to add a matching record for the new array
- `docker-compose down`
- `make build`
- `docker-compose up -d`

To remove an array, remove it from `config.json` and `docker-compose.yml` and do the last three steps the same way.

## Update password for the monitor account

To change the monitor account password for `R11U01-EF300`, change it on the array as array admin, find this array in `docker-compose.yml`, change the password value in the `PASSWORD=` row for the array, run `docker-compose down R11U01-EF300` followed by `docker-compose up R11U01-EF300`. 

The array name has not changed, so it wasn't necessary to edit `./collector/config.json` and rebuild `./collector/dbmanager`. That's also why running `make build` wasn't necessary.

## Walk-through

- If collector and dbmanager run on a different host, create firewall rules to open 8086/tcp only to collector clients, and 3000/tcp (Grafana) only to users allowed to access Grafana (even better, deploy a reverse proxy with TLS to protect Grafana)

- Build and run InfluxDB and Grafana:

```sh
$ cd epa

$ make build 

$ docker images 
REPOSITORY                                           TAG               IMAGE ID       CREATED              SIZE
ntap-grafana-plugin/eseries_monitoring/python-base   latest            9d5f8085ab4a   51 seconds ago       50.1MB
<none>                                               <none>            510d1a737cad   52 seconds ago       12.9MB
ntap-grafana-plugin/eseries_monitoring/alpine-base   latest            85a1ebbfbc5e   54 seconds ago       7.05MB
ntap-grafana/influxdb                                3.1               4c650d02806a   55 seconds ago       173MB
ntap-grafana/ansible                                 3.1               94ee4e4a0405   About a minute ago   398MB
<none>                                               <none>            bd3051fd74a4   About a minute ago   621MB
ntap-grafana/python-base                             3.1               5216517bec73   2 minutes ago        50.1MB
<none>                                               <none>            e9b76094f71d   2 minutes ago        12MB

$ make run    # runs: docker-compose up -d

$ # expect to see two containers listening on external ports - InfluxDB and Grafana

$ docker ps -a | grep '0.0.0.0'
95dd8ec86b82   ntap-grafana/grafana:3.0    0.0.0.0:3000->3000/tcp, :::3000->3000/tcp   grafana
f00b858c0728   ntap-grafana/influxdb:3.0   0.0.0.0:8086->8086/tcp, :::8086->8086/tcp   influxdb
```

- Login to Grafana with admin/admin and change admin password. At this point you're not supposed to see anything in the EPA dashboards

- Go to top-level collector directory to build Collector-related containers

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

$ make build
```

- `make build` builds two containers, collector & dbmanager, and copies `config.json` to `./collector/dbmanager/config.json`
- There should be two new container images (collector & dbmanager) used by two or more containers (here three, because there are two arrays)

```sh
$ docker ps -a | grep monitoring 
CONTAINER ID   IMAGE                                               NAMES
9d725fa1a756   ntap-grafana-plugin/eseries_monitoring/collector    R24U04-E2824
1048f321d631   ntap-grafana-plugin/eseries_monitoring/collector    R26U25-EF600
61d3cb5e83bc   ntap-grafana-plugin/eseries_monitoring/dbmanager    dbmanager
```

- Stop any existing Collector collectors and start new (or updated) containers

```sh
$ docker-compose down && docker-compose up 
```

## Sample Grafana screenshots of EPA/Collector dashboards

This fork's dashboards are identical to upstream, but upstream repository has no screenshots - in fact they're hard to find on the Internet - so below shows a sample of each dashboard.

- System view

![E-Series System](/images/sample-screenshot-epa-collector-system.png)

- Array interfaces

![E-Series Array Interfaces.png](/images/sample-screenshot-epa-collector-interfaces.png)

This screenshot shows *aggregate* values. Further below there are other charts with individual metrics.

- Physical disks 

![E-Series Physical Disks.png](/images/sample-screenshot-epa-collector-disks.png)

- Logical volumes

![E-Series Volumes.png](/images/sample-screenshot-epa-collector-volumes.png)

- Physical disks - SSD wear level (%)

![E-Series SSD Wear Level](/images/sample-screenshot-epa-collector-disks-ssd-wear-level.png)

This is the second example with physical disks and it's highlighted because this data is collected by collector, but not shown in dashboards. In order to collect this data, an E-Series array with a recent SANtricity OS (11.74, for example) and at least one SSD is required. Visualization can then be done by duplicating one of the existing disk charts and modifying to show "percentEnduranceUsed" values. This screenshot shows that SSD wear level metrics are not collected from the E2824 array which happens to have SANtricity 11.50 and no SSD disks.

## Tips and Q&A

Below details are mostly related to this fork. For upstream details please check their read-me file.

**Q:** Why do I need to fill in so many details in Collector's YAML file? 

**A:** I think it lowers the possibility of making a mistake and if collector containers run on different machines, each will still need its own config file. But users are free to make changes as you see fit.

**Q:** It's not convenient for me to have multiple storage admins edit `./collector/docker-compose.yml` 

**A:** The whole point of separating Collector from EPA is that centralization can be avoided, so when there's no one "storage team" that manages all arrays, each admin can have their own.

**Q:** How to modify Collector's Docker image? 

**A:** Any way you want. Example: `cp -pr ./collector/collector ./collector/mycollector`, edit container config in the new location, build the container with `docker build -t ${NAME} .`, change `./collector/docker-compose.yml` to use the new Docker image, change `./collector/config.json` to make sure a folder is created in Grafana. Finally, run `docker-compose up $mycollector`. Collector's Makefile could automate this, but currently it is very simple and doesn't have that feature.

**Q:** This looks complicated... 

**A:** If you can't handle it, install InfluxDB any way you can/want, run Collector from the CLI (`python3 ./collector/collector/collector.py -h`). Create a data source (InfluxDB) for Grafana and add your own dashboards or try to replicate EPA's configuration by looking at the source code, configuration files and exported dashboard JSON files.

**Q:** Why can't we have one config.json for all monitored arrays? 

**A:** There may be different people managing different arrays. Each can run their own Collector and not spend more than 5 minutes to learn what they need to do to get this to work. Each can edit their Docker environment parameters (say, change the password) without touching InfluxDB and Grafana.

**Q:** If I have three arrays, two VMs with collectors and these send data to one InfluxDB, do I need to run 1, 2 or 3 dbmanager containers?

**A:** Just one dbmanager is needed if you have one InfluxDB. 

**Q:** What does dbmanager actually do?

**A:** It just creates a drop-down list of arrays in EPA's Grafana dashboards. It's a stupid reason to run a container, but previously (upstream EPA and this EPA fork v3.0.0) EPA got its list of arrays from the WSP and it "knew" which arrays are being monitored. Here we could have collector containers running in several places and none of them know what other containers exist out there. dbmanager is there to gather that list and periodically push it to InfluxDB, while dropping other folders which no longer need to be monitored. If we didn't want to remove other folders from the menu, we could have the code in each collector (just add own folder, and don't worry about dropping anything) but I think the idea behind dropping older folders was to decrease database bloat and that's why it's in there. If you have a better idea or know that's unnecessary, feel free to submit a pull request. InfluxDB v1 is old so I'm not in a mood to devise new ways to deal with it.

**Q:** I have existing upstream EPA v3.0.0. Can I add more E-Series arrays without using WSP?

**A**: It could be done, but it's complicated because dbmanager.py now drops folder tags for arrays it's not aware of. It's too much trouble. Best to remove that and you can probably retain all data. EPA v3.0.0 dashboards and InfluxDB have not been modified in this fork's v3.1.0.

**Q:** What if I run my own InfluxDB v1.8 and Grafana v8? Can I use this Collector without EPA?

**A**: Yes. That's another reason why I made collector.py a stand-alone script without dependencies on the WSP. Just build this fork of EPA and Collector container, and then run just Collector's docker-compose. Note that this Collector doesn't support InfluxDB v2 - additional work would be required for that.

**Q:** Where's my InfluxDB data?

**A:** It is the `epa/influx-database` sub-directory and created on first successful run of EPA (`make run`). 

**Q:** Where's my Grafana data? I see nothing when I look at the dashboards!

**A:** It uses a local Docker volume, `epa/docker-compose.yml`. Grafana data can't be seen in dahboards until Collector successfully runs and sends it to InfluxDB. `dbmanager` also must create Influx "folders" (system tags, actually) that let you select arrays for which collector collects data.

**Q:** If I use my own Grafana, do I need to recreate EPA dashboards from scratch?

**A:** It should be possible to create an identically named data source (to connect to InfluxDB) and import dashboards from `epa/plugins/eseries_monitoring/dashboards`. Grafana 9 users need to do the same, but may also have to [make minor edits](https://github.com/grafana/grafana/discussions/45230) to Grafana 8 dashboards.

**Q:** How much memory does each Collector container need? 

**A:** It my testing, much less than 32 MiB. It'd take 32 arrays to use 1GiB of RAM (with 32 collector containers).

**Q:** How to use Collector outside of a containers? 

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

**A:** You will notice it quickly because you'll stop getting metrics. Then fix the controller or change the setting to the other controller and restart the collector container. It is also possible to use `--api 5.5.5.1 5.5.5.2` to round-robin requests to two controllers. If one fails you should see 50% less metric delivered to Grafana, and get a hint. Or, in docker-compose.yaml: `API=5.5.5.1 5.5.5.2`.

**Q:** Can the E-Series' WWN change?

**A:** Normally it can't, but it's theoretically [possible](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/E-Series_SANtricity_Software_Suite/WWNs_changed_after_offline_replacement_of_tray_0). Should that happen you'd have to update your configuration and restart Collector container.

