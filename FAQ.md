## FAQs

- [FAQs](#faqs)
  - [Why can't we have one EPA Collector all monitored arrays?](#why-cant-we-have-one-epa-collector-all-monitored-arrays)
  - [What kind of consolidation is possible or advisable?](#what-kind-of-consolidation-is-possible-or-advisable)
  - [Can I use this Collector without EPA?](#can-i-use-this-collector-without-epa)
  - [Where's my InfluxDB data?](#wheres-my-influxdb-data)
  - [What do temperature sensors measure?](#what-do-temperature-sensors-measure)
  - [If I use my own Grafana, do I need to recreate EPA dashboards from scratch?](#if-i-use-my-own-grafana-do-i-need-to-recreate-epa-dashboards-from-scratch)
  - [How much memory does each collector container need?](#how-much-memory-does-each-collector-container-need)
  - [Can the E-Series' WWN change?](#can-the-e-series-wwn-change)
  - [How to backup and restore EPA or InfluxDB?](#how-to-backup-and-restore-epa-or-influxdb)
  - [How do temperature alarms work?](#how-do-temperature-alarms-work)
  - [InfluxDB capacity and performance requirements](#influxdb-capacity-and-performance-requirements)



### Why can't we have one EPA Collector all monitored arrays?

That's what NetApp's EPA used to do. This EPA refuses to do that. Each EPA instance requires minimal resources and it's extremely easy to deploy. There's no need for consolidation. 

InfluxDB can be consolidated, but doesn't have to be.

### What kind of consolidation is possible or advisable?

No consolidation means 1 E-Series, 1 EPA Collector, 1 Influx DB, and optionally 1 Container with S3.

Some consolidation can be realized by creating multiple databases on InfluxDB, so that only one DB service is used and each EPA Collector uses its own instance. The trouble with this is InfluxDB 3.3 Core offers no segregation or encryption, so in this setup any user can access and delete any other user's data.

![EPA Database Consolidation](./images/epa-v4-services-diagram.svg)

### Can I use this Collector without EPA?

Yes. See the documentation.

### Where's my InfluxDB data?

If you use reference `docker-compose.yaml` from this project: your data is in `eseries` database which is in `./data/influxdb/` (assuming you haven't changed that file). 

### What do temperature sensors measure?

The ones we've seen represent the following:

- CPU temperature in degrees C - usually > 50C
- Controller shelf's inlet temperature in degrees C - usually in 20C - 30C range
- "Overall" temperature status as binary indicator - 128 if OK, and not 128 if not OK, so this one probably doesn't need a chart but some indicator that alerts if the value is not 128

It's annoying that E-Series uses floating point precision even for *de facto* integers, so even "128" above is stored as `128.0`. It's clearly an integer, but we don't know if sensors on all models use *de facto* integers so we store it as a float.

### If I use my own Grafana, do I need to recreate EPA dashboards from scratch?

A reference all-in-one dashboard will be provided. The [TIPS](./TIPS.md) page has many of the reference queries that will be used to create it.

Old dashboards from EPA 3 are less unlikely to work. They were created for InfluxQL and although InfluxDB 3 still supports it, Influx Data recommends SQL as the non-legacy option. 

There have also been changes to the database itself (both the engine, obviously, but also measurements. It should be much easier to recreate dashboards and recycle them from EPA v3.

### How much memory does each collector container need? 

It should be less than 100 MB RAM and 0.25 vCPU.

### Can the E-Series' WWN change?

It can't without you knowing it. It is theoretically [possible](https://kb.netapp.com/Advice_and_Troubleshooting/Data_Storage_Software/E-Series_SANtricity_Software_Suite/WWNs_changed_after_offline_replacement_of_tray_0), though. Should that happen EPA Collector will start collecting new WWN, but your SQL queries or dashboards may need an update.

### How to backup and restore EPA or InfluxDB?

First, make sure you have a backup of all configuration files and settings including InfluxDB API keys, TLS keys, passwords, etc. 

Second, if you tier InfluxDB to S3, then there's no point in backing up InfluxDB. If you do *not* tier to S3 (EPA 4 default), the best way to backup data is to stop (in Kubernetes, scale down to 0) deployment and use Velero to back it up, then scale up to 1 (or `docker compopse up -d influxdb` on Docker). You may not gather metrics for a minute or two, but so what? Restart all EPA services and you'll be fine.

It is also possible to dump everything from InfluxDB to file-system or S3.

### How do temperature alarms work?

For the inlet sensor a warning message should be sent at 35C, and a critical message should be sent at 40C. I don't know about the CPU temperature sensor.

### InfluxDB capacity and performance requirements

Performance requirements should be insignificant even for up to half a dozen arrays. If InfluxDB is on flash storage, any will do.

Capacity requirements depend on the number of arrays, disks and volumes (LUNs). Without tiering to S3, InfluxDB should use less than 100 GB/month.