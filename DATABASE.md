# InfluxDB v1 in EPA 3.5

InfluxDB v1 uses InfluxQL which is supported in InfluxDB 3 Core which EPA 4 uses, so there's still value in learning it. Although in the case of EPA 4, database schema will differ, similar queries will work with small adjustments.

- `DISTINCT` only works on **tags**, not fields. Use `SHOW TAG VALUES` for tags, `GROUP BY` for field de-duplication in query results
- Use `GROUP BY` for uniqueness. When you want unique records, group by a unique identifier (like `volumeRef` below)
- Mix tags and fields in `WHERE`. Tags use `=` or `=~`, while fields can use comparison operators
- Time filtering. Always include time filters for performance: `time > now() - 5m` makes it *much* easier on database. For `config_` measurements, use `now() - 20m)` minutes as those are collected every 15 minutes

To know what to query in terms of tag **values**, you can get them like so:

```sh
docker exec influxdb influx -database eseries -execute "SHOW TAG VALUES FROM volumes WITH KEY = \"vol_name\" WHERE sys_name =~ /.*/ AND time > now() - 5m"
```

To see what tags and fields exist and may be queried in the first place, refer to EPA 3's database schema below.

Also, see the included Grafana dashboards for additional examples.

## Queries for configuration details

While the performance- and event-related dashboards contain 10-20 panels with queries, queries for the `config_` measurements are just few in the reference configuration dashboard so this section shares several practical examples of queries related to EPA's `config_` measurements.

Storage pool capacity and utilization:

```sh
docker exec influxdb influx -database eseries -execute "SELECT last(pool_name_field) AS \"Pool_Name\", last(totalRaidedSpace)/1099511627776 AS \"Total_TB\", last(usedSpace)/1099511627776 AS \"Used_TB\", (last(totalRaidedSpace)-last(usedSpace))/1099511627776 AS \"Available_TB\", last(usedSpace)*100/last(totalRaidedSpace) AS \"Util_%\", last(diskPool) AS \"Is_DiskPool\" FROM config_storage_pools WHERE sys_name = 'netapp_03' GROUP BY volumeGroupRef"
```

Volumes' space consumption per pool:

```sh
docker exec influxdb influx -database eseries -execute "SELECT SUM(last_totalSizeInBytes)/1099511627776 AS \"Allocated_TB\" FROM (SELECT last(totalSizeInBytes) AS \"last_totalSizeInBytes\" FROM config_volumes WHERE sys_name = 'netapp_03' GROUP BY volumeRef) GROUP BY volumeGroupRef"
```

Compare DiskPool vs VolumeGroup utilization:

```sh
docker exec influxdb influx -database eseries -execute "SELECT last(pool_name_field) AS \"Pool_Name\", last(diskPool) AS \"Is_DiskPool\", last(usedSpace)*100/last(totalRaidedSpace) AS \"Utilization_%\" FROM config_storage_pools WHERE sys_name = 'netapp_03' GROUP BY volumeGroupRef ORDER BY time DESC"
```

With these you may get results like this one. Newer E-Series don't support thin provisioning, so `Util %` is likely to be high as most users provision all space:

```raw
name: config_storage_pools
tags: volumeGroupRef=040000006D039EA0004D006B00000D6768AC53AD
time Pool_Name     Total_TB           Used_TB            Available_TB      Util_%            Is_DiskPool
---- ---------     --------           -------            ------------      ------            -----------
0    beegfs_s9_s10 139.67675910890102 134.08957862854004 5.587180480360985 95.99992116368847 false

name: config_storage_pools
tags: volumeGroupRef=040000006D039EA0004D006B00000D6868AC53BA
time Pool_Name      Total_TB           Used_TB            Available_TB      Util_%            Is_DiskPool
---- ---------      --------           -------            ------------      ------            -----------
0    beegfs_s13_s14 139.67675910890102 134.08957862854004 5.587180480360985 95.99992116368847 false
```

You may also try the Bash script in the `scripts` directory. Pass E-Series system name to it when you run the script: `./storage_pool_analysis.sh <sys_name>`.

## Schema

For convenience, a list of measurements, fields and keys that v3.5.0 collects are given below. These aren't expected to change, but you can view your own with `SHOW MEASUREMENTS`, `SHOW FIELD KEYS`, `SHOW TAG KEYS`. `"SHOW FIELD KEYS FROM config_volumes"` shows fields from specific measurement.

```raw
EPA Database Schema Dump
========================
Host: influxdb:8086
Database: eseries
Generated: Wed Sep  3 09:16:18 AM UTC 2025

Found measurement: disks
=================================
Field Keys:
name: disks
fieldKey                    fieldType
--------                    ---------
averageReadOpSize           float
averageWriteOpSize          float
combinedIOps                float
combinedResponseTime        float
combinedThroughput          float
otherIOps                   float
percentEnduranceUsed        integer
readIOps                    float
readOps                     float
readPhysicalIOps            float
readResponseTime            float
readThroughput              float
spareBlocksRemainingPercent integer
writeIOps                   float
writeOps                    float
writePhysicalIOps           float
writeResponseTime           float
writeThroughput             float

Tag Keys:
name: disks
tagKey
------
sys_id
sys_name
sys_tray
sys_tray_slot
vol_group_name


Found measurement: volumes
=================================
Field Keys:
name: volumes
fieldKey                   fieldType
--------                   ---------
averageReadOpSize          float
averageWriteOpSize         float
combinedIOps               float
combinedResponseTime       float
combinedThroughput         float
flashCacheHitPct           float
flashCacheReadHitBytes     float
flashCacheReadHitOps       float
flashCacheReadResponseTime float
flashCacheReadThroughput   float
otherIOps                  float
queueDepthMax              float
queueDepthTotal            float
readCacheUtilization       float
readHitBytes               float
readHitOps                 float
readIOps                   float
readOps                    float
readPhysicalIOps           float
readResponseTime           float
readThroughput             float
writeCacheUtilization      float
writeHitBytes              float
writeHitOps                float
writeIOps                  float
writeOps                   float
writePhysicalIOps          float
writeResponseTime          float
writeThroughput            float

Tag Keys:
name: volumes
tagKey
------
sys_id
sys_name
vol_name


Found measurement: interface
=================================
Field Keys:
name: interface
fieldKey             fieldType
--------             ---------
averageReadOpSize    float
averageWriteOpSize   float
channelErrorCounts   float
combinedIOps         float
combinedResponseTime float
combinedThroughput   float
otherIOps            float
queueDepthMax        float
queueDepthTotal      float
readIOps             float
readOps              float
readResponseTime     float
readThroughput       float
writeIOps            float
writeOps             float
writeResponseTime    float
writeThroughput      float

Tag Keys:
name: interface
tagKey
------
channel_type
interface_id
sys_id
sys_name


Found measurement: controllers
=================================
Field Keys:
name: controllers
fieldKey                           fieldType
--------                           ---------
averageReadOpSize                  float
averageWriteOpSize                 float
cacheHitBytesPercent               float
combinedHitResponseTime            float
combinedHitResponseTimeStdDev      float
combinedIOps                       float
combinedResponseTime               float
combinedResponseTimeStdDev         float
combinedThroughput                 float
controllerId                       string
cpuAvgUtilization                  float
cpuAvgUtilizationPerCoreStdDev_max float
cpuAvgUtilizationPerCore_max       float
ddpBytesPercent                    float
fullStripeWritesBytesPercent       float
maxCpuUtilization                  float
maxCpuUtilizationPerCore_max       float
mirrorBytesPercent                 float
observedTime                       string
observedTimeInMS                   string
otherIOps                          float
raid0BytesPercent                  float
raid1BytesPercent                  float
raid5BytesPercent                  float
raid6BytesPercent                  float
randomIosPercent                   float
readHitResponseTime                float
readHitResponseTimeStdDev          float
readIOps                           float
readOps                            float
readPhysicalIOps                   float
readResponseTime                   float
readResponseTimeStdDev             float
readThroughput                     float
writeHitResponseTime               float
writeHitResponseTimeStdDev         float
writeIOps                          float
writeOps                           float
writePhysicalIOps                  float
writeResponseTime                  float
writeResponseTimeStdDev            float
writeThroughput                    float

Tag Keys:
name: controllers
tagKey
------
controller_id
sys_id
sys_name


Found measurement: systems
=================================
Field Keys:
name: systems
fieldKey          fieldType
--------          ---------
cpuAvgUtilization float
maxCpuUtilization float

Tag Keys:
name: systems
tagKey
------
sys_id
sys_name


Found measurement: power
=================================
Field Keys:
name: power
fieldKey   fieldType
--------   ---------
totalPower integer

Tag Keys:
name: power
tagKey
------
sys_id
sys_name


Found measurement: temp
=================================
Field Keys:
name: temp
fieldKey fieldType
-------- ---------
temp     integer

Tag Keys:
name: temp
tagKey
------
sensor
sensor_seq
sys_id
sys_name


Found measurement: major_event_log
=================================
Field Keys:
name: major_event_log
fieldKey    fieldType
--------    ---------
description string
id          string
location    string

Tag Keys:
name: major_event_log
tagKey
------
asc
ascq
category
critical
event_type
priority
sys_id
sys_name
time_stamp


Found measurement: failures
=================================
Field Keys:
name: failures
fieldKey fieldType
-------- ---------
name_of  string
type_of  string

Tag Keys:
name: failures
tagKey
------
active
failure_type
object_ref
object_type
sys_id
sys_name


Found measurement: config_hosts
=================================
Field Keys:
name: config_hosts
fieldKey                                         fieldType
--------                                         ---------
confirmLUNMappingCreation                        string
hostSidePortCount                                integer
hostSidePorts_first_id                           string
hostSidePorts_first_mtpIoInterfaceType           string
hostSidePorts_first_type                         string
host_name_field                                  string
initiatorCount                                   integer
initiators_first_hostRef                         string
initiators_first_id                              string
initiators_first_initiatorInactive               string
initiators_first_initiatorNodeName_interfaceType string
initiators_first_initiatorRef                    string
initiators_first_label                           string
initiators_first_nodeName_ioInterfaceType        string
initiators_first_nodeName_iscsiNodeName          string
initiators_first_nodeName_nvmeNodeName           string
initiators_first_nodeName_remoteNodeWWN          string
isLargeBlockFormatHost                           string
isLun0Restricted                                 string
isSAControlled                                   string
protectionInformationCapableAccessMethod         string

Tag Keys:
name: config_hosts
tagKey
------
clusterRef
hostRef
hostTypeIndex
host_name
id
label
sys_id
sys_name


Found measurement: config_volumes
=================================
Field Keys:
name: config_volumes
fieldKey                      fieldType
--------                      ---------
blkSize                       integer
capacity                      float
currentControllerId           string
dssMaxSegmentSize             integer
flashCached                   string
listOfMappings_lun            integer
listOfMappings_lunMappingRef  string
listOfMappings_ssid           integer
preReadRedundancyCheckEnabled string
preferredControllerId         string
protectionInformationCapable  string
protectionType                string
raidLevel                     string
segmentSize                   integer
status                        string
totalSizeInBytes              float
volume_name_field             string

Tag Keys:
name: config_volumes
tagKey
------
extendedUniqueIdentifier
id
label
sys_id
sys_name
volumeGroupRef
volumeHandle
volumeRef
volume_name
worldWideName
wwn


Found measurement: config_storage_pools
=================================
Field Keys:
name: config_storage_pools
fieldKey                     fieldType
--------                     ---------
blkSizeRecommended           integer
blkSizeSupported_4096        string
blkSizeSupported_512         string
diskPool                     string
drawerLossProtection         string
driveMediaType               string
drivePhysicalType            string
extents_raidLevel            string
extents_rawCapacity          integer
freeSpace                    integer
isInaccessible               string
offline                      string
pool_name_field              string
protectionInformationCapable string
raidLevel                    string
raidStatus                   string
reservedSpaceAllocated       string
sequenceNum                  integer
spindleSpeedMatch            string
state                        string
totalRaidedSpace             integer
usedSpace                    integer
volumeGroupData_type         string

Tag Keys:
name: config_storage_pools
tagKey
------
driveMediaType
id
label
pool_name
raidLevel
state
sys_id
sys_name
volumeGroupRef


Found measurement: config_drives
=================================
Field Keys:
name: config_drives
fieldKey                      fieldType
--------                      ---------
available                     boolean
cause                         string
currentVolumeGroupRef         string
hasDegradedChannel            boolean
hotSpare                      boolean
id                            string
interfaceType_nvme_deviceName string
interfaceType_sas_deviceName  string
invalidDriveData              boolean
manufacturer                  string
offline                       string
pfa                           boolean
pfaReason                     string
rawCapacity                   string
removed                       boolean
sparedForDriveRef             string
status                        string
uncertified                   boolean
usableCapacity                integer
volumeGroupIndex              float
worldWideName                 string

Tag Keys:
name: config_drives
tagKey
------
driveMediaType
driveRef
physicalLocation__trayRef
physicalLocation_slot
productID
serialNumber
sys_id
sys_name
```
