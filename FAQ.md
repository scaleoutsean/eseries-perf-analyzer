## FAQs

Below details are mostly related to this fork. For upstream details please check their README.

- [FAQs](#faqs)
  - [Why do I need to fill in so many details in Collector's YAML file?](#why-do-i-need-to-fill-in-so-many-details-in-collectors-yaml-file)
  - [It's not convenient for me to have multiple storage admins edit `./collector/docker-compose.yml`](#its-not-convenient-for-me-to-have-multiple-storage-admins-edit-collectordocker-composeyml)
  - [How to modify collector Docker image?](#how-to-modify-collector-docker-image)
  - [This looks complicated!](#this-looks-complicated)
  - [Why can't we have one config.json for all monitored arrays?](#why-cant-we-have-one-configjson-for-all-monitored-arrays)
  - [If I have three arrays, two VMs with collectors and these send data to one InfluxDB, do I need to run 1, 2 or 3 dbmanager containers?](#if-i-have-three-arrays-two-vms-with-collectors-and-these-send-data-to-one-influxdb-do-i-need-to-run-1-2-or-3-dbmanager-containers)
  - [What does dbmanager actually do?](#what-does-dbmanager-actually-do)
  - [I have an existing intance of the upstream EPA v3.0.0. Can I add more E-Series arrays without using WSP?](#i-have-an-existing-intance-of-the-upstream-epa-v300-can-i-add-more-e-series-arrays-without-using-wsp)
  - [How can I customize Grafana's options?](#how-can-i-customize-grafanas-options)
  - [What if I run my own InfluxDB v1.8 and Grafana v8? Can I use this Collector without EPA?](#what-if-i-run-my-own-influxdb-v18-and-grafana-v8-can-i-use-this-collector-without-epa)
  - [Where's my InfluxDB data?](#wheres-my-influxdb-data)
  - [Where's my Grafana data? I see nothing when I look at the dashboards!](#wheres-my-grafana-data-i-see-nothing-when-i-look-at-the-dashboards)
  - [How to display temperature and power consumption?](#how-to-display-temperature-and-power-consumption)
  - [How to display SSD wear level?](#how-to-display-ssd-wear-level)
  - [What do temperature sensors measure?](#what-do-temperature-sensors-measure)
- [Why there's six environmental sensor readings, but one PSU figure?](#why-theres-six-environmental-sensor-readings-but-one-psu-figure)
  - [If I use my own Grafana, do I need to recreate EPA dashboards from scratch?](#if-i-use-my-own-grafana-do-i-need-to-recreate-epa-dashboards-from-scratch)
  - [How much memory does each collector container need?](#how-much-memory-does-each-collector-container-need)
  - [How much memory does the dbmanager container need?](#how-much-memory-does-the-dbmanager-container-need)
  - [How to run collector and dbmanager from the CLI?](#how-to-run-collector-and-dbmanager-from-the-cli)
  - [If InfluxDB is re-installed or migrated, how do I restore InfluxDB and Grafana configuration?](#if-influxdb-is-re-installed-or-migrated-how-do-i-restore-influxdb-and-grafana-configuration)
  - [What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails?](#what-happens-if-the-controller-specified-by---api-ipv4-address-or-api-in-docker-composeyml-fails)
  - [Can the E-Series' WWN change?](#can-the-e-series-wwn-change)
  - [How to backup and restore EPA or InfluxDB?](#how-to-backup-and-restore-epa-or-influxdb)
  - [How do temperature alarms work?](#how-do-temperature-alarms-work)
  - [InfluxDB capacity and performance requirements](#influxdb-capacity-and-performance-requirements)


### Why do I need to fill in so many details in Collector's YAML file?

It's a one time activity that lowers the possibility of making a mistake.

### It's not convenient for me to have multiple storage admins edit `./collector/docker-compose.yml` 

The whole point of this fork (and separating collector from the rest) is that centralization can be avoided, so when there's no one "storage team" that manages all arrays, each admin can have their own collector and rotate (and protect) passwords as they see fit.

### How to modify collector Docker image? 

Any way you want. Example: `cp -pr ./collector/collector ./collector/mycollector-v1`, edit container config in the new location, build the container in the new directory using `docker build -t ${NEW_NAME} .`, change `./collector/docker-compose.yml` to use the new Docker image (under `epa/mycollector-v1`), change `./collector/config.json` to make sure dbmanager is aware of the new array name (`SYSNAME`). Finally, run `docker-compose build && docker-compose up $mycollector`. You may modify collector's Makefile to add the new directory.

### This looks complicated!

If you can't handle it, you don't even have to use containers. Install InfluxDB *any way you can/want*, and run collector and dbmanager from the CLI (use `python3 ./collector/collector/collector.py -h` and similar for db_manager.py to see how). Create a data source (InfluxDB) for Grafana, import EPA's dashboards or create your own.

### Why can't we have one config.json for all monitored arrays?

There may be different people managing different arrays. Each can run their own collector and not spend more than 5 minutes to learn what they need to do to get this to work. Each can edit their Docker environment parameters (say, change the password in docker-compose.yaml) without touching InfluxDB and Grafana. dbmanager (config.json) is the only "centralized" service which needs to maintain the list of array names that are being sent to InfluxDB and container no credentials (see `config.json`).

### If I have three arrays, two VMs with collectors and these send data to one InfluxDB, do I need to run 1, 2 or 3 dbmanager containers?

Just one dbmanager is needed if you have one InfluxDB. 

### What does dbmanager actually do?

It sends the list of monitored arrays (`SYSNAME`s) to InfluxDB, that's all. This is used to create a drop-down list of arrays in EPA's Grafana dashboards. 

Prior to v3.1.0 EPA got its list of arrays from the Web Services Proxy so it "knew" which arrays are being monitored. In EPA v3.1.0 and v3.2.0 collector containers may be running in several places and none of them would know what other collectors exist out there. dbmanager maintains a list of all monitored arrays and periodically pushes it to InfluxDB, while dropping other folders (array names which no longer need to be monitored). If you have a better idea or know that's unnecessary, feel free to submit a pull request. InfluxDB v1 is old and this approach is simple and gets the job done.

### I have an existing intance of the upstream EPA v3.0.0. Can I add more E-Series arrays without using WSP?

It could be done, but it's complicated because db_manager.py now drops folder tags for arrays it's not aware of so it'd be too much trouble. Best remove existing EPA and deploy EPA >= v3.1.0. You may be able to retain all InfluxDB data if you used just default folders in WSP and did not change array names (i.e. `SYSNAME` and `SYSID` remain the same as they were in v3.0.0). Grafana dashboards haven't been changed and I won't change them in any future v3, but if you've customized them or added your own, make a backup and make sure it can be restore it to the new deployment before old Grafana is deleted.

### How can I customize Grafana's options?

EPA doesn't change Grafana in any way, so follow the official documentation. If ./epa/grafana/grafana.ini is replaced by ./epa/grafana/grafana.ini.alternative that may provide better privacy (but it also disables notifications related to security and other updates).

### What if I run my own InfluxDB v1.8 and Grafana v8? Can I use this Collector without EPA?

Yes. That's another reason why I made collector.py a stand-alone script without dependencies on the WSP. Just build this fork of EPA and collector container, and then run just collector's docker-compose (no need to run `make run` in the `epa` subdirectory since you already have InfluxDB and Grafana). Or use `collector` and `dbmanager` from the CLI, without containers.

### Where's my InfluxDB data?

It is in the `epa/influx-database` sub-directory and created on first successful run of EPA (`make run`). 

### Where's my Grafana data? I see nothing when I look at the dashboards!

It uses a local Docker volume, see `epa/docker-compose.yml`. Grafana data can't be seen in dashboards until collector successfully runs, and sends data to the `eseries` database in InfluxDB. `dbmanager` also must run to create Influx "folders" (kind of tags) that let you select arrays in EPA's Grafana dashboards. Login to InfluxDB or go to Grafana > Explore to see if Grafana can access InfluxDB and see any data in it. Sometimes data is accessible to Grafana, but collector or dbmanager are misconfigured so dashboards show nothing. Other times the collector has a typo in the password or IP address and can't even access E-Series.

### How to display temperature and power consumption?

Copy one of existing EPA dashboard panels, then edit a panel to change from whatever (`disks`, etc.) to `sensors`. You will likely see six sensors per two array controllers. Sensors 2 and 4 may have the value 128 for "optimal", and non-128 for "not good". The other four are temperature readings in degrees Celsius.

```sql
# TEMP (Celsius)
SELECT last("temp") FROM "temp" WHERE ("sys_name" =~ /^$System$/ AND "sensor" = '0B00000000000000000001000000000000000000') AND $timeFilter GROUP BY time($__interval), "sys_name" fill(none)
SELECT last("temp") FROM "temp" WHERE ("sys_name" =~ /^$System$/ AND "sensor" = '0B00000000000000000003000000000000000000') AND $timeFilter GROUP BY time($__interval), "sys_name" fill(none)
SELECT last("temp") FROM "temp" WHERE ("sys_name" =~ /^$System$/ AND "sensor" = '0B00000000000000000005000000000000000000') AND $timeFilter GROUP BY time($__interval), "sys_name" fill(none)
SELECT last("temp") FROM "temp" WHERE ("sys_name" =~ /^$System$/ AND "sensor" = '0B00000000000000000006000000000000000000') AND $timeFilter GROUP BY time($__interval), "sys_name" fill(none)
# TEMP (128=OK, <>128=NG)
SELECT last("temp") FROM "temp" WHERE ("sys_name" =~ /^$System$/ AND "sensor" = '0B00000000000000000002000000000000000000') AND $timeFilter GROUP BY time($__interval), "sys_name" fill(none)
SELECT last("temp") FROM "temp" WHERE ("sys_name" =~ /^$System$/ AND "sensor" = '0B00000000000000000004000000000000000000') AND $timeFilter GROUP BY time($__interval), "sys_name" fill(none)
# POWER (Watt, total consumption of controller shelf)
SELECT last("totalPower") FROM "power" WHERE ("sys_name" =~ /^$System$/) AND $timeFilter GROUP BY time($__interval), "sys_name" fill(none)
```

See this [sample screenshot](images/sample-screenshot-epa-collector-environmental.png) for a possible visualization.

In Grafana 10 with manual submission from the CLI the query may look slightly different. I didn't look closely but in any case, play in query editor until you see the metrics.

```sql
SELECT mean("temp") FROM "temp" WHERE ("sensor"::tag = '0B00000000000000000001000000000000000000') AND $timeFilter GROUP BY time($__interval) fill(null)
SELECT mean("temp") FROM "temp" WHERE ("sensor"::tag = '0B00000000000000000002000000000000000000') AND $timeFilter GROUP BY time($__interval) fill(null)
SELECT mean("totalPower") FROM "power" WHERE $timeFilter GROUP BY time($__interval) fill(null)
```

### How to display SSD wear level?

The same as above - add a new dashboard or copy existing (this is easier), edit a panel in it, find the SSD wear level metric, and try to visualize it. See this [sample screenshot](images/sample-screenshot-epa-collector-disks-ssd-wear-level.png) for an example.

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

### If I use my own Grafana, do I need to recreate EPA dashboards from scratch?

It is possible to create an InfluxDB data source named "WSP" (name hard-coded in EPA dashboards) and import dashboards from `epa/plugins/eseries_monitoring/dashboards` - see the Kubernetes README for additional information. Grafana 9 and 10 users need to do the same, but may also have to [make minor edits](https://github.com/grafana/grafana/discussions/45230) to EPA's Grafana 8 dashboards.

### How much memory does each collector container need? 

It my testing, much less than 32 MiB. It'd take 32 arrays to use 1GiB of RAM (with 32 collector containers).

### How much memory does the dbmanager container need? 

We need just one container per InfluxDB and it needs less than 20 MiB. 32 MiB is more than enough.

### How to run collector and dbmanager from the CLI? 

Run `db_manager.py -h` and `collector.py -h`. Example for the latter:

```sh
python3 ./collector/collector/collector.py \
  -u ${USERNAME} -p ${PASSWORD} \
  --api ${API} \
  --dbAddress ${DB_ADDRESS}:8086 \
  --retention ${RETENTION_PERIOD} \
  --sysname ${SYSNAME} --sysid ${SYSID} \
  -i -s
```

### If InfluxDB is re-installed or migrated, how do I restore InfluxDB and Grafana configuration?

dbmanager will re-create the eseries database if it doesn't exist. The Grafana data source ("WSP") can be changed manually or removed and recreated using the EPA Ansible container as suggested in the README files for Docker and Kubernetes.

### What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails? 

You will notice it quickly because you'll stop getting metrics. Then fix the controller or change the setting to use the other controller and restart collector. It is also possible to use `--api 5.5.5.1 5.5.5.2` to round-robin collector requests to two controllers. If one fails you should get 50% less frequent metric delivery to Grafana, and get a hint. Or, set `API=5.5.5.1 5.5.5.2` in docker-compose.yaml. This hasn't been tested a lot, but it appears to work.

### Can the E-Series' WWN change?

Normally it can't, but it's theoretically [possible](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/E-Series_SANtricity_Software_Suite/WWNs_changed_after_offline_replacement_of_tray_0). Should that happen you'd have to update your configuration and restart collector container affected by this change.

WWN is required because E-Series array names change more frequently and can even be duplicate, so WWN provides the measurements with consistency.

### How to backup and restore EPA or InfluxDB?

- Backup software: use software such as [Astra Control](https://docs.netapp.com/us-en/astra-control-center/) (if you store EPA data on ONTAP), [Kasten K10](https://scaleoutsean.github.io/2023/02/10/backup-epa-data-on-kubernetes.html) or [Velero](https://scaleoutsean.github.io/2022/03/15/velero-18-with-restic-and-trident-2201.html). If your backup approach has no application-aware snapshot integration, you may want to scale-down InfluxDB to 0 in order to get a consistent PV snapshot, and then back to 1
  - Velero: prepare your environment and use something like `velero backup create epa-influxdb-backup --include-namespaces epa`
- Manual backup: considering that Grafana itself may not have a lot of data, and InfluxDB can be backed up with InfluxDB client, shell script that uses InfluxDB client and the copy or rsync command can be used to dump data out and restore it later. Note that you may need to also dump/backup Grafana config, PVC configuration, InfluxDB secrets, and the rest
- Cold backup and single-volume InfluxDB: if your backup application does not support consistency group snapshots and you use multiple PVCs for InfluxDB, it is better to take a cold backup. Alternatively, take one cold backup using InfluxDB client, re-provision InfluxDB with a single PVC, restore data to it, and then hot crash-consistent backups will be more reliable

### How do temperature alarms work?

For the inlet sensor a warning message should be sent at 35C, and a critical message should be sent at 40C. I don't know about the CPU temperature sensor.

### InfluxDB capacity and performance requirements

Performance requirements should be insignificant even for several arrays. If InfluxDB is on flash storage, any will do.

Capacity requirements depend on the number of arrays, disks and volumes (LUNs). With a small EF570 (24 disks, 10 volumes) collected every 60s, InfluxDB grew 1 MB per day.
