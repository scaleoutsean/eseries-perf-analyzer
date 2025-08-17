# TIPS

- [TIPS](#tips)
  - [General tips](#general-tips)
    - [Difference between E-Series and InfluxDB metrics](#difference-between-e-series-and-influxdb-metrics)
    - [InfluxDB 3 client tips](#influxdb-3-client-tips)
    - [Storage management](#storage-management)
  - [Measurements, fields, tags](#measurements-fields-tags)
  - [`controllers` - controller performance](#controllers---controller-performance)
  - [`disks` - disk-level performance](#disks---disk-level-performance)
  - [`drives` - disk drive characteristics](#drives---disk-drive-characteristics)
  - [`failures` - failure events](#failures---failure-events)
  - [`health_check`](#health_check)
  - [`interface` - interfaces' metrics](#interface---interfaces-metrics)
  - [`major_event_log` - MEL logs](#major_event_log---mel-logs)
  - [`power` - power supply units' readings](#power---power-supply-units-readings)
  - [`systems` - system-level performance metrics](#systems---system-level-performance-metrics)
  - [`temp` - temperature sensors](#temp---temperature-sensors)
  - [`volumes` - volume performance metrics](#volumes---volume-performance-metrics)

## General tips

`influxdb3` is the InfluxDB client/server binary. It's pre-installed in the `utils` container, but you can download your own and deploy to a client of your choosing. See [the InfluxDB 3 Core documentation](https://docs.influxdata.com/influxdb3/core/install/).

If you're looking for easier options, try InfluxDB Explorer which has a plugin for Natural Language queries (currently commercial chat clients only, so one of their API tokens is required), or try InfluxDB MCP (separate installation) or switch to Grafana for a nicer UI and more AI options.

We always have to assume InfluxDB data may be outdated or even wrong, so verify independently before performing destructive actions.

**NOTE:** fields and tags may change by the time v4.0.0 is released. These commands were created on an early v4.0.0 beta.

### Difference between E-Series and InfluxDB metrics

This is important to know: 

- E-Series sometimes uses decimals where it doesn't make sense. It's not just wrong, but also annoying and wasteful
- EPA Collector fixes it "close to source": the most ridiculous examples of this type abuse are dealt with before writing to InfluxDB

In EPA v3 that was not the case, so you'd have a disk drive in slot `12.0`. EPA v4 eliminates a lot of that nonsense.

### InfluxDB 3 client tips

- Use the `influxdb3` CLI (pre-installed in the `utils` container) or install your own from https://docs.influxdata.com/influxdb3/core/install/.

- Configure your shell for convenience (the `utils` container has this pre-configured):
  ```sh
  export INFLUXDB3_HOST_URL="https://influxdb:8181"
  export INFLUXDB3_DATABASE_NAME="eseries"
  export INFLUXDB3_AUTH_TOKEN="apiv3_..."
  export INFLUXDB3_TLS_CA="/path/to/ca.crt"
  ```

   If you don't have that or environment variables (`.bashrc`, Docker `.env` file, etc.), then you have to prefix each command with those variables or pass these annoying parameters which will drive you nuts.

   ```sh
   -H, --host <HOST_URL>           The host URL of the running InfluxDB 3 Core server [env: INFLUXDB3_HOST_URL=https://influxdb:8181]
   -d, --database <DATABASE_NAME>  The name of the database to operate on [env: INFLUXDB3_DATABASE_NAME=eseries]
   --token <AUTH_TOKEN>        The token for authentication with the InfluxDB 3 Core server [env: INFLUXDB3_AUTH_TOKEN=apiv3_...]
   --tls-ca <CA_CERT> The CA certificate that signed the TLS certificate of InfluxDB server [env: INFLUXDB3_TLS_CA="...."]
   ```

- Get quick help:
  ```sh
  influxdb3 --help
  influxdb3 query --help
  ```

- Field and tag names are case-sensitive. Always double-quote mixed-case identifiers:
  ```sql
  SELECT "softwareVersion", "physicalLocation_slot"
    FROM drives
    WHERE "softwareVersion" <> 'NA54'
    ORDER BY "physicalLocation_slot" ASC
  ```

- Escape single-quotes inside a single-quoted shell string:
  ```sh
  influxdb3 query \
    'SELECT * FROM drives WHERE "softwareVersion" != '\''NA54'\'''
  ```

- Default query language is **SQL**. To use InfluxQL add `--language influxql`.  
  - SQL docs: https://docs.influxdata.com/influxdb3/core/reference/sql/  
  - InfluxQL docs: https://docs.influxdata.com/influxdb3/core/query-data/influxql/
  - [InfluxDB API reference documentation](https://docs.influxdata.com/influxdb3/core/api/v3/)

- Control output for scripting:
  ```sh
  influxdb3 query --language sql --output csv 'SELECT ...'   # CSV, no headers
  influxdb3 query --language sql --output json 'SELECT ...'  # JSON array
  ```

- Always filter by time, tags or use `LIMIT` to avoid scanning massive datasets (this applies to queries in Grafana dashboards, too!):
  ```sql
  SELECT * 
    FROM volumes 
   WHERE time >= now() - interval '1d'
   LIMIT 100
  ```

- De-duplicate repeated points:  
  - In SQL use `DISTINCT()` or `LAST()`  
  - In InfluxQL use `DISTINCT` or `LAST()` (and/or `GROUP BY time(...)`)

### Storage management

- Down-sampling: use the [official plugin](https://docs.influxdata.com/influxdb3/core/plugins/library/official/downsampler/) or write your own
- Expiration: use a down-sampling plugin to down-sample to 1 record per month or something like that - that's the easiest way that can use the same down-sampling approach you will likely have in place anyway. If you *must not* have older data (i.e. in the case of government overreach).

## Measurements, fields, tags

Measurements are "SQL tables", fields are values (e.g. `1.2`) and tags are properties (such as `system_id`) assigned to rec.

As `SQL` is the default in influxDB 3, set `--language` to use InfluxQL. 

```sh
$ influxdb3 query --language influxql "SHOW MEASUREMENTS"
+------------------+-----------------+
| iox::measurement | name            |
+------------------+-----------------+
| measurements     | controllers     |
| measurements     | disks           |
| measurements     | drives          |
| measurements     | failures        |
| measurements     | health_check    |
| measurements     | interface       |
| measurements     | major_event_log |
| measurements     | power           |
| measurements     | systems         |
| measurements     | temp            |
| measurements     | volumes         |
+------------------+-----------------+

```

Show `SELECT`-able fields from a measurement.

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM drives'
+------------------+----------------------------------------------------------------+-----------+
| iox::measurement | fieldKey                                                       | fieldType |
+------------------+----------------------------------------------------------------+-----------+
| drives           | available                                                      | boolean   |
| drives           | blkSize                                                        | float     |
| drives           | blkSizePhysical                                                | float     |
| drives           | cause                                                          | string    |
| drives           | currentCommandAgingTimeout                                     | float     |
| drives           | currentSpeed                                                   | string    |
| drives           | currentVolumeGroupRef                                          | string    |
| drives           | defaultCommandAgingTimeout                                     | float     |
...
| drives           | workingChannel                                                 | float     |
| drives           | worldWideName                                                  | string    |
+------------------+----------------------------------------------------------------+-----------+

```

Select a (distinct) field (15.3 TB NVMe disk drive).

```sh
$ influxdb3 query --language influxql 'SELECT DISTINCT usableCapacity FROM drives'
+------------------+---------------------+----------------+
| iox::measurement | time                | distinct       |
+------------------+---------------------+----------------+
| drives           | 1970-01-01T00:00:00 | 15357622706176 |
+------------------+---------------------+----------------+

```

Show tags from the `disks` table. Notice these have no special "type", which is important to remember.

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM drives'
+------------------+----------------+
| iox::measurement | tagKey         |
+------------------+----------------+
| drives           | driveMediaType |
| drives           | driveRef       |
| drives           | driveType      |
| drives           | id             |
| drives           | serialNumber   |
| drives           | status         |
| drives           | system_id      |
| drives           | system_name    |
+------------------+----------------+

```

With a list of tags, we can focus on one and show all values that tag has in this measurement, which may be useful if you want to narrow down your `SELECT` queries.

```sh
$ influxdb3 query --language influxql 'SHOW TAG VALUES FROM drives WITH key ="driveType"'
+------------------+-----------+----------------+
| iox::measurement | key       | value          |
+------------------+-----------+----------------+
| drives           | driveType | nvmeDirectPcie |
+------------------+-----------+----------------+
```

## `controllers` - controller performance

This may be just one in singleton systems or if a single controller's API address is provided, or both (when both controllers are defined, reachable and functioning).

Another special thing about this measurement is these are less frequent (see the docs) as per-controller metrics aren't that useful in minute-level intervals.

Fields:

```sh
influxdb3 query --language influxql 'SHOW FIELD KEYS FROM controllers'
+------------------+---------------------------------+-----------+
| iox::measurement | fieldKey                        | fieldType |
+------------------+---------------------------------+-----------+
| controllers      | averageReadOpSize               | float     |
| controllers      | averageWriteOpSize              | float     |
| controllers      | cacheHitBytesPercent            | float     |
| controllers      | combinedHitResponseTime         | float     |
| controllers      | combinedHitResponseTimeStdDev   | float     |
| controllers      | combinedIOps                    | float     |
| controllers      | combinedResponseTime            | float     |
| controllers      | combinedResponseTimeStdDev      | float     |
| controllers      | combinedThroughput              | float     |
| controllers      | cpuAvgUtilization               | float     |
| controllers      | ddpBytesPercent                 | float     |
| controllers      | fullStripeWritesBytesPercent    | float     |
| controllers      | maxCpuUtilization               | float     |
| controllers      | maxPossibleBpsUnderCurrentLoad  | float     |
| controllers      | maxPossibleIopsUnderCurrentLoad | float     |
| controllers      | mirrorBytesPercent              | float     |
| controllers      | otherIOps                       | float     |
| controllers      | raid0BytesPercent               | float     |
| controllers      | raid1BytesPercent               | float     |
| controllers      | raid5BytesPercent               | float     |
| controllers      | raid6BytesPercent               | float     |
| controllers      | randomIosPercent                | float     |
| controllers      | readHitResponseTime             | float     |
| controllers      | readHitResponseTimeStdDev       | float     |
| controllers      | readIOps                        | float     |
| controllers      | readOps                         | float     |
| controllers      | readPhysicalIOps                | float     |
| controllers      | readResponseTime                | float     |
| controllers      | readResponseTimeStdDev          | float     |
| controllers      | readThroughput                  | float     |
| controllers      | writeHitResponseTime            | float     |
| controllers      | writeHitResponseTimeStdDev      | float     |
| controllers      | writeIOps                       | float     |
| controllers      | writeOps                        | float     |
| controllers      | writePhysicalIOps               | float     |
| controllers      | writeResponseTime               | float     |
| controllers      | writeResponseTimeStdDev         | float     |
| controllers      | writeThroughput                 | float     |
+------------------+---------------------------------+-----------+

```

Tags:

```sh
influxdb3 query --language influxql 'SHOW tag KEYS FROM controllers'   
+------------------+---------------------+
| iox::measurement | tagKey              |
+------------------+---------------------+
| controllers      | controllerId        |
| controllers      | controller_endpoint |
| controllers      | sourceController    |
| controllers      | system_id           |
| controllers      | system_name         |
+------------------+---------------------+

```

In **InfluxDB Explorer**, to find six most recent data from `5.5.5.5`.

```sql
SELECT "time",
         "system_id",
         "controller_endpoint",
         "readIOps",
         "writeIOps",
         "otherIOps",
         "maxPossibleIopsUnderCurrentLoad"
    FROM controllers WHERE controller_endpoint='5.5.5.5'
  ORDER BY "time" DESC
    LIMIT 6
```

## `disks` - disk-level performance 

Fields:

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM disks'
+------------------+----------------------+-----------+
| iox::measurement | fieldKey             | fieldType |
+------------------+----------------------+-----------+
| disks            | averageReadOpSize    | float     |
| disks            | averageWriteOpSize   | float     |
| disks            | combinedIOps         | float     |
| disks            | combinedResponseTime | float     |
| disks            | combinedThroughput   | float     |
| disks            | otherIOps            | float     |
| disks            | readIOps             | float     |
| disks            | readOps              | float     |
| disks            | readPhysicalIOps     | float     |
| disks            | readResponseTime     | float     |
| disks            | readThroughput       | float     |
| disks            | writeIOps            | float     |
| disks            | writeOps             | float     |
| disks            | writePhysicalIOps    | float     |
| disks            | writeResponseTime    | float     |
| disks            | writeThroughput      | float     |
+------------------+----------------------+-----------+
```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM disks'
+------------------+---------------+
| iox::measurement | tagKey        |
+------------------+---------------+
| disks            | sys_id        |
| disks            | sys_name      |
| disks            | sys_tray      |
| disks            | sys_tray_slot |
+------------------+---------------+

```

## `drives` - disk drive characteristics

`drives` and `disks`... Sorry.

Similar to `controlles`, these aren't captured too frequently. 

Use `disks` table to get disk drive details including firmware, slot location, spare blocks remaining in SSD media. 

Fields are many, and most never change. Which is why these are collected at a longer, but still adjustable, interval (see the documentation).

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM drives'
+------------------+----------------------------------------------------------------+-----------+
| iox::measurement | fieldKey                                                       | fieldType |
+------------------+----------------------------------------------------------------+-----------+
| drives           | available                                                      | boolean   |
| drives           | blkSize                                                        | float     |
| drives           | blkSizePhysical                                                | float     |
| drives           | cause                                                          | string    |
| drives           | currentCommandAgingTimeout                                     | float     |
| drives           | currentSpeed                                                   | string    |
| drives           | currentVolumeGroupRef                                          | string    |
| drives           | defaultCommandAgingTimeout                                     | float     |
| drives           | driveSecurityType                                              | string    |
| drives           | driveTemperature_currentTemp                                   | float     |
| drives           | driveTemperature_refTemp                                       | float     |
| drives           | dulbeCapable                                                   | boolean   |
| drives           | fdeCapable                                                     | boolean   |
| drives           | fdeEnabled                                                     | boolean   |
| drives           | fdeLocked                                                      | boolean   |
| drives           | fipsCapable                                                    | boolean   |
| drives           | firmwareVersion                                                | string    |
| drives           | fpgaVersion                                                    | string    |
| drives           | hasDegradedChannel                                             | boolean   |
| drives           | hotSpare                                                       | boolean   |
| drives           | interfaceType_driveType                                        | string    |
| drives           | interfaceType_nvme_deviceName                                  | string    |
| drives           | interposerPresent                                              | boolean   |
| drives           | interposerRef                                                  | string    |
| drives           | invalidDriveData                                               | boolean   |
| drives           | locateInProgress                                               | boolean   |
| drives           | lockKeyID                                                      | string    |
| drives           | lowestAlignedLBA                                               | string    |
| drives           | manufacturer                                                   | string    |
| drives           | manufacturerDate                                               | string    |
| drives           | maxSpeed                                                       | string    |
| drives           | mirrorDrive                                                    | string    |
| drives           | nonRedundantAccess                                             | boolean   |
| drives           | offline                                                        | boolean   |
| drives           | pfa                                                            | boolean   |
| drives           | pfaReason                                                      | string    |
| drives           | phyDriveType                                                   | string    |
| drives           | phyDriveTypeData_phyDriveType                                  | string    |
| drives           | physicalLocation_label                                         | string    |
| drives           | physicalLocation_locationParent_refType                        | string    |
| drives           | physicalLocation_locationPosition                              | float     |
| drives           | physicalLocation_slot                                          | float     |
| drives           | physicalLocation_trayRef                                       | string    |
| drives           | productID                                                      | string    |
| drives           | protectionInformationCapabilities_protectionInformationCapable | boolean   |
| drives           | protectionInformationCapabilities_protectionType               | string    |
| drives           | protectionInformationCapable                                   | boolean   |
| drives           | protectionType                                                 | string    |
| drives           | rawCapacity                                                    | string    |
| drives           | removed                                                        | boolean   |
| drives           | repairPolicy_removalData_removalMethod                         | string    |
| drives           | repairPolicy_replacementMethod                                 | string    |
| drives           | reserved                                                       | string    |
| drives           | rtrAttributes_cruType                                          | string    |
| drives           | rtrAttributes_rtrAttributeData_hasReadyToRemoveIndicator       | boolean   |
| drives           | rtrAttributes_rtrAttributeData_readyToRemove                   | boolean   |
| drives           | sanitizeCapable                                                | boolean   |
| drives           | softwareVersion                                                | string    |
| drives           | sparedForDriveRef                                              | string    |
| drives           | spindleSpeed                                                   | float     |
| drives           | ssdWearLife_averageEraseCountPercent                           | float     |
| drives           | ssdWearLife_isWearLifeMonitoringSupported                      | boolean   |
| drives           | ssdWearLife_percentEnduranceUsed                               | float     |
| drives           | ssdWearLife_spareBlocksRemainingPercent                        | float     |
| drives           | uncertified                                                    | boolean   |
| drives           | usableCapacity                                                 | string    |
| drives           | volumeGroupIndex                                               | float     |
| drives           | workingChannel                                                 | float     |
| drives           | worldWideName                                                  | string    |
+------------------+----------------------------------------------------------------+-----------+
```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM disks'
+------------------+---------------+
| iox::measurement | tagKey        |
+------------------+---------------+
| disks            | sys_id        |
| disks            | sys_name      |
| disks            | sys_tray      |
| disks            | sys_tray_slot |
+------------------+---------------+

```

In **InfluxDB Explorer** > `SQL query`:

```sql
SELECT DISTINCT "serialNumber", "manufacturer", "productID", "firmwareVersion","physicalLocation_slot","ssdWearLife_spareBlocksRemainingPercent" 
  FROM drives WHERE "ssdWearLife_isWearLifeMonitoringSupported"=TRUE AND system_id = "6D039EA00041F29A0000000065FCE1F0"
  ORDER BY "physicalLocation_slot"
```

The same thing **has to be reworked** for the CLI:

```sh
$ influxdb3 query --language influxql '
    SELECT manufacturer,serialNumber,productID,softwareVersion,physicalLocation_slot,ssdWearLife_spareBlocksRemainingPercent 
    FROM drives
    '
```

A CLI query with **InfluxQL**:

```sh
$ influxdb3 query --language influxql 'SELECT softwareVersion,physicalLocation_slot FROM drives'
+------------------+---------------------+-----------------+-----------------------+
| iox::measurement | time                | softwareVersion | physicalLocation_slot |
+------------------+---------------------+-----------------+-----------------------+
| drives           | 2025-08-13T17:31:42 | NA54            | 12                    |
| drives           | 2025-08-13T17:31:42 | NQ02            | 2                     |
| drives           | 2025-08-13T17:31:42 | NQ02            | 3                     |
| drives           | 2025-08-13T17:31:42 | NA50            | 11                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 15                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 16                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 13                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 24                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 18                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 8                     |
| drives           | 2025-08-13T17:31:42 | NA50            | 19                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 10                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 23                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 14                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 4                     |
| drives           | 2025-08-13T17:31:42 | NA50            | 20                    |
| drives           | 2025-08-13T17:31:42 | NQ02            | 22                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 21                    |
| drives           | 2025-08-13T17:31:42 | NA50            | 17                    |
| drives           | 2025-08-13T17:31:42 | NQ02            | 6                     |
| drives           | 2025-08-13T17:31:42 | NQ02            | 9                     |
| drives           | 2025-08-13T17:31:42 | NQ02            | 1                     |
| drives           | 2025-08-13T17:31:42 | NA50            | 7                     |
| drives           | 2025-08-13T17:31:42 | NQ02            | 5                     |
+------------------+---------------------+-----------------+-----------------------+

```

Also using **InfluxQL**, to find all disk drives with outdated SSD firmware (assuming `NA54` is the latest for this particular disk):

```sql
influxdb3 query --language influxql \
  'SELECT "softwareVersion","physicalLocation_slot"
     FROM drives
    WHERE "softwareVersion" != '\''NA54'\'''
```


One funny thing is InfluxDB Explorer offers convenient statement conversion to other SQL dialects and languages, except that right now that example doesn't convert properly. Maybe it does on OS X. Well done... not. 

This worked (note no `--language influxql`) on Linux (Bash). I had to use double quotes and surround everything with single.

```sh
influxdb3 query 'SELECT DISTINCT "serialNumber", "manufacturer", "productID", "physicalLocation_slot","ssdWearLife_spareBlocksRemainingPercent" FROM drives WHERE "ssdWearLife_isWearLifeMonitoringSupported"=TRUE ORDER BY "ssdWearLife_spareBlocksRemainingPercent"'
```

This works:

```sh
influxdb3 query 'SELECT "serialNumber" FROM drives WHERE "ssdWearLife_isWearLifeMonitoringSupported"=TRUE ORDER BY "ssdWearLife_spareBlocksRemainingPercent"'
```

... and this does not (`serialNumber` without double quotes):

```sh
# NG
$ influxdb3 query 'SELECT serialNumber FROM drives WHERE "ssdWearLife_isWearLifeMonitoringSupported"=TRUE ORDER BY "ssdWearLife_spareBlocksRemainingPercent"'
```

Similar CLI queries with **SQL**:

```sql
influxdb3 query --language sql \
  'SELECT "softwareVersion", "physicalLocation_slot" 
     FROM drives'
+-----------------+-----------------------+
| softwareVersion | physicalLocation_slot |
+-----------------+-----------------------+
| NA54            | 12                    |
| NQ02            | 2                     |
| NQ02            | 3                     |
| NA50            | 11                    |
| NA50            | 15                    |
| NA50            | 16                    |
| NA50            | 13                    |
| NA50            | 24                    |
| NA50            | 18                    |
| NA50            | 8                     |
| NA50            | 19                    |
| NA50            | 10                    |
| NA50            | 23                    |
| NA50            | 14                    |
| NA50            | 4                     |
| NA50            | 20                    |
| NQ02            | 22                    |
| NA50            | 21                    |
| NA50            | 17                    |
| NQ02            | 6                     |
| NQ02            | 9                     |
| NQ02            | 1                     |
| NA50            | 7                     |
| NQ02            | 5                     |
+-----------------+-----------------------+

influxdb3 query --language sql \
  'SELECT "softwareVersion","physicalLocation_slot"
     FROM drives
    WHERE "softwareVersion" <> '\''NA54'\'''

```

In SQL and hence **InfluxDB Explorer** ), we'd probably pick more details and sort by certain properties (E-Series' `system_id`, slot, etc.).

```sql
SELECT "system_name","manufacturer","productID", "physicalLocation_slot","softwareVersion"
     FROM drives
    WHERE "softwareVersion" <> '\''NA54\'''  ORDER BY "physicalLocation_slot" ASC
```

That would work fine for 2U controllers without expansion enclosures, but if you have multi-shelf or multi-tray systems, maybe  you want to add additional column.

```sh
SELECT "system_name","physicalLocation_trayRef","physicalLocation_slot","manufacturer","productID", "softwareVersion"
     FROM drives
    WHERE "softwareVersion" <> '\''NA54\'''
```

## `failures` - failure events

Fields:

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM failures'
+------------------+----------+-----------+
| iox::measurement | fieldKey | fieldType |
+------------------+----------+-----------+
| failures         | name_of  | string    |
| failures         | type_of  | string    |
+------------------+----------+-----------+
```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM failures'
+------------------+--------------+
| iox::measurement | tagKey       |
+------------------+--------------+
| failures         | active       |
| failures         | failure_type |
| failures         | object_ref   |
| failures         | object_type  |
| failures         | sys_id       |
| failures         | sys_name     |
+------------------+--------------+
```

In **InfluxDB Explorer**, identify failures for a time range:

```sql
SELECT failure_type, time
  FROM failures  
  WHERE time >= '2025-08-13T11:00:00' AND time < '2025-08-13T14:00:00'
```

Also in **InfluxDB Explorer**, list only active failures from last six hours.

```sql
SELECT failure_type, time, active
  FROM failures
  WHERE time >= now() - interval '6 hours' AND active = 'True'
```

`TRUE` is string type because tags are stored as strings (this drove me nuts).

In Bash **shell** using the CLI (also SQL):

```sh
influxdb3 query \
  "SELECT failure_type, time, active
    FROM failures
    WHERE active = 'True'"
```

Also in Bash but using `--language influxql`: I couldn't make any smart examples.


## `health_check` 

Fields:

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM health_check'
+------------------+----------+-----------+
| iox::measurement | fieldKey | fieldType |
+------------------+----------+-----------+
| health_check     | value    | float     |
+------------------+----------+-----------+

```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM health_check'
+------------------+--------+
| iox::measurement | tagKey |
+------------------+--------+
| health_check     | source |
| health_check     | test   |
+------------------+--------+

```


## `interface` - interfaces' metrics

"Outbound" (host-facing) interfaces are useful to see and understand how well E-Series' clients are balancing workload across controller ports. 

For load-balancing across controllers, see `controllers`.

Fields:

```sh
influxdb3 query --language influxql 'SHOW FIELD KEYS FROM interface'
+------------------+----------------------+-----------+
| iox::measurement | fieldKey             | fieldType |
+------------------+----------------------+-----------+
| interface        | averageReadOpSize    | float     |
| interface        | averageWriteOpSize   | float     |
| interface        | channelErrorCounts   | float     |
| interface        | combinedIOps         | float     |
| interface        | combinedResponseTime | float     |
| interface        | combinedThroughput   | float     |
| interface        | otherIOps            | float     |
| interface        | queueDepthMax        | float     |
| interface        | queueDepthTotal      | float     |
| interface        | readIOps             | float     |
| interface        | readOps              | float     |
| interface        | readResponseTime     | float     |
| interface        | readThroughput       | float     |
| interface        | writeIOps            | float     |
| interface        | writeOps             | float     |
| interface        | writeResponseTime    | float     |
| interface        | writeThroughput      | float     |
+------------------+----------------------+-----------+

```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM interface'
+------------------+--------------+
| iox::measurement | tagKey       |
+------------------+--------------+
| interface        | channel_type |
| interface        | interface_id |
| interface        | sys_id       |
| interface        | sys_name     |
+------------------+--------------+

```

When selecting we may group by interface, or by E-Series system, which we get from `sys_id` tag values:

```sh
$ influxdb3 query --language influxql "SELECT LAST(channelErrorCounts) FROM interface GROUP BY interface_id"
+------------------+---------------------+------------------------------------------+------+
| iox::measurement | time                | interface_id                             | last |
+------------------+---------------------+------------------------------------------+------+
| interface        | 2025-08-13T15:15:00 | 2201000000000000000000000000000000000000 | 0.0  |
| interface        | 2025-08-13T15:15:00 | 2201020000000000000000000000000000000000 | 0.0  |
| interface        | 2025-08-13T15:15:00 | 2201030000000000000000000000000000000000 | 0.0  |
| interface        | 2025-08-13T15:15:00 | 2201040000000000000000000000000000000000 | 0.0  |
| interface        | 2025-08-13T15:15:00 | 2201050000000000000000000000000000000000 | 0.0  |
| interface        | 2025-08-13T15:15:00 | 2202010000000000000000000000000000000000 | 0.0  |
| interface        | 2025-08-13T15:15:00 | 2202020000000000000000000000000000000000 | 0.0  |
| interface        | 2025-08-13T15:15:00 | 2202030000000000000000000000000000000000 | 0.0  |
| interface        | 2025-08-13T15:15:00 | 2202040000000000000000000000000000000000 | 0.0  |
| interface        | 2025-08-13T15:15:00 | 2202050000000000000000000000000000000000 | 0.0  |
+------------------+---------------------+------------------------------------------+------+

$ influxdb3 query --language influxql 'SHOW TAG VALUES FROM interface WITH key= "sys_id"'
+------------------+--------+----------------------------------+
| iox::measurement | key    | value                            |
+------------------+--------+----------------------------------+
| interface        | sys_id | 6D039EA00041F29A0000000065FCE1F0 |
| interface        | sys_id | 6D039EA0004259B00000000066531FD6 |
| interface        | sys_id | 6D039EA0004D0072000000006596A217 |
| interface        | sys_id | 6D039EA0004D00AA000000006652A086 |
+------------------+--------+----------------------------------+

$ influxdb3 query --language influxql "SELECT LAST(channelErrorCounts) FROM interface GROUP BY sys_id"
+------------------+---------------------+----------------------------------+------+
| iox::measurement | time                | sys_id                           | last |
+------------------+---------------------+----------------------------------+------+
| interface        | 2025-08-13T15:15:00 | 6D039EA00041F29A0000000065FCE1F0 | 0.0  |
| interface        | 2025-08-13T11:11:00 | 6D039EA0004259B00000000066531FD6 | 0.0  |
| interface        | 2025-08-13T11:12:00 | 6D039EA0004D0072000000006596A217 | 0.0  |
| interface        | 2025-08-13T15:04:00 | 6D039EA0004D00AA000000006652A086 | 0.0  |
+------------------+---------------------+----------------------------------+------+
```

And of course this tripped me a dozen times - tags and values both must be quoted.

```sh
$ influxdb3 query --language influxql \
   "SELECT LAST(channelErrorCounts) 
     FROM interface 
    WHERE \"sys_id\" = '6D039EA0004259B00000000066531FD6'"
+------------------+---------------------+------+
| iox::measurement | time                | last |
+------------------+---------------------+------+
| interface        | 2025-08-13T11:11:00 | 0.0  |
+------------------+---------------------+------+
```


## `major_event_log` - MEL logs

Table for [major system events](https://duckduckgo.com/?t=lm&q=mel+eseries+netapp&ia=web). A better place to understand this topic may be [this](https://scaleoutsean.github.io/2022/12/13/eseries-santricity-mel-forwarding.html).

Fields:

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM major_event_log'
+------------------+-------------+-----------+
| iox::measurement | fieldKey    | fieldType |
+------------------+-------------+-----------+
| major_event_log  | description | string    |
| major_event_log  | id          | string    |
| major_event_log  | location    | string    |
+------------------+-------------+-----------+

```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM major_event_log'
+------------------+------------+
| iox::measurement | tagKey     |
+------------------+------------+
| major_event_log  | asc        |
| major_event_log  | ascq       |
| major_event_log  | category   |
| major_event_log  | critical   |
| major_event_log  | event_type |
| major_event_log  | priority   |
| major_event_log  | sys_id     |
| major_event_log  | sys_name   |
| major_event_log  | time_stamp |
+------------------+------------+

```

## `power` - power supply units' readings

Most people like to gather and watch these, although they're quite useless. 

Fields:

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM power'
+------------------+------------------------+-----------+
| iox::measurement | fieldKey               | fieldType |
+------------------+------------------------+-----------+
| power            | calculatedTotalPower   | float     |
| power            | numberOfTrays          | float     |
| power            | powerValidation        | string    |
| power            | returnCode             | string    |
| power            | totalPower             | float     |
| power            | tray99_psu0_inputPower | float     |
| power            | tray99_psu1_inputPower | float     |
| power            | tray99_totalPower      | float     |
+------------------+------------------------+-----------+

```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM power'
+------------------+-------------+
| iox::measurement | tagKey      |
+------------------+-------------+
| power            | return_code |
| power            | sys_id      |
| power            | sys_name    |
+------------------+-------------+

```

## `systems` - system-level performance metrics

These are "overall" storage system performance metrics aggregated from both controllers if two are available. The source is obviously one and it's tagged with `source_controller`. In itself the source does not matter, but I mention it because in case of re-connection or interruption the next reading may come from the other controller. 

`controllers` table may contains the details for individual controllers.

Fields:

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM systems'
+------------------+---------------------------------+-----------+
| iox::measurement | fieldKey                        | fieldType |
+------------------+---------------------------------+-----------+
| systems          | averageReadOpSize               | float     |
| systems          | averageWriteOpSize              | float     |
| systems          | cacheHitBytesPercent            | float     |
| systems          | combinedHitResponseTime         | float     |
| systems          | combinedHitResponseTimeStdDev   | float     |
| systems          | combinedIOps                    | float     |
| systems          | combinedResponseTime            | float     |
| systems          | combinedResponseTimeStdDev      | float     |
| systems          | combinedThroughput              | float     |
| systems          | cpuAvgUtilization               | float     |
| systems          | ddpBytesPercent                 | float     |
| systems          | fullStripeWritesBytesPercent    | float     |
| systems          | maxCpuUtilization               | float     |
| systems          | maxPossibleBpsUnderCurrentLoad  | float     |
| systems          | maxPossibleIopsUnderCurrentLoad | float     |
| systems          | mirrorBytesPercent              | float     |
| systems          | observedTime                    | string    |
| systems          | observedTimeInMS                | string    |
| systems          | otherIOps                       | float     |
| systems          | raid0BytesPercent               | float     |
| systems          | raid1BytesPercent               | float     |
| systems          | raid5BytesPercent               | float     |
| systems          | raid6BytesPercent               | float     |
| systems          | randomIosPercent                | float     |
| systems          | readHitResponseTime             | float     |
| systems          | readHitResponseTimeStdDev       | float     |
| systems          | readIOps                        | float     |
| systems          | readOps                         | float     |
| systems          | readPhysicalIOps                | float     |
| systems          | readResponseTime                | float     |
| systems          | readResponseTimeStdDev          | float     |
| systems          | readThroughput                  | float     |
| systems          | writeHitResponseTime            | float     |
| systems          | writeHitResponseTimeStdDev      | float     |
| systems          | writeIOps                       | float     |
| systems          | writeOps                        | float     |
| systems          | writePhysicalIOps               | float     |
| systems          | writeResponseTime               | float     |
| systems          | writeResponseTimeStdDev         | float     |
| systems          | writeThroughput                 | float     |
+------------------+---------------------------------+-----------+

```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM systems'
+------------------+-------------------+
| iox::measurement | tagKey            |
+------------------+-------------------+
| systems          | source_controller |
| systems          | sys_id            |
| systems          | sys_name          |
+------------------+-------------------+

```

## `temp` - temperature sensors

This is expected to show several (at least inlet temperature, CPU temperature) per controller and maybe the same for shelves, but due to limited hardware access the exact number isn't known to me yet. EPA Collector should handles any number of sensors.

Fields:

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM temp'
+------------------+------------------+-----------+
| iox::measurement | fieldKey         | fieldType |
+------------------+------------------+-----------+
| temp             | sensor_index     | float     |
| temp             | status_indicator | string    |
| temp             | temp             | float     |
+------------------+------------------+-----------+

```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM temp'
+------------------+---------------+
| iox::measurement | tagKey        |
+------------------+---------------+
| temp             | sensor_ref    |
| temp             | sensor_seq    |
| temp             | sensor_status |
| temp             | sensor_type   |
| temp             | sys_id        |
| temp             | sys_name      |
+------------------+---------------+

```

## `volumes` - volume performance metrics

This is the the main place to monitor a volume or volumes. 

To watch "consistency groups", we should have a field or tag. It's unclear if anyone needs that so for time being that's not implemented. As a workaround, it's possible to select a collection of tags (`vol_name`) and aggregate in SQL or Grafana.

Fields:

```sh
$ influxdb3 query --language influxql 'SHOW FIELD KEYS FROM volumes'
+------------------+----------------------------+-----------+
| iox::measurement | fieldKey                   | fieldType |
+------------------+----------------------------+-----------+
| volumes          | averageReadOpSize          | float     |
| volumes          | averageWriteOpSize         | float     |
| volumes          | combinedIOps               | float     |
| volumes          | combinedResponseTime       | float     |
| volumes          | combinedThroughput         | float     |
| volumes          | flashCacheHitPct           | float     |
| volumes          | flashCacheReadHitBytes     | float     |
| volumes          | flashCacheReadHitOps       | float     |
| volumes          | flashCacheReadResponseTime | float     |
| volumes          | flashCacheReadThroughput   | float     |
| volumes          | otherIOps                  | float     |
| volumes          | queueDepthMax              | float     |
| volumes          | queueDepthTotal            | float     |
| volumes          | readCacheUtilization       | float     |
| volumes          | readHitBytes               | float     |
| volumes          | readHitOps                 | float     |
| volumes          | readIOps                   | float     |
| volumes          | readOps                    | float     |
| volumes          | readPhysicalIOps           | float     |
| volumes          | readResponseTime           | float     |
| volumes          | readThroughput             | float     |
| volumes          | writeCacheUtilization      | float     |
| volumes          | writeHitBytes              | float     |
| volumes          | writeHitOps                | float     |
| volumes          | writeIOps                  | float     |
| volumes          | writeOps                   | float     |
| volumes          | writePhysicalIOps          | float     |
| volumes          | writeResponseTime          | float     |
| volumes          | writeThroughput            | float     |
+------------------+----------------------------+-----------+

```

Tags:

```sh
$ influxdb3 query --language influxql 'SHOW TAG KEYS FROM volumes'
+------------------+----------+
| iox::measurement | tagKey   |
+------------------+----------+
| volumes          | sys_id   |
| volumes          | sys_name |
| volumes          | vol_name |
+------------------+----------+

```

Here we may want to select volumes, time periods, calculate average values by interval, etc.


```sh
$ influxdb3 query --language influxql \
  "SELECT flashCacheHitPct, readCacheUtilization
     FROM volumes
    WHERE \"vol_name\" = 'stor_02_tgt_0202'
      AND time >= now() - 12h
    LIMIT 5"
+------------------+---------------------+------------------+----------------------+
| iox::measurement | time                | flashCacheHitPct | readCacheUtilization |
+------------------+---------------------+------------------+----------------------+
| volumes          | 2025-08-13T11:07:00 | 0.0              | 0.0                  |
| volumes          | 2025-08-13T11:08:00 | 0.0              | 0.0                  |
| volumes          | 2025-08-13T11:09:00 | 0.0              | 0.0                  |
| volumes          | 2025-08-13T11:09:00 | 0.0              | 0.0                  |
| volumes          | 2025-08-13T11:10:00 | 0.0              | 0.0                  |
+------------------+---------------------+------------------+----------------------+

```

A volume's `MEAN` cache-related metrics for the past 24 hours calculated over 5 minute intervals.

```sh
influxdb3 query --language influxql \
  "SELECT 
     MEAN(flashCacheHitPct)  AS avgFlashCacheHitPct,
     MEAN(readCacheUtilization) AS avgReadCacheUtilization
   FROM volumes
  WHERE \"vol_name\" = 'stor_02_tgt_0202'
    AND time >= now() - 24h
  GROUP BY time(5m) fill(none)"
+------------------+---------------------+---------------------+-------------------------+
| iox::measurement | time                | avgFlashCacheHitPct | avgReadCacheUtilization |
+------------------+---------------------+---------------------+-------------------------+
| volumes          | 2025-08-13T11:05:00 | 0.0                 | 0.0                     |
| volumes          | 2025-08-13T11:10:00 | 0.0                 | 0.0                     |
| volumes          | 2025-08-13T15:00:00 | 0.0                 | 0.0                     |
| volumes          | 2025-08-13T15:15:00 | 0.0                 | 0.0                     |
+------------------+---------------------+---------------------+-------------------------+
```

Recall that EPA queries E-Series' `analysed-<object>` statistics, so by the time those metrics get to InfluxDB they have been sliced and diced and because of that calculating averages, means and similar for short intervals such as 5 minutes is probably misleading at best. The [FAQs](FAQ.md) have a bit more on this.

