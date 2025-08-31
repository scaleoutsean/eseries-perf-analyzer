## FAQs

Below details are mostly related to this fork. For upstream details please check their README.

- [FAQs](#faqs)
  - [Why do I need to fill in so many details in Collector's YAML file?](#why-do-i-need-to-fill-in-so-many-details-in-collectors-yaml-file)
  - [It's not convenient for me to have multiple storage admins edit the same `./epa/docker-compose.yml`](#its-not-convenient-for-me-to-have-multiple-storage-admins-edit-the-same-epadocker-composeyml)
  - [This looks complicated!](#this-looks-complicated)
  - [How can I customize Grafana's options?](#how-can-i-customize-grafanas-options)
  - [What if I run my own InfluxDB v1 and Grafana v8? Can I use this Collector without EPA?](#what-if-i-run-my-own-influxdb-v1-and-grafana-v8-can-i-use-this-collector-without-epa)
  - [Where's my InfluxDB data?](#wheres-my-influxdb-data)
  - [Where's my Grafana data? I see nothing when I look at the dashboards!](#wheres-my-grafana-data-i-see-nothing-when-i-look-at-the-dashboards)
  - [What do temperature sensors measure?](#what-do-temperature-sensors-measure)
- [Why there's six environmental sensor readings, but one PSU figure?](#why-theres-six-environmental-sensor-readings-but-one-psu-figure)
  - [If I use my own Grafana, do I need to recreate EPA dashboards from scratch?](#if-i-use-my-own-grafana-do-i-need-to-recreate-epa-dashboards-from-scratch)
  - [How much memory does each collector container need?](#how-much-memory-does-each-collector-container-need)
  - [How much memory does the dbmanager container need?](#how-much-memory-does-the-dbmanager-container-need)
  - [How to run collector and dbmanager from the CLI?](#how-to-run-collector-and-dbmanager-from-the-cli)
  - [How to upgrade?](#how-to-upgrade)
  - [If InfluxDB is re-installed or migrated, how do I restore InfluxDB and Grafana configuration?](#if-influxdb-is-re-installed-or-migrated-how-do-i-restore-influxdb-and-grafana-configuration)
  - [What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails?](#what-happens-if-the-controller-specified-by---api-ipv4-address-or-api-in-docker-composeyml-fails)
  - [Can the E-Series' WWN change?](#can-the-e-series-wwn-change)
  - [How to backup and restore EPA or InfluxDB?](#how-to-backup-and-restore-epa-or-influxdb)
  - [How do temperature alarms work?](#how-do-temperature-alarms-work)
  - [InfluxDB capacity and performance requirements](#influxdb-capacity-and-performance-requirements)


### Why do I need to fill in so many details in Collector's YAML file?

It's a one time activity that lowers the possibility of making a mistake.

### It's not convenient for me to have multiple storage admins edit the same `./epa/docker-compose.yml` 

You can have each administrator have their own docker-compose.yaml or indeed, run EPA collector from the CLI. 

They just need to be able to reach the same InfluxDB (and even that is only if you want to provide a centralized database).

### This looks complicated!

If you can't handle it, you don't even have to use containers. Install InfluxDB *any way you can/want*, and run collector and dbmanager from the CLI (use `python3 ./collector/collector/collector.py -h` and similar for db_manager.py to see how). Create a data source (InfluxDB) for Grafana, import EPA's dashboards or create your own.

### How can I customize Grafana's options?

EPA doesn't change Grafana in any way, so follow the official documentation. If ./epa/grafana/grafana.ini is replaced by ./epa/grafana/grafana.ini.alternative that may provide better privacy (but it also disables notifications related to security and other updates).

### What if I run my own InfluxDB v1 and Grafana v8? Can I use this Collector without EPA?

Yes. That's another reason why I made collector.py a stand-alone script without dependencies on the WSP. Just build this fork of EPA and collector container, and then run just `docker compose up collector`.

### Where's my InfluxDB data?

It is in the "named" Docker volume. If you want to evacuate it, you use a subdirectory such as `./epa/influx-data` but remember to `chown -R 1500:1500 ./epa/influx-data` in that case.

### Where's my Grafana data? I see nothing when I look at the dashboards!

Use the Explore feature in Grafana, and if that doesn't let you see anything, check Data Source, and finally, try the `utils` container (see `./epa/utils/README.txt`) or `curl` to InfluxDB's HTTP API endpoint. 

### What do temperature sensors measure?

The ones we capture (EF570, E2800) represent the following:

- CPU temperature in degrees C - usually >50C
- Controller shelf's inlet temperature in degrees C - usually between 20-30C
- "Overall" temperature status as binary indicator - 128 if OK, and not 128 if not OK, so this one probably doesn't need a chart but some indicator that alerts if the value is not 128

## Why there's six environmental sensor readings, but one PSU figure?

Sensors: I suppose it's 2 per each controller, as per the list above, one per each controller gives you six. These can't be averaged or "merged", so collector keeps them separate.

PSU: the API indeed provides two readings, but I decided to add them up because there's little value in looking per-PSU power consumption (especially since auto-rebalancing may move volumes around, causing visible changes in power consumption that have nothing to do with the PSU itself). Feel free to change the code if you want to watch them separately. Personally I couldn't imagine a scenarion in which retaining both wouldn't be waste of space.

Important detail about limitations:
- Sensors: I've no idea if all E-Series models have 3 sensors per controller, and in what order (which is why I gave approximate values that you may expect from each kind). I also don't know if their names (e.g. 0B00000000000000000002000000000000000000) are consistent across E- and EF-Series models
- Expansion shelves: I don't have access to E-Series with expansion enclosures and have no idea what the API returns for those, so in v3.3.0 collector does not collect total power consumption of the entire *array*

## How to get more details about Major Event Log entries?

You may create a panel with a table (rather than chart) and see how you want to filter it (e.g. last 24 hours or some other condition(s)).

```sql
SELECT "description", "id", "location" FROM "major_event_log"
```

## How to get interface error metrics?

Check `channelErrorCounts` in the `interface` measurement.

```sql
SELECT mean("channelErrorCounts") FROM "interface" WHERE $timeFilter GROUP BY time($__interval), "sys_name" fill(none)
```

There may be some other places, but that could be the main one. I didn't see anything but 0 (no errors) in my InfluxDB, so I can't say it works for sure.

### If I use my own Grafana, do I need to recreate EPA dashboards from scratch?

No, you may import them from epa/grafana-init/dashboards.

### How much memory does each collector container need? 

It my testing, much less than 32 MiB (average, 21 MiB). It'd take 32 arrays to use 1GiB of RAM (with 32 collector containers). 

However, EPA's RAM utilization may spike when it processes very large JSON, so if you need set a maximum uppper RAM resource limit, you may set it to 256 MiB. That should handle any short-lived spikes. 

### How much memory does the dbmanager container need? 

We need just one container per InfluxDB and it needs less than 20 MiB. 32 MiB is more than enough.

### How to run collector and dbmanager from the CLI? 

Example for Collector:

```sh
python3 ./epa/collector/collector.py \
  -u ${USERNAME} -p ${PASSWORD} \
  --api ${API} \
  --dbAddress ${DB_ADDRESS}:8086 \
  --retention ${RETENTION_PERIOD} \
  --sysname ${SYSNAME} --sysid ${SYSID} \
  -i -s
```

### How to upgrade?

From 3.[1,2,3] to 3.4 or newer version 3, I wouldn't try since there aren't new features. But if you want to, then I recommend removing old setup and starting from scratch. Or, if you insist, you could transplant Collector from `./epa/collector/` and also copy its Docker Compose service to the "old" `./collector/collector/docker-compose.yaml`, and leave InfluxDB and Grafana alone. That is quick, easy to do and easy to revert.

EPA 3.4.0's `./epa/docker-compose.yaml` has changes, from versions to volumes and so on, that it's unlikely that older versions can be upgraded in place and without any trouble.

### If InfluxDB is re-installed or migrated, how do I restore InfluxDB and Grafana configuration?

EPA Collector creates database automatically: `--dbName` parameter if specified, `eseries` if not. So you can just run Collector. 

Or you can create the DB before you run.

- Using the `collector` container (mind the container name and version!):

```sh
docker run --rm --network eseries_perf_analyzer \
  -e CREATE_DB=true -e DB_NAME=eseries -e DB_ADDRESS=influxdb -e DB_PORT=8086 \
  epa/collector:3.5.0
```

- Using the `utils` container:

```sh
# if you prefer to use InfluxDB v1 CLI
docker compose up -d utils
# enter the container
docker exec -u 0 -it utils /bin/sh
# inside of the utils container
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'SHOW DATABASES'
# create database (or several). EPA defaults to "eseries"
influx -host "${INFLUX_HOST:-influxdb}" -port "${INFLUX_PORT:-8086}" -execute 'CREATE DATABASE eseries'
exit
```

To restore default configuration to Grafana, deploy Grafana, run `grafana-init` once (configures Grafana Data Source, pushes dashboards to Grafana) and finally start EPA Collector.

### What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails? 

You will notice it quickly because you'll stop getting metrics. Then fix the controller or change the setting to use the other controller and restart collector. It is also possible to use `--api 5.5.5.1 5.5.5.2` to round-robin collector requests to two controllers. If one fails you should get 50% less frequent metric delivery to Grafana, and get a hint. Or, set `API=5.5.5.1 5.5.5.2` in docker-compose.yaml. This hasn't been tested a lot, but it appears to work.

### Can the E-Series' WWN change?

Normally it can't, but it's theoretically [possible](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/E-Series_SANtricity_Software_Suite/WWNs_changed_after_offline_replacement_of_tray_0). Should that happen you'd have to update your configuration and restart collector container affected by this change.

WWN is required because E-Series array names change more frequently and can even be duplicate, so WWN provides the measurements with consistency.

### How to backup and restore EPA or InfluxDB?

- Backup software: use software such as [Astra Control](https://docs.netapp.com/us-en/astra-control-center/) (if you store EPA data on ONTAP), [Kasten K10](https://scaleoutsean.github.io/2023/02/10/backup-epa-data-on-kubernetes.html) or [Velero](https://scaleoutsean.github.io/2022/03/15/velero-18-with-restic-and-trident-2201.html). If your backup approach has no application-aware snapshot integration, you may want to scale-down InfluxDB to 0 in order to get a consistent PV snapshot, and then back to 1
  - Velero: prepare your environment and use something like `velero backup create epa-influxdb-backup --include-namespaces epa`
- Manual backup: considering that Grafana itself may not have a lot of data, and InfluxDB can be backed up with InfluxDB client, shell script that uses InfluxDB client and the copy or `rsync` command can be used to dump data out and restore it later. Note that you may need to also dump/backup Grafana config, PVC configuration, InfluxDB secrets, and the rest
- Cold backup and single-volume InfluxDB: if your backup application does not support consistency group snapshots and you use multiple PVCs for InfluxDB, it is better to take a cold backup. Alternatively, take one cold backup using InfluxDB client, re-provision InfluxDB with a single PVC, restore data to it, and then hot crash-consistent backups will be more reliable

### How do temperature alarms work?

For the inlet sensor a warning message should be sent at 35C, and a critical message should be sent at 40C. I don't know about the CPU temperature sensor.

### InfluxDB capacity and performance requirements

Performance requirements should be insignificant even for several arrays. If InfluxDB is on flash storage, any will do.

Capacity requirements depend on the number of arrays, disks and volumes (LUNs). With a small EF570 (24 disks, 10 volumes) collected every 60s, you may need several GB/month.
