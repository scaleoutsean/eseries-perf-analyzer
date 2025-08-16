# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

"""
Metrics configuration for E-Series Perf Analyzer
Defines lists of metrics parameters for different resource types.
"""

# Controller metrics parameters
# Note: CONTROLLER_PARAMS is legacy - The system collector provides aggregated 
# controller performance data in every interval, while controller metrics are
#  gathered every CONTROLLER_COLLECTION_INTERVAL seconds. 
# See SYSTEM and CONTROLLER collectors for current implementation.

CONTROLLER_PARAMS = [
    "observedTime",
    "observedTimeInMS",
    "sourceController",
    "readIOps",
    "writeIOps",
    "otherIOps",
    "combinedIOps",
    "readThroughput",
    "writeThroughput",
    "combinedThroughput",
    "readResponseTime",
    "readResponseTimeStdDev",
    "writeResponseTime",
    "writeResponseTimeStdDev",
    "combinedResponseTime",
    "combinedResponseTimeStdDev",
    "averageReadOpSize",
    "averageWriteOpSize",
    "readOps",
    "writeOps",
    "readPhysicalIOps",
    "writePhysicalIOps",
    "controllerId",
    "cacheHitBytesPercent",
    "randomIosPercent",
    "mirrorBytesPercent",
    "fullStripeWritesBytesPercent",
    "maxCpuUtilization",
    "maxCpuUtilizationPerCore",
    "cpuAvgUtilization",
    "cpuAvgUtilizationPerCore",
    "cpuAvgUtilizationPerCoreStdDev",
    "raid0BytesPercent",
    "raid1BytesPercent",
    "raid5BytesPercent",
    "raid6BytesPercent",
    "ddpBytesPercent",
    "readHitResponseTime",
    "readHitResponseTimeStdDev",
    "writeHitResponseTime",
    "writeHitResponseTimeStdDev",
    "combinedHitResponseTime",
    "combinedHitResponseTimeStdDev"
]

# Controller fields to exclude from *EPA-processed* JSON output (these are large arrays stored as JSON strings)
# These fields contain per-core CPU utilization arrays that are not useful in InfluxDB
CONTROLLER_FIELDS_EXCLUDED = [
    "maxCpuUtilizationPerCore_json",
    "cpuAvgUtilizationPerCore_json", 
    "cpuAvgUtilizationPerCoreStdDev_json"
]

# Drive metrics parameters
DRIVE_PARAMS = [
    'averageReadOpSize',
    'averageWriteOpSize',
    'combinedIOps',
    'combinedResponseTime',
    'combinedThroughput',
    'otherIOps',
    'readIOps',
    'readOps',
    'readPhysicalIOps',
    'readResponseTime',
    'readThroughput',
    'writeIOps',
    'writeOps',
    'writePhysicalIOps',
    'writeResponseTime',
    'writeThroughput'
]

# Note: DRIVES_PARAMS is not needed - the drives collector automatically
# enumerates all available fields from the drive objects and includes them
# in InfluxDB. See app/drives_collector.py for implementation details.
# DRIVES_COLLECTION_INTERVAL is now configured in app/config.py

# Interface metrics parameters
INTERFACE_PARAMS = [
    "readIOps",
    "writeIOps",
    "otherIOps",
    "combinedIOps",
    "readThroughput",
    "writeThroughput",
    "combinedThroughput",
    "readResponseTime",
    "writeResponseTime",
    "combinedResponseTime",
    "averageReadOpSize",
    "averageWriteOpSize",
    "readOps",
    "writeOps",
    "queueDepthTotal",
    "queueDepthMax",
    "channelErrorCounts"
]

# System metrics parameters
# Note: SYSTEM_PARAMS is not currently used - the system collector automatically
# enumerates all available fields from the system statistics API response and includes them
# in InfluxDB. See app/storage.py for implementation details.
SYSTEM_PARAMS = [
    "maxCpuUtilization",
    "cpuAvgUtilization"
]

# Volume metrics parameters
VOLUME_PARAMS = [
    'averageReadOpSize',
    'averageWriteOpSize',
    'combinedIOps',
    'combinedResponseTime',
    'combinedThroughput',
    'flashCacheHitPct',
    'flashCacheReadHitBytes',
    'flashCacheReadHitOps',
    'flashCacheReadResponseTime',
    'flashCacheReadThroughput',
    'otherIOps',
    'queueDepthMax',
    'queueDepthTotal',
    'readCacheUtilization',
    'readHitBytes',
    'readHitOps',
    'readIOps',
    'readOps',
    'readPhysicalIOps',
    'readResponseTime',
    'readThroughput',
    'writeCacheUtilization',
    'writeHitBytes',
    'writeHitOps',
    'writeIOps',
    'writeOps',
    'writePhysicalIOps',
    'writeResponseTime',
    'writeThroughput'
]

# Major Event Log metrics parameters
MEL_PARAMS = [
    "description",
    "id", 
    "location"
]


# Hardware inventory data is collected as hardware_{WWN}.json files in the --toJson output 
# directory. The hardware inventory API is called every iteration to handle dynamic changes 
# (hot-swap drives, expansion shelves, drive replacements) ensuring new hardware gets proper 
# location tags. The JSON file is overwritten each iteration to show current topology - this 
# is space-efficient since location data is preserved in drive/system metrics tags.
# In other words, hardware inventory has no own measurement, but its data may be included in
# other EPA measurements.
# See app/drives.py get_drive_location() function.

# Sensor (environmental) metrics parameters  
# Note: SENSOR_PARAMS is not currently used - the temperature sensor collector automatically
# enumerates all available sensors and creates individual measurement points for each.
# Each sensor gets its own data point with tags (sensor_ref, sensor_seq, sensor_type).
# The system dynamically handles any number of thermal sensors per array.
# Below shows the fields within each sensor measurement, not hardcoded sensor names.
# See app/symbols_collector.py lines ~280-300 for implementation details.
SENSOR_PARAMS = [
    'temp',              # Temperature value (°C) - actual reading or None for status sensors  
    'sensor_index',      # Sensor index for debugging order changes
    'status_indicator'   # Status indicator for inlet/status sensors ('normal', 'abnormal', or None)
]

# PSU (Power Supply Unit) metrics parameters
# Note: PSU_PARAMS is not currently used - the PSU collector automatically
# enumerates all available fields from the power/energy API response and includes them
# in InfluxDB. Field names are dynamic based on system configuration:
# - tray{N}_psu{M}_inputPower (for N trays, M PSUs per tray)
# - tray{N}_totalPower (total power per tray)
# - totalPower, calculatedTotalPower (system totals)
# See app/symbols_collector.py for implementation details.
# Note that E/EF Series arrays that haven't been fiddled with have controller shelf ID 99 and
# expansion shelves may be 00-98 (but in reality they're auto-added sequentially from 00, 01, up 
# to the max number of shelves each system and configuration supports.)
PSU_PARAMS = [
    'totalPower',
    'calculatedTotalPower', 
    'numberOfTrays',
    'powerValidation',
    'returnCode',
    # Example fields (actual fields are generated dynamically):
    'tray0_psu0_inputPower',
    'tray0_psu1_inputPower', 
    'tray0_totalPower'
]
