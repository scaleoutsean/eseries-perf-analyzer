# NetApp E-Series Performance Analyzer ("EPA") without SANtricity Web Services Proxy ("WSP")

- [NetApp E-Series Performance Analyzer ("EPA") without SANtricity Web Services Proxy ("WSP")](#netapp-e-series-performance-analyzer-epa-without-santricity-web-services-proxy-wsp)
  - [What is this thing](#what-is-this-thing)
  - [How to use this fork](#how-to-use-this-fork)
    - [Summary](#summary)
    - [Build containers and create configuration files](#build-containers-and-create-configuration-files)
    - [Adjust firewall settings for InfluxDB and Grafana ports](#adjust-firewall-settings-for-influxdb-and-grafana-ports)
    - [Start services](#start-services)
  - [Add or remove a monitored array](#add-or-remove-a-monitored-array)
  - [Update password for the monitor account](#update-password-for-the-monitor-account)
  - [Notes](#notes)
  - [Walk-through](#walk-through)
    - [Build EPA](#build-epa)
    - [Use collector](#use-collector)
    - [Use collector Docker Hub image](#use-collector-docker-hub-image)
  - [Sample Grafana screenshots of EPA/Collector dashboards](#sample-grafana-screenshots-of-epacollector-dashboards)
  - [Component versions](#component-versions)


## What is this thing

This is a friendly fork of [E-Series Performance Analyzer aka EPA](https://github.com/NetApp/eseries-perf-analyzer) v3.0.0 (see its README.md for additional information) created with the following objectives:

- Disentangle E-Series Collector from the rest of EPA and make it easy to run it anywhere (shell, Docker/Docker Compose, Kubernetes, Nomad)
- Remove SANtricity Web Services Proxy (WSP) dependency so that one collector script captures data for one and only one E-Series array

Additionally, minor differences include:

- Latest minor version of Grafana v8 (8.5.15), and Alpine OS image for Python 3.10 (3.10-alpine3.17)
- Expanded number of required arguments in `collector.py` to avoid mistakes and (for the most part) the need to understand how the EPA Makefile works
- Collector container no longer shares Docker network with the two (InfluxDB, Grafana) EPA containers because the assumption is Collector will run on a different host or in any case access InfluxDB over public host network
- Unit tests and Makefile in the EPA directory for collector plugin no longer work
- The SANtricity Web Services Proxy container was upgraded to latest and can run, but it's set to not start with EPA because `collector.py` no longer uses it. It can be started independently and used on port 8443/tcp by those who need it.

## How to use this fork

### Summary

- We build EPA images which builds one of all images including the one used by Collector (although Collector can also be built on its own)
- Docker Compose for EPA starts Influx and Grafana, while Docker Compose for Collector starts one or more Collector containers

### Build containers and create configuration files

- Clone the repository
- Navigate to the `epa` folder and run `make build` to download and build Docker container images
- Run `make run` to start InfluxDB v1 and Grafana v8. Unlike the original, WSP and Collector will *not* be started

```sh
git clone github.com/scaleoutsean/eseries-perf-analyzer
cd eseries-perf-analyzer
# go to the epa folder
cd epa
make build
# go back to top level and then to the collector folder
cd ..
cd collector
vim docker-compose.yml
```

- When editing `collector/docker-compose.yml`, provide the following for each E-Series array:
  - USERNAME - SANtricity account for monitoring such as `monitor` (read-only access to SANtricity)
  - PASSWORD - SANtricity password for the account used to monitor
  - SYSNAME - SANtricity array name, such as rack26u25-ef600 - get this from SANtricity Web UI
  - SYSID - SANtricity WWID for the array, such as 600A098000F63714000000005E79C888 - get this from SANtricity Web UI
  - API - SANtricity controller's IP address such as 6.6.6.6
  - RETENTION_PERIOD - data retention in InfluxDB, such as 52w (52 weeks)
  - DB_ADDRESS - external IPv4 of host where EPA is running, such as 7.7.7.7, to connect to InfluxDB

- Where to find values of API, SYSNAME and SYSID? API are IPv4 addresses (or FQDNs) used to connect to the E-Series Web management UI. You can see them in the browser. For SYSNAME and SYSID see [this](/sysname-in-santricity-manager.png) and [this](/sysid-in-santricity-manager.png) screenshot.

- In the example below you may also want to change service name (collector-rack26u25-ef600) and `container_name` to match sub-directory name for easier orientation later on:

```yaml
services:

  collector-rack26u25-ef600:
    image: ntap-grafana-plugin/eseries_monitoring/collector:latest
    container_name: rack26u25-ef600
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
      - SYSNAME=rack26u25-ef600
      - SYSID=600A098000F63714000000005E79C888
      - API=6.6.6.6
      - RETENTION_PERIOD=26w
      - DB_ADDRESS=7.7.7.7
      - DB_PORT=8086
```

- There's a sample directory (`collector/docker-compose.yml/rack26u25-ef600`) which matches the disk array name from above YAML, and the purpose is to have one directory per each array, and a `docker-compose.yml` where service name is `collector-$SYSNAME` (where SYSNAME is System Name you gave to E-Series array). You can rename it, and you can rename the string in YAML file above.
- You can also copy-paste the sample folder and rename it and ignore the original sample folder (just leave it there for reference). With two directory copies named `array1` and `array2`, your `collector/docker-compose.yaml` may look similar to this:

```yaml
version: '3.6'

services:

  collector-array1:
    image: ntap-grafana-plugin/eseries_monitoring/collector:latest
    container_name: array1
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
      - SYSNAME=rack26u25-ef600
      - SYSID=600A098000F63714000000005E79C888
      - API=5.5.5.5
      - RETENTION_PERIOD=26w
      - DB_ADDRESS=7.7.7.7
      - DB_PORT=8086

  collector-array2:
    image: ntap-grafana-plugin/eseries_monitoring/collector:latest
    container_name: array2
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
      - SYSNAME=rack15u04-e5760
      - SYSID=600A098000F63714000000005E79C111
      - API=6.6.6.6
      - RETENTION_PERIOD=26w
      - DB_ADDRESS=7.7.7.7
      - DB_PORT=8086
```

Now we have:

- `epa/docker-compose.yml` with InfluxDB and Grafana ready to start in the `EPA` directory (requires no changes, activated with `make run`)
- `ntap-grafana-plugin/eseries_monitoring/collector:latest` image built with EPA's `make build`. You may copy this image to other hosts or upload to container registry
- On this or other system: `collector/docker-compose.yml` where several Collector containers can be started to collect data from different E-Series arrays and send them to InfluxDB

### Adjust firewall settings for InfluxDB and Grafana ports

The original EPA exposes WSP (8080/tcp) and Grafana (3000/tcp) to the outside world.

This fork does not have WSP. Grafana is the same (3000/tcp), but InfluxDB is now exposed on port 8086/tcp. The idea is you may run Collectors in various locations (closer to E-Series, for example) outside of the InfluxDB VM and send data to InfluxDB.

To protect InfluxDB service, you may use your OS settings to open 8086/tcp to hosts where Collector will run. Collector itself does not need open inbound ports.

### Start services

- EPA is started with `make run` (which runs services using docker-compose)

```sh
# go to epa
cd epa
make run
```

- Inspect the output and make sure InfluxDB and Grafana are listening on ports 8086 and 3000, respectively. Login to Grafana with admin/admin.
- Next start Collector (maybe you'll need to add `sudo`)

```sh
# go to collector
cd collector
docker-compose up
```

- If you see it working properly, hit CTRL+C and then run it with `docker-compose up -d` to have it run in the background
- Collector containers doesn't listen on any ports, it only creates outgoing connections to SANtricity API endpoints and InfluxDB

## Add or remove a monitored array

To add a SANtricity array, change docker-compose.yml for Collector: make a copy of the sample directory, rename it (array3, for example) add another section in docker-compose.yml, and run `docker-compose up array3 -d`.

To remove and array, `docker-compose down array3`. Then remove the folder and configuration section.

## Update password for the monitor account

Change it on SANtricity, run `docker-compose down array3`, change the password in docker-compose.yml, and start the container with `docker-compose up array3` to verify it's working, then hit CTRL+C to stop it and start it again with `-d`. 

Collector containers are stateless and have no data that needs to be persisted to its own volume.

## Notes

Below details are mostly related to this fork. For upstream details please check their read-me file.

**Q:** Why do I need to fill in so many details in Collector's YAML file? 

**A:** Because it's simple. If you fill it out correctly, it will work. If you don't, it won't. There should be no other place to troubleshoot.

**Q:** It's not convenient for me to have multiple storage admins edit `collector/docker-compose.yml` 

**A:** The whole point of separating Collector from EPA is that centralization can be avoided, so when there's no one "storage team" that manages all arrays, each admin can have their own.

```sh
somedir
  epa               # VM1
  collector1/arrayA # can be only on VM2
  collector2/arrayB1 # can be only on VM3
  collector2/arrayB2 # can be only on VM3
```

**Q:** How to modify Collector's Docker image? 

**A:** If you want to use EPA to build like in walk-through below, you can modify it in `epa/plugins/eseries_monitoring/collector`. You can also use the one in `collector/rack26u25-ef600`, but as mentioned elsewhere it uses python-base image from EPA so you still need to run `make build` and such in the `epa` directory. The difference is: the former approach can break `Makefile` scripts (i.e. if you mess up Collector build, `make build` won't work). The latter cannot, so it's easier to experiment with.

**Q:** This looks complicated... 

**A:** If you can't handle it, install InfluxDB any way you can/want, run Collector from the CLI (`python3 collector/rack26u25-ef600/collector.py -h`). Create a data source (InfluxDB) for Grafana and add your own dashboards or try to replicate EPA's configuration by looking at the source code, configuration files and exported dashboard JSON files.

**Q:** Why can't we have one config.json for all monitored arrays? 

**A:** See the first answer. In this approach there may be different people managing different arrays. Each can run their own Collector and not spend more than 5 minutes to learn what they need to do to get this to work. Each can edit their Docker environment parameters (say, change the password) without touching InfluxDB and Grafana.

**Q:** I first (or "I only") tried to build Collector container and it failed. 

**A:** Then don't do that. Collector uses a base image from EPA, so EPA must be built (`make build`) first or you could edit Collector's Dockerfile, or you could build Collector on EPA InfluxDB VM and then upload Collector image to your registry to let all collector runners avoid the need to build EPA and Collector.

**Q:** What if I run existing upstream EPA v3.0.0? Can I add more E-Series arrays without using WSP 

**A**: Yes. You need to modify InfluxDB to listen on an external and port 8086/tcp, and then just build and configure this fork EPA and Collector, and run only Collector's docker-compose. All arrays are put in "All Storage Systems" and if System Names and WWN's are unique they shouldn't collide with existing storage systems and WSP's "folders".

**Q:** What if I run own InfluxDB v1.8 and Grafana v8? Can I use Collector without EPA? 

**A**: Yes. That's another reason why I made collector.py a stand-alone script without dependencies on WSP. Just build this fork of EPA and Collector container, and then run just Collector's docker-compose. Note that this Collector doesn't support InfluxDB v2, a bit of additional work would be required for that.

**Q:** Since this EPA builds collector container, why can't I just run that one like upstream does? 

**A:** It's probably possible - you can specify the right image and environment variables in `epa/plugins/eseries_monitoring/docker-compose.yaml` and try `make run` - but that hasn't been tested because the purpose of this fork is (1) to dis-entangle Collector from InfluxDB and Grafana, and (2) be able to run multiple collectors, which is easier from the collector folder than from the epa folder.

**Q:** Where's my InfluxDB?

**A:** It is created in `epa/influx-database` on first successful run of EPA (`make run`). 

**Q:** Where's my Grafana DB? 

**A:** It is created as local Docker volume - see `epa/docker-compose.yml`. 

**Q:** How much memory does each Collector container need? 

**A:** It my testing, less than 32 MiB. It'd take 32 arrays to use 1GiB of RAM (with 32 collector containers).

**Q:** `collector.py` looks messy. 

**A**: Yes. I couldn't spend more time on this. Please improve it and submit a pull request, it will be appreciated.

**Q:** Can I run Collector without containers? 

**A:** Yes. Run collector.py in the sample directory with `-h` or try this with own variables:

```sh
python3 collector/rack26u25-ef600/collector.py \
  -u ${USERNAME} -p ${PASSWORD} \
  --api ${API} \
  --dbAddress ${DB_ADDRESS}:8086 \
  --retention ${RETENTION_PERIOD} \
  --sysname ${SYSNAME} --sysid ${SYSID} \
  -i -s
```

Example for array2 above (remember, `rack15u04-e5760` should correspond to System Name in SANtricity Web UI and the same goes for WWN, to avoid confusion:

```sh
python3 collector/array3/collector.py \
  -u monitor -p monitor123 \
  --api 5.5.5.5 \
  --dbAddress 7.7.7.7:8086 \
  --retention 26w \
  --sysname rack15u04-e5760 \
  --sysid 600A098000F63714000000005E79C888 \
  -i -s
```

**Q:** What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails? 

**A:** You will notice it quickly because you'll stop getting metrics. Then fix the controller or change the setting to the other controller and restart the collector container. It is also possible to use `--api 5.5.5.1 5.5.5.2` to round-robin requests to two controllers. Then if one fails you should see 50% less metric delivered to Grafana, and get a hint. I haven't tried multiple controllers in docker-compose.yaml, but I'd first try `API=5.5.5.1 5.5.5.2`.

**Q:** I tried to run Collector on the same host as EPA InfluxDB and Grafana, and `--dbAddress localhost:8086` (or `DB_ADDRESS=7.7.7.7`) doesn't work. Why? 

**A:** Because InfluxDB is not running on `localhost`, but on `influxdb` (`epa/docker-compose.yaml`). Change the value to `--dbAddress influxdb:8086` (`DB_ADDRESS=influxdb`) when running Collector in Docker on the same host as EPA.

## Walk-through

### Build EPA

- Run `make build` in `epa` and inspect images:

```sh
$ make build 

$ docker images | grep ntap
ntap-grafana/ansible                                 3.0               b5e28ea3de6e   18 minutes ago   384MB
ntap-grafana/influxdb                                3.0               0de6bf41b550   21 minutes ago   173MB
ntap-grafana/alpine-base                             3.0               5510f7cd5042   22 minutes ago   7.05MB
ntap-grafana-plugin/eseries_monitoring/collector     latest            42f2438474b6   23 minutes ago   75.7MB
ntap-grafana-plugin/eseries_monitoring/webservices   latest            6c1b94316eed   23 minutes ago   203MB
ntap-grafana-plugin/eseries_monitoring/alpine-base   latest            5d17de7f905d   23 minutes ago   7.05MB
ntap-grafana/python-base                             3.0               43b56b1ee660   24 minutes ago   50MB
ntap-grafana-plugin/eseries_monitoring/python-base   latest            59f897165fca   6 hours ago      50MB
ntap-grafana/grafana                                 3.0               00af3efd1202   5 weeks ago      287MB
```

- Export collector (ntap-grafana-plugin/eseries_monitoring/collector:latest) image. If you have container registry, you may tag your collector image with own tags and upload to registry.

```sh
$ cd epa
$ make export-plugins

$ ll images/
total 338148
-rw-r--r-- 1 sean sean   7354368 Dec  5 10:41 ntap-grafana-plugin-eseries_monitoring-alpine-base.tar
-rw-r--r-- 1 sean sean  81607680 Dec  5 10:41 ntap-grafana-plugin-eseries_monitoring-collector.tar
-rw-r--r-- 1 sean sean  53046272 Dec  5 10:41 ntap-grafana-plugin-eseries_monitoring-python-base.tar
-rw-r--r-- 1 sean sean 204250624 Dec  5 10:41 ntap-grafana-plugin-eseries_monitoring-webservices.tar
```

- `make run` to start InfluxDB and Grafana. Collector will fail and exit because `docker-compose.yml` in the `epa/plugins/eseries_monitoring` subdirectory has incorrect ENV configuration (that's on purpose, we don't want to run that one). You can leave that container or remove it with `docker rm $CONTAINER_ID`).

```sh
$ cd epa
$ make run 

$ docker ps -a
CONTAINER ID   IMAGE                       COMMAND                  CREATED          STATUS              PORTS                   NAMES
533ace123ec4   collector:latest            "./docker-entrypoint…"   14 seconds ago   Exited (1) 13 seconds ago                                               collector
46c4971c20a6   ntap-grafana/grafana:3.0    "/run.sh"                15 seconds ago   Up 14 seconds       0.0.0.0:3000->3000/tcp  grafana
3af632f3645a   ntap-grafana/influxdb:3.0   "/entrypoint.sh /bin…"   15 seconds ago   Up 14 seconds       0.0.0.0:8086->8086/tcp  influxdb

$ docker rm 533ace123ec4 # remove unnecessary collector container; we just wanted to build the collector image
```

- Notice (`PORTS`, above) that Grafana and InfluxDB ports are open
- Login to Grafana and change its admin password

### Use collector

- Use this cloned repository and work from the `collector` folder.

- Copy `epa/images/ntap-grafana-plugin-eseries_monitoring-collector.tar` to the VM where Collector will run and import the image. If you have uploaded it to internal registry, pull it instead.

```sh
$ docker load ntap-grafana-plugin-eseries_monitoring-collector.tar
Loaded image: ntap-grafana-plugin/eseries_monitoring/collector:latest
```

- In the `collector` folder, edit `docker-compose.yml` as explained earlier. Then start it, first without `-d` to make sure it works, then with `-d`.

```sh
$ docker-compose up
[+] Running 2/0
 ⠿ Network collector_default  Created                              0.0s
 ⠿ Container rack26u25-ef600  Created                              0.0s
0.0s 
Attaching to rack26u25-ef600
rack26u25-ef600  | 2022-12-06 06:16:08,058 - collector - INFO - rack26u25-ef600
rack26u25-ef600  | 2022-12-06 06:16:08,058 - collector - INFO - Collecting system folder information...
rack26u25-ef600  | 2022-12-06 06:16:08,452 - collector - INFO - Time interval: 60.0000 Time to collect and send: 00.3967 Iteration: 1
rack26u25-ef600  | 2022-12-06 06:17:08,134 - collector - INFO - rack26u25-ef600
rack26u25-ef600  | 2022-12-06 06:17:08,380 - collector - INFO - Time interval: 60.0000 Time to collect and send: 00.2645 Iteration: 2
```

- Above we see that our E-Series API is being accessed, array ("folder" is remnant of old WSP function) information sent to InfluxDB and iterations show two successful rounds of collection (enabled with `-i`)
- To stop all Collector containers when `-d` is used, run `docker-compose stop $CONTAINER_NAME`. To stop and *remove* the container, use `down $CONTAINER_NAME`:

```sh
$ docker-compose down
[+] Running 2/0
 ⠿ Container rack26u25-ef600  Removed                              0.0s
 ⠿ Network collector_default  Removed                              0.0s 
```

- If you rebuild the container in VM where you have EPA, you can run `down` as per above to remove old collector container(s), then `up -d` to start them based on latest image.

### Use collector Docker Hub image 

- Let's say you figured out InfluxDB on your own and just want a ready-made collector image that doesn't use WSP. You should build it on your own as explained in Q&A, but if you want a quick try:

```sh
$ docker pull scaleoutsean/epa-collector:v3.0.0
v3.0.0: Pulling from scaleoutsean/epa-collector
Digest: sha256:2ceca8e7a10ad9ddc31bdbf07baeeec843188642d39197b47252df1ac62d012c
Status: Downloaded newer image for scaleoutsean/epa-collector:v3.0.0
docker.io/scaleoutsean/epa-collector:v3.0.0
```

- Go to the collector folder with `cd collector` and edit `docker-compose.yml` to use `image: scaleoutsean/epa-collector:v3.0.0` (not `:latest`)

```yaml
version: '3.6'

services:

  collector-rack26u25-ef600:
    # image: ntap-grafana-plugin/eseries_monitoring/collector:latest 
    image: scaleoutsean/epa-collector:v3.0.0
```

- Edit environment variables (username, password, etc.) and run Collector with `docker-compose up`.

## Sample Grafana screenshots of EPA/Collector dashboards

This fork's dashboards are identical to upstream, but upstream repo has no screenshots - in fact they're hard to find on the Internet - so below shows a sample of each dashboard.

- System view

![E-Series System](/sample-screenshot-epa-collector-system.png)

- Array interfaces

![E-Series Array Interfaces.png](/sample-screenshot-epa-collector-interfaces.png)

- Physical disks 

![E-Series Physical Disks.png](/sample-screenshot-epa-collector-disks.png)

- Logical volumes

![E-Series Volumes.png](/sample-screenshot-epa-collector-volumes.png)

## Component versions

This fork of EPA v3.0.0 was tested with E-Series SANtricity 11.74 and current Docker CE. It should work with other recent SANtricity versions and Docker CE.
