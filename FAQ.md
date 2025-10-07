# FAQs

Below details are mostly related to this fork. For upstream details please check their README.

- [FAQs](#faqs)
  - [Why do I need to fill in so many details in Collector's YAML file?](#why-do-i-need-to-fill-in-so-many-details-in-collectors-yaml-file)
  - [It's not convenient for me to have multiple storage admins edit the same `./epa/docker-compose.yml`](#its-not-convenient-for-me-to-have-multiple-storage-admins-edit-the-same-epadocker-composeyml)
  - [How can I customize Grafana's options?](#how-can-i-customize-grafanas-options)
  - [What if I run my own InfluxDB v1 and Grafana? Can I use this Collector without EPA?](#what-if-i-run-my-own-influxdb-v1-and-grafana-can-i-use-this-collector-without-epa)
  - [How can I protect EPA's InfluxDB from unauthorized access?](#how-can-i-protect-epas-influxdb-from-unauthorized-access)
  - [Where's my InfluxDB data?](#wheres-my-influxdb-data)
  - [Where's my Grafana data? I see nothing when I look at the dashboards!](#wheres-my-grafana-data-i-see-nothing-when-i-look-at-the-dashboards)
  - [What do temperature sensors measure?](#what-do-temperature-sensors-measure)
  - [Why there's six environmental sensor readings, but one PSU figure?](#why-theres-six-environmental-sensor-readings-but-one-psu-figure)
  - [How to get more details about Major Event Log entries?](#how-to-get-more-details-about-major-event-log-entries)
  - [How to get interface error metrics?](#how-to-get-interface-error-metrics)
  - [If I use my own Grafana, do I need to recreate EPA dashboards from scratch?](#if-i-use-my-own-grafana-do-i-need-to-recreate-epa-dashboards-from-scratch)
  - [How to query InfluxDB schema?](#how-to-query-influxdb-schema)
    - [What are those `repos_<three-digits>` volumes in my `config_volumes` table?](#what-are-those-repos_three-digits-volumes-in-my-config_volumes-table)
  - [How much memory does each collector container need?](#how-much-memory-does-each-collector-container-need)
  - [How to upgrade?](#how-to-upgrade)
  - [If InfluxDB is re-installed or migrated, how do I restore InfluxDB and Grafana configuration?](#if-influxdb-is-re-installed-or-migrated-how-do-i-restore-influxdb-and-grafana-configuration)
  - [What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails?](#what-happens-if-the-controller-specified-by---api-ipv4-address-or-api-in-docker-composeyml-fails)
  - [Can the E-Series' WWN change?](#can-the-e-series-wwn-change)
  - [How to backup and restore EPA or InfluxDB?](#how-to-backup-and-restore-epa-or-influxdb)
  - [How do temperature alarms work?](#how-do-temperature-alarms-work)
  - [InfluxDB capacity and performance requirements](#influxdb-capacity-and-performance-requirements)

## Why do I need to fill in so many details in Collector's YAML file?

It's a one time activity that lowers the possibility of making a mistake.

## It's not convenient for me to have multiple storage admins edit the same `./epa/docker-compose.yml`

You can have each administrator have their own docker-compose.yaml or indeed, run EPA collector from the CLI.

They just need to be able to reach the same InfluxDB (and even that is only if you want to provide a centralized database).

## How can I customize Grafana's options?

EPA doesn't change Grafana in any way, so follow the official Grafana documentation.

## What if I run my own InfluxDB v1 and Grafana? Can I use this Collector without EPA?

Yes. That's another reason why I made collector.py a stand-alone script without dependencies on the WSP. Just build this fork of EPA and collector container, and then run just `docker compose up collector`.

Reference dashboards are in `./epa/grafana-init/dashboards/` and you may need to update them for Grafana other than version 8.

## How can I protect EPA's InfluxDB from unauthorized access?

Within Docker Compose, EPA containers are on own network. Externally, add firewall rules to prevent unrelated clients from accessing InfluxDB.

```sh
iptables -A INPUT -p tcp --dport 8086 -s <collector-ip> -j ACCEPT
iptables -A INPUT -p tcp --dport 8086 -j DROP
```

If you need much better security, consider [InfluxDB 3](https://github.com/scaleoutsean/eseries-santricity-collector).

## Where's my InfluxDB data?

By default:

- EPA 3.5: it is  is the volume created by `./epa/setup-data-dirs.sh`
- EPA 3.4: it is in a "named" Docker volume (use `docker volume ls` to see it). If you want to evacuate it, you may use `./epa/setup-data-dirs.sh`

An easy way to evacuate/move InfluxDB v1 data is with backup/restore command.

## Where's my Grafana data? I see nothing when I look at the dashboards!

Use the Explore feature in Grafana, and if that doesn't let you see anything, check Data Source, and finally, try the `utils` container (see `./epa/utils/README.txt`) or `curl` to InfluxDB's HTTP API endpoint.

## What do temperature sensors measure?

The ones we have seen represent the following:

- CPU temperature in degrees C - usually >50C
- Controller shelf's inlet temperature in degrees C - usually between 20-30C
- "Overall" temperature status as binary indicator - 128 if OK, and not 128 if not OK, so this one probably doesn't need a chart but some indicator that alerts if the value is *not* 128

## Why there's six environmental sensor readings, but one PSU figure?

Sensors: I suppose it's 2 per each controller, as per the list above, one per each controller gives you six. These can't be averaged or "merged", so collector keeps them separate.

PSU: the API indeed provides two readings, but I decided to add them up because there's little value in looking per-PSU power consumption (especially since auto-rebalancing may move volumes around, causing visible changes in power consumption that have nothing to do with the PSU itself). Feel free to change the code if you want to watch them separately. Personally I couldn't imagine a scenario in which retaining both wouldn't be waste of space.

Important detail about limitations:

- Sensors: I've no idea if all E-Series models have 3 sensors per controller, and in what order (which is why I gave approximate values that you may expect from each kind). I also don't know if their names (e.g. 0B00000000000000000002000000000000000000) are consistent across E- and EF-Series models
- Expansion shelves: I don't have access to E-Series with expansion enclosures and have no idea what the API returns for those, so in v3.3.0 collector does not collect total power consumption of the entire *array*. Later releases may collect everything they find

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

## If I use my own Grafana, do I need to recreate EPA dashboards from scratch?

No, you may import them from `./epa/grafana-init/dashboards`.

## How to query InfluxDB schema?

You may start and enter `utils` container and do it from there. Externally, you can run it like this example below, or install InfluxDB v1 and use it as client.

```sh
docker exec utils influx -host influxdb -port 8086 -database eseries -execute "SHOW FIELD KEYS FROM config_drives"

docker exec utils influx -host influxdb -port 8086 -database eseries -execute "SHOW TAG KEYS FROM config_drives"
```

### What are those `repos_<three-digits>` volumes in my `config_volumes` table?

You may see them if you have snapshot reserves and such.

See [this](https://scaleoutsean.github.io/2023/10/05/snapshots-and-consistency-groups-with-netapp-e-series.html#appendix-c---repository-utilization) and similar content for related information.

## How much memory does each collector container need?

It my testing, much less than 32 MiB (average, 21 MiB). It'd take 32 arrays to use 1GiB of RAM (with 32 collector containers).

However, EPA's RAM utilization may spike when it processes very large JSON objects, so if you need set a maximum upper RAM resource limit, you may set it to 256 MiB. That should handle any short-lived spikes.

## How to upgrade?

From 3.[1,2,3] to 3.4 or newer version 3, I wouldn't try since there aren't new features. But if you want to, then I recommend removing old setup and starting from scratch. Or, if you insist, you could transplant Collector from `./epa/collector/` and also copy its Docker Compose service to the "old" `./collector/collector/docker-compose.yaml`, and leave InfluxDB and Grafana alone. That is quick, easy to do and easy to revert.

EPA 3.4.0's `./epa/docker-compose.yaml` has changes, from versions to volumes and so on, that it's unlikely that older versions can be upgraded in place and without any trouble.

EPA 3.5.0 doesn't have a changes compared to 3.4, but it has new "tables". Upgrade should be possible.

## If InfluxDB is re-installed or migrated, how do I restore InfluxDB and Grafana configuration?

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

To restore a DB, you can start a new InfluxDB instance with a volume mount `./dump:/dump` and restore from it:

```sh
docker-compose exec influxdb influxd restore -portable -database eseries /dump/
```

## What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails?

You will notice it quickly because you'll stop getting metrics. Then fix the controller or change the setting to use the other controller and restart collector. It is also possible to use `--api 5.5.5.1 5.5.5.2` to have Collector round-robin collector requests to two controllers. If one fails you should get 50% less frequent metric delivery to Grafana, and get a hint. Or, set `API=5.5.5.1 5.5.5.2` in `docker-compose.yaml`.

## Can the E-Series' WWN change?

Normally it can't, but it's theoretically [possible](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/E-Series_SANtricity_Software_Suite/WWNs_changed_after_offline_replacement_of_tray_0). Should that happen you'd have to update your configuration and restart collector container affected by this change.

WWN is required because E-Series array names change more frequently and can even be duplicate, so WWN provides the measurements with consistency.

## How to backup and restore EPA or InfluxDB?

- Mount a backup volume to the `utils` container
- Use `influxdb` native backup command to dump DB to that volume
- To restore, do the same with `inflxudb` container: mount the same volume, restore from that path

## How do temperature alarms work?

For the inlet sensor a warning message should be sent at 35C, and a critical message should be sent at 40C. I don't know about the CPU temperature sensor.

## InfluxDB capacity and performance requirements

Performance requirements should be modest even for several arrays. If InfluxDB is on flash storage, any will do. 

Capacity requirements depend on the number of arrays, disks and volumes (LUNs). With a small EF570 (24 disks, 10 volumes) collected every 60s, you may need up to several GB/month.

Anecdotally, v3.5.0 (this includes the extra configuration metrics) collecting 2 arrays, each with 12 disks and about 6 volumes:

- 1 hour of collection 5 MB (60 collections of performance, MEL and failures, and four of various configuration metrics which by default run every 15 min)
- This amounts less than 1 GB/month or ~500 MB/mo for a small array

For many arrays or volumes, showing weeks at once may benefit from more RAM given to Grafana, but you can evaluate that based on your use case.
