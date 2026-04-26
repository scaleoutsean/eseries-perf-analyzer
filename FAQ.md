# FAQs

- [FAQs](#faqs)
  - [EPA 4](#epa-4)
    - [What's the main difference compared to EPA 3?](#whats-the-main-difference-compared-to-epa-3)
    - [What's recommended - EPA 4 or EPA 3?](#whats-recommended---epa-4-or-epa-3)
    - [Where can I see list of supported metrics?](#where-can-i-see-list-of-supported-metrics)
  - [EPA 3](#epa-3)
    - [Is EPA 3 still maintained?](#is-epa-3-still-maintained)
    - [Why do I need to fill in so many details in Collector's YAML file?](#why-do-i-need-to-fill-in-so-many-details-in-collectors-yaml-file)
    - [It's not convenient for me to have multiple storage admins edit the same `./epa/docker-compose.yml`](#its-not-convenient-for-me-to-have-multiple-storage-admins-edit-the-same-epadocker-composeyml)
    - [How can I customize Grafana's options?](#how-can-i-customize-grafanas-options)
    - [What if I run my own InfluxDB v1 and Grafana? Can I use this Collector without EPA?](#what-if-i-run-my-own-influxdb-v1-and-grafana-can-i-use-this-collector-without-epa)
    - [How can I protect EPA's InfluxDB from unauthorized access?](#how-can-i-protect-epas-influxdb-from-unauthorized-access)
    - [Where's my InfluxDB data?](#wheres-my-influxdb-data)
    - [Where's my Grafana data? I see nothing when I look at the dashboards!](#wheres-my-grafana-data-i-see-nothing-when-i-look-at-the-dashboards)
    - [What do temperature sensors measure?](#what-do-temperature-sensors-measure)
    - [Why there's just one PSU figure when there are two (or more) power supply units?](#why-theres-just-one-psu-figure-when-there-are-two-or-more-power-supply-units)
    - [How to get more details about Major Event Log entries?](#how-to-get-more-details-about-major-event-log-entries)
    - [How to get interface error metrics?](#how-to-get-interface-error-metrics)
    - [If I use my own Grafana, do I need to recreate EPA dashboards from scratch?](#if-i-use-my-own-grafana-do-i-need-to-recreate-epa-dashboards-from-scratch)
    - [How to query InfluxDB schema?](#how-to-query-influxdb-schema)
    - [What are those `repos_<three-digits>` volumes in my `config_volumes` table?](#what-are-those-repos_three-digits-volumes-in-my-config_volumes-table)
    - [How much memory does each collector container need?](#how-much-memory-does-each-collector-container-need)
    - [How to upgrade an EPA 3?](#how-to-upgrade-an-epa-3)
    - [If InfluxDB is re-installed or migrated, how do I restore InfluxDB and Grafana configuration?](#if-influxdb-is-re-installed-or-migrated-how-do-i-restore-influxdb-and-grafana-configuration)
    - [What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails?](#what-happens-if-the-controller-specified-by---api-ipv4-address-or-api-in-docker-composeyml-fails)
    - [Can the E-Series' WWN change?](#can-the-e-series-wwn-change)
    - [How to backup and restore EPA or InfluxDB?](#how-to-backup-and-restore-epa-or-influxdb)
    - [What's the difference between Ops and IOPs?](#whats-the-difference-between-ops-and-iops)
    - [How do temperature alarms work?](#how-do-temperature-alarms-work)
    - [InfluxDB capacity and performance requirements](#influxdb-capacity-and-performance-requirements)
    - [How to use the capture feature](#how-to-use-the-capture-feature)

## EPA 4

### What's the main difference compared to EPA 3?

EPA 4 removes database from the picture and retains only Prometheus metrics (which most people didn't even know about, but they've been available for a while). See more about other differences and reasons behind changes [here](https://scaleoutsean.github.io/2026/04/23/epa_400_beta.html).

### What's recommended - EPA 4 or EPA 3?

EPA 4 is recommended - it certainly takes less time to install and figure out.

### Where can I see list of supported metrics?

You can run collector and see with `curl http://localhost:9080/metrics`.

Example from 4.0.0beta1:

```sh
# HELP epa_scrape_duration_seconds Time spent scraping SANtricity
# HELP epa_scrape_duration_seconds_created Time spent scraping SANtricity
# HELP epa_scrape_errors_total Number of failures during collection
# HELP epa_metrics_generated_total Number of metrics successfully generated
# HELP eseries_disk_iops_total Total IOPS for disk
# HELP eseries_disk_throughput_bytes_per_second Disk throughput in bytes/sec
# HELP eseries_disk_response_time_seconds Disk response time in seconds
# HELP eseries_disk_ssd_wear_percent SSD wear level percentage
# HELP eseries_controller_iops_total Controller IOPS
# HELP eseries_controller_throughput_bytes_per_second Controller throughput in bytes/sec
# HELP eseries_controller_cpu_utilization_percent Controller CPU utilization
# HELP eseries_controller_cache_hit_percent Controller cache hit percentage
# HELP eseries_volume_iops_total Volume IOPS
# HELP eseries_volume_throughput_bytes_per_second Volume throughput in bytes/sec
# HELP eseries_volume_response_time_seconds Volume response time in seconds
# HELP eseries_epa_status EPA collector status (1=OK, 0=Error/Unreachable)
# HELP eseries_interface_iops_total Interface IOPS
# HELP eseries_interface_throughput_bytes_per_second Interface throughput in bytes/sec
# HELP eseries_interface_queue_depth Interface queue depth
# HELP eseries_power_consumption_watts Total power consumption in watts
# HELP eseries_temperature_celsius Temperature in Celsius
# HELP eseries_flashcache_bytes Flash Cache byte metrics
# HELP eseries_flashcache_blocks_total Flash Cache block metrics (delta)
# HELP eseries_flashcache_ops_total Flash Cache operations (delta)
# HELP eseries_flashcache_components Flash Cache related component counts
# HELP eseries_active_failures_total Number of active failures
# HELP eseries_volume_info Volume configuration info
# HELP eseries_volume_capacity_bytes Volume capacity in bytes
# HELP eseries_volume_total_size_bytes Volume total size in bytes
# HELP eseries_storage_pool_info Storage pool configuration info
# HELP eseries_storage_pool_free_space_bytes Storage pool free space in bytes
# HELP eseries_storage_pool_used_space_bytes Storage pool used space in bytes
# HELP eseries_storage_pool_total_raided_space_bytes Storage pool total raided space in bytes
# HELP eseries_host_group_info Host group configuration info
# HELP eseries_host_info Host configuration info
# HELP eseries_drive_info Drive configuration info
# HELP eseries_drive_raw_capacity_bytes Drive raw capacity in bytes
# HELP eseries_drive_usable_capacity_bytes Drive usable capacity in bytes
# HELP eseries_controller_info Controller configuration info
# HELP eseries_interface_info Interface configuration info
# HELP eseries_system_info System configuration info
# HELP eseries_system_drive_count System metric drive_count
# HELP eseries_system_tray_count System metric tray_count
# HELP eseries_system_used_pool_space System metric used_pool_space
# HELP eseries_system_free_pool_space System metric free_pool_space
# HELP eseries_system_unconfigured_space System metric unconfigured_space
# HELP eseries_system_hot_spare_count System metric hot_spare_count
# HELP eseries_system_host_spares_used System metric host_spares_used
# HELP eseries_system_media_scan_period_days System metric media_scan_period_days
# HELP eseries_system_defined_partition_count System metric defined_partition_count
# HELP eseries_system_unconfigured_space_bytes System metric unconfigured_space_bytes
# HELP eseries_system_free_pool_space_bytes System metric free_pool_space_bytes
# HELP eseries_system_hot_spare_size_bytes System metric hot_spare_size_bytes
# HELP eseries_system_used_pool_space_bytes System metric used_pool_space_bytes
# HELP eseries_interface_alert Interface alert status (1=down, 0=ok)
# HELP eseries_consistency_group_info Consistency group info info
# HELP eseries_repository_info Repository info info
# HELP eseries_repository_aggregate_capacity_bytes Repository info - aggregate_capacity_bytes
# HELP eseries_snapshot_group_info Snapshot group info info
# HELP eseries_snapshot_group_repository_capacity_bytes Snapshot group info - repository_capacity_bytes
# HELP eseries_snapshot_image_info Snapshot image info info
# HELP eseries_snapshot_image_pit_capacity_bytes Snapshot image info - pit_capacity_bytes
# HELP eseries_snapshot_image_pit_sequence_number Snapshot image info - pit_sequence_number
# HELP eseries_snapshot_image_pit_timestamp Snapshot image info - pit_timestamp
# HELP eseries_snapshot_image_repository_capacity_utilization_percent Snapshot image info - repository_capacity_utilization_percent
# HELP eseries_snapshot_volume_info Snapshot volume info info
# HELP eseries_snapshot_volume_base_volume_capacity_bytes Snapshot volume info - base_volume_capacity_bytes
# HELP eseries_snapshot_volume_repository_capacity_bytes Snapshot volume info - repository_capacity_bytes
# HELP eseries_snapshot_volume_total_size_in_bytes Snapshot volume info - total_size_in_bytes
# HELP eseries_snapshot_volume_view_sequence_number Snapshot volume info - view_sequence_number
# HELP eseries_snapshot_volume_view_time Snapshot volume info - view_time
# HELP eseries_snapshot_group_utilization_info Snapshot group utilization info
# HELP eseries_snapshot_group_utilization_pit_group_bytes_used Snapshot group utilization - pit_group_bytes_used
# HELP eseries_snapshot_group_utilization_pit_group_bytes_available Snapshot group utilization - pit_group_bytes_available
# HELP eseries_snapshot_volume_utilization_info Snapshot volume utilization info
# HELP eseries_snapshot_volume_utilization_view_bytes_used Snapshot volume utilization - view_bytes_used
# HELP eseries_snapshot_volume_utilization_view_bytes_available Snapshot volume utilization - view_bytes_available
# HELP eseries_consistency_group_member_info CG member info info
# HELP eseries_snapshot_schedule_info Snapshot schedule info info
# HELP eseries_snapshot_schedule_creation_time Snapshot schedule info - creation_time
# HELP eseries_snapshot_schedule_last_run_time Snapshot schedule info - last_run_time
# HELP eseries_snapshot_schedule_next_run_time Snapshot schedule info - next_run_time
# HELP eseries_snapshot_schedule_stop_time Snapshot schedule info - stop_time
# HELP eseries_snapshot_schedule_schedule_start_date Snapshot schedule info - schedule_start_date
```

## EPA 3

### Is EPA 3 still maintained?

Yes. Bug reports are accepted and issues will be worked on, although it's really maintenance-free. Just update 3rd party dependencies in ./epa/collector/requirements.txt and rebuild. EPA 3 seems to work fine with SANtricity 12, but if anyone notices a bug related to SANtricty 12 differences, it will be fixed.

### Why do I need to fill in so many details in Collector's YAML file?

It's a one time activity that lowers the possibility of making a mistake.

### It's not convenient for me to have multiple storage admins edit the same `./epa/docker-compose.yml`

You can have each administrator have their own docker-compose.yaml or indeed, run EPA collector from the CLI.

They just need to be able to reach the same InfluxDB (and even that is only if you want to provide a centralized database).

### How can I customize Grafana's options?

EPA doesn't change Grafana in any way, so follow the official Grafana documentation.

### What if I run my own InfluxDB v1 and Grafana? Can I use this Collector without EPA?

Yes. That's another reason why I made collector.py a stand-alone script without dependencies on the WSP. Just build this fork of EPA and collector container, and then run just `docker compose up collector`.

Reference dashboards are in `./epa/grafana-init/dashboards/` and you may need to update them for Grafana other than version 8.

### How can I protect EPA's InfluxDB from unauthorized access?

Within Docker Compose, EPA containers are on own network. Externally, add firewall rules to prevent unrelated clients from accessing InfluxDB.

```sh
iptables -A INPUT -p tcp --dport 8086 -s <collector-ip> -j ACCEPT
iptables -A INPUT -p tcp --dport 8086 -j DROP
```

If you need much better security, consider [InfluxDB 3](https://github.com/scaleoutsean/eseries-santricity-collector).

### Where's my InfluxDB data?

By default:

- EPA 3.5: it is  is the volume created by `./epa/setup-data-dirs.sh`
- EPA 3.4: it is in a "named" Docker volume (use `docker volume ls` to see it). If you want to evacuate it, you may use `./epa/setup-data-dirs.sh`

An easy way to evacuate/move InfluxDB v1 data is with backup/restore command.

### Where's my Grafana data? I see nothing when I look at the dashboards!

Use the Explore feature in Grafana, and if that doesn't let you see anything, check Data Source, and finally, try the `utils` container (see `./epa/utils/README.txt`) or `curl` to InfluxDB's HTTP API endpoint.

### What do temperature sensors measure?

The ones we have seen represent the following:

- CPU temperature in degrees C - usually >50C (not all systems expose it)
- Controller shelf's inlet temperature in degrees C - usually between 20-30C
- "Overall" temperature status as binary indicator - decimal 128 if OK, and not 128 if not OK, so this one probably doesn't need a chart but some indicator that alerts if the value is *not* 128

One of the sample dashboards has an example panel that demonstrates the approach.

On EF600, there appears to be just two (inlet and overall status) sensors.

### Why there's just one PSU figure when there are two (or more) power supply units?

There's little value in looking per-PSU power consumption (especially since controllers' auto-rebalancing may move volumes around, causing visible changes in power consumption that have nothing to do with the PSU itself). Feel free to change the code if you want to watch them separately. Personally I couldn't imagine a scenario in which retaining both wouldn't be waste of space.

Power consumption by expansion shelves would be somewhat interesting,. but I don't have access to E-Series with expansion enclosures and have no idea what the API returns for those.

Therefore, Collector collects total power consumption of the entire *array*, regardless of whether there are any expansion shelves.

### How to get more details about Major Event Log entries?

You may create a panel with a table (rather than chart) and see how you want to filter it (e.g. last 24 hours or some other condition(s)).

```sql
SELECT "description", "id", "location" FROM "major_event_log"
```

### How to get interface error metrics?

Check `channelErrorCounts` in the `interface` measurement.

```sql
SELECT mean("channelErrorCounts") FROM "interface" WHERE $timeFilter GROUP BY time($__interval), "sys_name" fill(none)
```

There may be some other places, but that could be the main one. I didn't see anything but 0 (no errors) in my InfluxDB, so I can't say it works for sure.

### If I use my own Grafana, do I need to recreate EPA dashboards from scratch?

No, you may import them from `./epa/grafana-init/dashboards`.

### How to query InfluxDB schema?

You may start and enter `utils` container and do it from there. Externally, you can run it like this example below, or install InfluxDB v1 and use it as client.

```sh
docker exec -u 0 -it utils /bin/bash
```

Once inside, check out the commands in the README file found the container.

### What are those `repos_<three-digits>` volumes in my `config_volumes` table?

You may see them if you have snapshots and clones.

See [this](https://scaleoutsean.github.io/2023/10/05/snapshots-and-consistency-groups-with-netapp-e-series.html#appendix-c---repository-utilization) and similar content for related information.

In 3.5.4 those `repos_*` volumes were removed from dashboards which show "named volumes" (where one expects to see names of "user volumes") because there can be many of them. But in storage pool consumption and other panels and stats where total consumption is shown, those have to, and do count.

### How much memory does each collector container need?

It my testing, much less than 32 MiB (average, 21 MiB), but peaks can go to 200 MiB. It'd take 32 arrays to use 1GiB of RAM (with 32 collector containers).

However, EPA's RAM utilization may spike when it processes very large JSON objects, so if you need set a maximum upper RAM resource limit, you may set it to 256 MiB. That should handle any short-lived spikes. Sustained RAM use is around 32 MiB per collector.

### How to upgrade an EPA 3?

From 3.[1,2,3] to 3.4 or newer version 3, I wouldn't try since there aren't new features. But if you want to, then I recommend removing old setup and starting from scratch. Or, if you insist, you could transplant Collector from `./epa/collector/` and also copy its Docker Compose service to the "old" `./collector/collector/docker-compose.yaml`, and leave InfluxDB and Grafana alone. That is quick, easy to do and easy to revert.

EPA 3.4.0's `./epa/docker-compose.yaml` has changes, from versions to volumes and so on, that it's unlikely that older versions can be upgraded in place and without any trouble.

EPA 3.5.0, 3.5.1, 3.5.2, 3.5.4 don't have changes compared to 3.4, but it has new "tables". Upgrade should be possible.

EPA 3.5.4: due to significant upgrades (including Grafana), you will have to re-touch some of your Grafana dashboards. If you want to keep them, you could probably upgrade just the Collector and keep everything else the same, but I haven't tried that.

### If InfluxDB is re-installed or migrated, how do I restore InfluxDB and Grafana configuration?

EPA Collector creates database automatically: `--dbName` parameter if specified, `eseries` if not. So you can just run Collector.

Or you can create the DB before you run.

- Using the `collector` container (mind the container name and version!):

```sh
docker run --rm --network eseries_perf_analyzer \
  -e CREATE_DB=true -e DB_NAME=eseries -e DB_ADDRESS=influxdb -e DB_PORT=8086 \
  epa/collector:3.5.4
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

### What happens if the controller (specified by `--api` IPv4 address or `API=` in `docker-compose.yml`) fails?

You will notice it quickly because you'll stop getting metrics. Then fix the controller or change the setting to use the other controller and restart collector. It is also possible to use `--api 5.5.5.1 5.5.5.2` to have Collector round-robin collector requests to two controllers. If one fails you should get 50% less frequent metric delivery to Grafana, and get a hint. Or, set `API=5.5.5.1 5.5.5.2` in `docker-compose.yaml`.

### Can the E-Series' WWN change?

Normally it can't, but it's theoretically [possible](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/E-Series_SANtricity_Software_Suite/WWNs_changed_after_offline_replacement_of_tray_0). Should that happen you'd have to update your configuration and restart collector container affected by this change.

WWN is required because E-Series array names change more frequently and can even be duplicate, so WWN provides the measurements with consistency.

### How to backup and restore EPA or InfluxDB?

- Mount a backup volume to the `utils` container (i.e. start that container with a volume)
- Use `influxdb` native backup command in `utils` container to dump DB to that volume
- To restore, do the same with `inflxudb` container: mount the same volume, restore from that path to InfluxDB container

### What's the difference between Ops and IOPs?

Rates versus absolute counts across the time interval `dt`.

- **Ops** (readOps, writeOps):
  - These are the raw, absolute number of distinct API requests recorded within the polling cycle
  - `delta_read_iops_total` (i.e. current_cycle_counter - previous_cycle_counter)
  - If you polled after 60 seconds and 6,000 requests occurred during that minute, readOps = 6,000
- **IOps** (readIOps, writeIOps):
  - These are the per-second rates (IO metrics)
  - It calculates these by dividing the raw operations count by the time differential `dt` in seconds (`read_iops = delta_read_iops_total / dt`)
  - If you polled after 60 seconds and 6,000 requests occurred, readIOps = 100 per second

So basically:

- Ops = Volume / Distance (Total operations logged since the last check)
- IOps = Speed / Velocity (Operations per Second)
- PhysicalIOps, (e.g. in `disks` table) would be IOps without controller read cache hits

### How do temperature alarms work?

For the inlet sensor a warning message should be sent at 35C, and a critical message should be sent at 40C.

EPA 3.5.4 has a sample temperature visualization panel that shows "red" at 30C, which is seemingly inconsistent, but feel free to adjust that threshold. Furthermore, alerts are separate from visualizations.

I don't know about the CPU temperature sensor (it's not even available on some systems, probably to (again) undocumented SANtricity API or hardware changes).

### InfluxDB capacity and performance requirements

Performance requirements should be modest even for several arrays. If InfluxDB is on flash storage, any will do.

Capacity requirements depend on the number of arrays, disks and volumes (LUNs). With a small EF570 (24 disks, 10 volumes) collected every 60s, you may need up to several GB/month.

Anecdotally, v3.5.0 (this includes the extra configuration metrics) collecting 2 arrays, each with 12 disks and about 6 volumes:

- 1 hour of collection 5 MB (60 collections of performance, MEL and failures, and four of various configuration metrics which by default run every 15 min)
- This amounts less than 1 GB/month or ~500 MB/mo for a small array

For many arrays or volumes, showing weeks at once may benefit from more RAM given to Grafana, but you can evaluate that based on your use case.

### How to use the capture feature

- Use timestamped or other unique directory names to store capture data without overwrites from multiple runs
- Test-replay capture files

```sh
python3 scripts/test_replay.py --captures tests/captures
```
