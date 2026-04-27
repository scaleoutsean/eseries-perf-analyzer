_str_to_int_was_here = True

def _str_to_int(val):
    try:
        return int(val)
    except:
        return 0

def _str_to_datetime(val):
    return val

def _remove_trailing_bytes(val):
    try:
        return int(val[:-5])
    except:
        return 0

import re

def _to_integer(value):
    try:
        if value is None or value == "":
            return 0
        return int(value)
    except (ValueError, TypeError):
        return value

def normalize_key(key):
    """Normalize arbitrary keys to stable snake_case identifiers."""
    normalized = str(key).strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unknown_key"

def _metadata_kv_list_to_string(value):
    if not isinstance(value, list):
        return value
    pairs: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if key is None:
            continue
        key = normalize_key(key)
        val = item.get("value", "")
        pairs.append(f"{key}={val}")
    return ";".join(pairs)

def _list_to_delimited_string(value, delimiter=";"):
    if not isinstance(value, list):
        return value
    return delimiter.join(str(item) for item in value)

SNAPSHOT_IMAGES_MAPPING = [
    ("activeCOW", "is_active_cow", None),
    ("baseVol", "base_volume", None),
    ("enrich_baseVol", "base_volume_name", None),
    ("consistencyGroupId", "consistency_group_id", None),
    ("enrich_consistencyGroupId", "consistency_group_name", None),
    ("creationMethod", "creation_method", None),
    ("id", "id", None),
    ("isRollbackSource", "is_rollback_source", None),
    ("pitCapacity", "pit_capacity_bytes", _to_integer),
    ("pitGroupRef", "pit_group_ref", None),
    ("enrich_pitGroupRef", "pit_group_name", None),
    ("pitRef", "pit_ref", None),
    ("pitSequenceNumber", "pit_sequence_number", _to_integer),
    ("pitTimestamp", "pit_timestamp", _to_integer),
    ("repositoryCapacityUtilization", "repository_capacity_utilization_bytes", _to_integer),
    ("status", "status", None)
]

SNAPSHOT_GROUPS_MAPPING = [
    ("action", "action", None),
    ("autoDeleteLimit", "auto_delete_limit", None),
    ("baseVolume", "base_volume", None),
    ("enrich_baseVolume", "base_volume_name", None),
    ("consistencyGroupRef", "consistency_group_ref", None),
    ("enrich_consistencyGroupRef", "consistency_group_name", None),
    ("consistencyGroup", "is_consistency_group", None),
    ("creationPendingStatus", "creation_pending_status", None),
    ("fullWarnThreshold", "full_warn_threshold_percent", None),
    ("id", "id", None),
    ("label", "label", None),
    ("name", "name", None),
    ("pitGroupRef", "pit_group_ref", None),
    ("enrich_pitGroupRef", "pit_group_name", None),
    ("repFullPolicy", "rep_full_policy", None),
    ("repositoryCapacity", "repository_capacity_bytes", _to_integer),
    ("repositoryVolume", "repository_volume", None),
    ("enrich_repositoryVolume", "repository_volume_name", None),
    ("rollbackPriority", "rollback_priority", None),
    ("rollbackStatus", "rollback_status", None),
    ("snapshotCount", "snapshot_count", None),
    ("status", "status", None),
    ("volcopyId", "volcopy_id", None)
]

SNAPSHOT_VOLUMES_MAPPING = [
    ("accessMode", "access_mode", None),
    ("asyncMirrorSource", "is_async_mirror_source", None),
    ("asyncMirrorTarget", "is_async_mirror_target", None),
    ("basePIT", "base_pit", None),
    ("baseVol", "base_vol", None),
    ("enrich_baseVol", "base_vol_name", None),
    ("baseVolumeCapacity", "base_volume_capacity_bytes", _to_integer),
    ("boundToPIT", "is_bound_to_pit", None),
    ("cloneCopy", "is_clone_copy", None),
    ("consistencyGroupId", "consistency_group_id", None),
    ("enrich_consistencyGroupId", "consistency_group_name", None),
    ("fullWarnThreshold", "full_warn_threshold_percent", None),
    ("id", "id", None),
    ("label", "label", None),
    ("mapped", "is_mapped", None),
    ("membership_viewType", "membership_view_type", None),
    ("membership_cgViewRef", "membership_cg_view_ref", None),
    ("enrich_membership_cgViewRef", "membership_cg_view_name", None),
    ("name", "name", None),
    ("objectType", "object_type", None),
    ("offline", "is_offline", None),
    ("onlineVolumeCopy", "is_online_volume_copy", None),
    ("pitBaseVolume", "is_pit_base_volume", None),
    ("remoteMirrorSource", "is_remote_mirror_source", None),
    ("remoteMirrorTarget", "is_remote_mirror_target", None),
    ("repositoryCapacity", "repository_capacity_bytes", _to_integer),
    ("repositoryVolume", "repository_volume", None),
    ("enrich_repositoryVolume", "repository_volume_name", None),
    ("status", "status", None),
    ("totalSizeInBytes", "total_size_in_bytes", _to_integer),
    ("viewRef", "view_ref", None),
    ("enrich_viewRef", "view_name", None),
    ("viewSequenceNumber", "view_sequence_number", _to_integer),
    ("viewTime", "view_time", _to_integer),
    ("volumeCopySource", "is_volume_copy_source", None),
    ("volumeCopyTarget", "is_volume_copy_target", None),
    ("volumeFull", "is_volume_full", None),
    ("worldWideName", "world_wide_name", None)
]

REPOSITORIES_CONCAT_MAPPING = [
    ("concatVolRef", "concat_vol_ref", None),
    ("status", "status", None),
    ("memberCount", "member_count", None),
    ("aggregateCapacity", "aggregate_capacity_bytes", _to_integer),
    ("mediaScanParams_enable", "media_scan_params_enable", None),
    ("mediaScanParams_parityValidationEnable", "media_scan_params_parity_validation_enable", None),
    ("memberRefs", "member_refs", _list_to_delimited_string),
    ("baseObjectType", "base_object_type", None),
    ("baseObjectId", "base_object_id", None),
    ("id", "id", None)
]

SNAPSHOT_GROUP_REPOSITORY_UTILIZATION_MAPPING = [
    ("enrich_groupRef", "group_name", None),
    ("pitGroupBytesUsed", "pit_group_bytes_used", _to_integer),
    ("pitGroupBytesAvailable", "pit_group_bytes_available", _to_integer),
    ("groupRef", "group_ref", None)
]

SNAPSHOT_VOLUMES_REPOSITORY_UTILIZATION_MAPPING = [
    ("enrich_viewRef", "view_name", None),
    ("viewBytesUsed", "view_bytes_used", _to_integer),
    ("viewBytesAvailable", "view_bytes_available", _to_integer),
    ("viewRef", "view_ref", None),
]

CONSISTENCY_GROUPS_MAPPING = [
    ("id", "id", None),
    ("name", "name", None),
    ("label", "label", None),
    ("repFullPolicy", "rep_full_policy", None),
]

CONSISTENCY_GROUPS_MEMBER_VOLUMES_MAPPING = [
    ("enrich_consistencyGroupId", "consistency_group_name", None),
    ("consistencyGroupId", "consistency_group_id", None),
    ("volumeId", "volume_id", None),
    ("enrich_pitGroupId", "pit_group_name", None),
    ("pitGroupId", "pit_group_id", None),
    ("baseVolumeName", "base_volume_name", None),
]

SNAPSHOT_SCHEDULES_MAPPING = [
    ("id", "id", None),
    ("schedRef", "sched_ref", None),
    ("scheduleStatus", "schedule_status", None),
    ("action", "action", None),
    ("targetObject", "target_object", None),
    ("creationTime", "creation_time", _to_integer),
    ("lastRunTime", "last_run_time", _to_integer),
    ("nextRunTime", "next_run_time", _to_integer),
    ("stopTime", "stop_time", _to_integer),
    ("schedule_startDate", "schedule_start_date", _to_integer),
]

CONFIG_VOLUMES_MAPPING = [
    ("offline", "offline", None),
    ("extremeProtection", "extreme_protection", None),
    ("mapped", "mapped_to_host", None),
    ("raidLevel", "raid_level", None),
    ("worldWideName", "wwn", None),
    ("label", "label", None),
    ("blkSize", "block_size", None),
    ("capacity", "capacity", int),
    ("segmentSize", "segment_size", None),
    ("mediaScan_enable", "media_scan_enable", None), 
    ("mediaScan_parityValidationEnable", "media_scan_parity_validation_enable", None),
    ("volumeRef", "volume_ref", None),
    ("status", "status", None),
    ("volumeGroupRef", "volume_group_ref", None),
    ("dssPreallocEnabled", "dss_preallocation_enabled", None),
    ("applicationTagOwned", "is_application_tag_owned", None),
    ("repairedBlockCount", "repaired_block_count", None),
    ("blkSizePhysical", "block_size_physical", None),
    ("allocGranularity", "allocation_granularity", int),
    ("volumeUse", "is_volume_in_use", None),
    ("volumeFull", "is_volume_full", None),
    ("volumeCopyTarget", "volume_copy_target", None),
    ("volumeCopySource", "volume_copy_source", None),
    ("pitBaseVolume", "pit_base_volume", None),
    ("asyncMirrorTarget", "is_async_mirror_target", None),
    ("asyncMirrorSource", "is_async_mirror_source", None),
    ("remoteMirrorSource", "is_remote_mirror_source", None),
    ("remoteMirrorTarget", "is_remote_mirror_target", None),
    ("diskPool", "is_disk_pool", None),
    ("flashCached", "is_flash_cached", None),
    ("metadata","metadata", lambda v: _metadata_kv_list_to_string(v)), # list[{"key":...,"value":...}] -> "key=value;..."
    ("dataAssurance", "is_data_assurance_enabled", None),
    ("objectType", "object_type", None),
    ("totalSizeInBytes", "total_size_in_bytes", int),
    ("onlineVolumeCopy", "online_volume_copy", None),
    ("name", "volume_name", None),
    ("id", "id", None),
    ("mapped_host_names", "mapped_host_names", None),
    ("mapped_host_count", "mapped_host_count", int),
    ("listOfMappings_lunMappingRef", "lun_mapping_ref", None),
    ("listOfMappings_lun", "lun", int),
    ("listOfMappings_ssid", "ssid", int)
]

STORAGE_POOLS_MAPPING = [
    ("name", "pool_name", None),
    ("id", "id", None),
    ("volumeGroupRef", "volume_group_ref", None),
    ("label", "label", None),
    ("sequenceNum", "sequence_num", int),
    ("offline", "offline", None),
    ("raidStatus", "state", None),
    ("drivePhysicalType", "drive_media_type", None),
    ("spindleSpeedMatch", "spindle_speed_match", None),
    ("isInaccessible", "is_inaccessible", None),
    ("drawerLossProtection", "drawer_loss_protection", None),
    ("protectionInformationCapable", "protection_information_capable", None),
    ("reservedSpaceAllocated", "reserved_space_allocated", None),
    ("diskPool", "is_disk_pool", None),
    ("usedSpace", "used_space", int),
    ("totalRaidedSpace", "total_raided_space", int),
    ("freeSpace", "free_space", int),
    ("blkSizeRecommended", "block_size_recommended", None),
    ("blkSizeSupported_512", "block_size_supported_512", None),
    ("blkSizeSupported_4096", "block_size_supported_4096", None),
    ("volumeGroupData_type", "volume_group_type", None),
    ("extents_rawCapacity", "extents_raw_capacity", int),
    ("extents_raidLevel", "raid_level", None)
]


HOST_GROUPS_MAPPING = [
    ("id", "id", None),
    ("clusterRef", "cluster_ref", None),
    ("label", "label", None),
    ("name", "name", None)
]

HOSTS_MAPPING = [
    ("id", "id", None),
    ("hostRef", "host_ref", None),
    ("name", "host_name", None),
    ("label", "label", None),
    ("hostTypeIndex", "host_type_index", _to_integer),
    ("clusterRef", "cluster_ref", None),
    ("isSAControlled", "is_sa_controlled", None),
    ("confirmLUNMappingCreation", "confirm_lun_mapping_creation", None),
    ("protectionInformationCapableAccessMethod", "protection_information_capable_access_method", None),
    ("isLargeBlockFormatHost", "is_large_block_format_host", None),
    ("isLun0Restricted", "is_lun0_restricted", None)
]

GLOBAL_ID_CACHE = {}

def apply_mapping(item, mapping):
    """
    Applies the tuple-based mapping filtering and coercion, with built-in id-to-name enrichment.
    Assumes `item` has already been flattened if needed.
    """
    result = {}
    for orig_key, new_key, coercion_func in mapping:
        if orig_key.startswith("enrich_"):
            source_id_key = orig_key.replace("enrich_", "")
            source_id_val = item.get(source_id_key)
            if source_id_val == "0000000000000000000000000000000000000000":
                val = "none"
            else:
                val = GLOBAL_ID_CACHE.get(source_id_val, "unknown") if source_id_val else "unknown"
            if coercion_func is not None:
                val = coercion_func(val)
            result[new_key] = val
        elif orig_key in item:
            val = item.get(orig_key)
            if coercion_func is not None:
                val = coercion_func(val)
            result[new_key] = val
    return result

def flatten_dict_one_level(item):
    """
    Flattens a dictionary exactly one level deep.
    Example: {"mediaScan_enable": {"enabled": True}} -> {"mediaScan_enable_enabled": True}
    """
    result = {}
    for key, value in item.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                result[f"{key}_{sub_key}"] = sub_value
        else:
            result[key] = value
    return result

def extract_tag_keys(mapping):
    """Returns a list of final keys that are tags (coercion is None or string-producing)."""
    return [new_key for orig, new_key, coerc in mapping if coercion_func_is_tag(coerc)]

def extract_field_keys(mapping):
    """Returns a list of final keys that are fields (numeric)."""
    return [new_key for orig, new_key, coerc in mapping if not coercion_func_is_tag(coerc)]

def coercion_func_is_tag(coercion_func):
    """If there's no coercion or it coerces to a string, it's a tag/label."""
    if coercion_func is None:
        return True
    if coercion_func in (_metadata_kv_list_to_string, _list_to_delimited_string):
        return True
    return False


# System overview metrics
STORAGE_SYSTEM_INFO_KEYS = [
  ("name", "name", None),
  ("wwn", "world_wide_name", None),
  ("passwordStatus", "password_status", None),
  ("passwordSet", "is_password_set", None),
  ("status", "status", None),
  ("certificateStatus", "certificate_status", None),
  ("ip1", "ip_address_1", None),
  ("traceEnabled", "is_trace_enabled", None),
  ("model", "model", None),
  ("resourceProvisionedVolumesEnabled", "is_resource_provisioned_volumes_enabled", None),
  ("bootVersion", "boot_version", None),
  ("nvsramVersion", "nvsram_version", None),
  ("chassisSerialNumber", "chassis_serial_number", None),
  ("driveChannelPortDisabled", "is_drive_channel_port_disabled", None),
  ("recoveryModeEnabled", "is_recovery_mode_enabled", None),
  ("autoLoadBalancingEnabled", "is_auto_load_balancing_enabled", None),
  ("hostConnectivityReportingEnabled", "is_host_connectivity_reporting_enabled", None),
  ("remoteMirroringEnabled", "is_remote_mirroring_enabled", None),
  ("fcRemoteMirroringState", "fc_remote_mirroring_state", None),
  ("asupEnabled", "is_asup_enabled", None),
  ("securityKeyEnabled", "is_security_key_enabled", None),
  ("externalKeyEnabled", "is_external_key_enabled", None),
  ("simplexModeEnabled", "is_simplex_mode_enabled", None),
  ("invalidSystemConfig", "has_invalid_system_config", None),
]

STORAGE_SYSTEM_GAUGE_KEYS = [
  ("driveCount", "drive_count", None),
  ("trayCount", "tray_count", None),
  ("usedPoolSpace", "used_pool_space", _str_to_int),
  ("freePoolSpace", "free_pool_space", _str_to_int),
  ("unconfiguredSpace", "unconfigured_space", _str_to_int),
  ("hotSpareCount", "hot_spare_count", None),
  ("hostSparesUsed", "host_spares_used", None),
  ("mediaScanPeriod", "media_scan_period_days", None),
  ("definedPartitionCount", "defined_partition_count", None),
  ("unconfiguredSpaceAsStrings", "unconfigured_space_bytes", _str_to_int),
  ("freePoolSpaceAsString", "free_pool_space_bytes", _str_to_int),
  ("hotSpareSizeAsString", "hot_spare_size_bytes", _str_to_int),
  ("usedPoolSpaceAsString", "used_pool_space_bytes", _str_to_int),
]

PROMETHEUS_METRICS_CONFIG = {
    'disks': {
        'iops': {
            'name': 'eseries_disk_iops_total',
            'desc': 'Total IOPS for disk',
            'labels': ['sys_id', 'sys_name', 'sys_tray', 'sys_tray_slot', 'vol_group_name']
        },
        'throughput': {
            'name': 'eseries_disk_throughput_bytes_per_second',
            'desc': 'Disk throughput in bytes/sec',
            'labels': ['sys_id', 'sys_name', 'sys_tray', 'sys_tray_slot', 'vol_group_name', 'direction']
        },
        'response_time': {
            'name': 'eseries_disk_response_time_seconds',
            'desc': 'Disk response time in seconds',
            'labels': ['sys_id', 'sys_name', 'sys_tray', 'sys_tray_slot', 'vol_group_name', 'operation']
        },
        'ssd_wear': {
            'name': 'eseries_disk_ssd_wear_percent',
            'desc': 'SSD wear level percentage',
            'labels': ['sys_id', 'sys_name', 'sys_tray', 'sys_tray_slot', 'vol_group_name', 'metric']
        }
    },
    'controllers': {
        'iops': {
            'name': 'eseries_controller_iops_total',
            'desc': 'Controller IOPS',
            'labels': ['sys_id', 'sys_name', 'controller_id', 'operation']
        },
        'throughput': {
            'name': 'eseries_controller_throughput_bytes_per_second',
            'desc': 'Controller throughput in bytes/sec',
            'labels': ['sys_id', 'sys_name', 'controller_id', 'direction']
        },
        'cpu_utilization': {
            'name': 'eseries_controller_cpu_utilization_percent',
            'desc': 'Controller CPU utilization',
            'labels': ['sys_id', 'sys_name', 'controller_id', 'metric']
        },
        'cache_hit': {
            'name': 'eseries_controller_cache_hit_percent',
            'desc': 'Controller cache hit percentage',
            'labels': ['sys_id', 'sys_name', 'controller_id']
        }
    },
    'volumes': {
        'iops': {
            'name': 'eseries_volume_iops_total',
            'desc': 'Volume IOPS',
            'labels': ['sys_id', 'sys_name', 'vol_name', 'operation']
        },
        'throughput': {
            'name': 'eseries_volume_throughput_bytes_per_second',
            'desc': 'Volume throughput in bytes/sec',
            'labels': ['sys_id', 'sys_name', 'vol_name', 'direction']
        },
        'response_time': {
            'name': 'eseries_volume_response_time_seconds',
            'desc': 'Volume response time in seconds',
            'labels': ['sys_id', 'sys_name', 'vol_name', 'operation']
        }
    },
    'system_status': {
        'epa_status': {
            'name': 'eseries_epa_status',
            'desc': 'EPA collector status (1=OK, 0=Error/Unreachable)',
            'labels': ['sys_id', 'sys_name', 'endpoint']
        }
    },
    'interface': {
        'iops': {
            'name': 'eseries_interface_iops_total',
            'desc': 'Interface IOPS',
            'labels': ['sys_id', 'sys_name', 'interface_id', 'channel_type', 'operation']
        },
        'throughput': {
            'name': 'eseries_interface_throughput_bytes_per_second',
            'desc': 'Interface throughput in bytes/sec',
            'labels': ['sys_id', 'sys_name', 'interface_id', 'channel_type', 'direction']
        },
        'queue_depth': {
            'name': 'eseries_interface_queue_depth',
            'desc': 'Interface queue depth',
            'labels': ['sys_id', 'sys_name', 'interface_id', 'channel_type', 'metric']
        }
    },
    'power': {
        'total_power': {
            'name': 'eseries_power_consumption_watts',
            'desc': 'Total power consumption in watts',
            'labels': ['sys_id', 'sys_name']
        }
    },
    'temp': {
        'temperature': {
            'name': 'eseries_temperature_celsius',
            'desc': 'Temperature in Celsius',
            'labels': ['sys_id', 'sys_name', 'sensor', 'sensor_seq']
        }
    },
    'flashcache': {
        'bytes': {
            'name': 'eseries_flashcache_bytes',
            'desc': 'Flash Cache byte metrics',
            'labels': ['sys_id', 'sys_name', 'flash_cache_id', 'flash_cache_name', 'metric']
        },
        'blocks': {
            'name': 'eseries_flashcache_blocks_total',
            'desc': 'Flash Cache block metrics (delta)',
            'labels': ['sys_id', 'sys_name', 'flash_cache_id', 'flash_cache_name', 'metric']
        },
        'ops': {
            'name': 'eseries_flashcache_ops_total',
            'desc': 'Flash Cache operations (delta)',
            'labels': ['sys_id', 'sys_name', 'flash_cache_id', 'flash_cache_name', 'metric']
        },
        'components': {
            'name': 'eseries_flashcache_components',
            'desc': 'Flash Cache related component counts',
            'labels': ['sys_id', 'sys_name', 'flash_cache_id', 'flash_cache_name', 'metric']
        }
    },
    'failures': {
        'active_failures': {
            'name': 'eseries_active_failures_total',
            'desc': 'Number of active failures',
            'labels': ['sys_id', 'sys_name', 'failure_type', 'object_type', 'object_ref']
        }
    },
    'config_volumes': {
        'info': {
            'name': 'eseries_volume_info',
            'desc': 'Volume configuration info',
            'labels': ['sys_id', 'sys_name', 'wwn', 'label', 'volume_ref', 'volume_name', 'id', 'volume_group_ref', 'raid_level', 'status', 'is_disk_pool']
        },
        'capacity_bytes': {
            'name': 'eseries_volume_capacity_bytes',
            'desc': 'Volume capacity in bytes',
            'labels': ['sys_id', 'sys_name', 'volume_ref', 'label', 'volume_name', 'volume_group_ref']
        },
        'total_size_bytes': {
            'name': 'eseries_volume_total_size_bytes',
            'desc': 'Volume total size in bytes',
            'labels': ['sys_id', 'sys_name', 'volume_ref', 'label', 'volume_name', 'volume_group_ref']
        }
    },
    'config_storage_pools': {
        'info': {
            'name': 'eseries_storage_pool_info',
            'desc': 'Storage pool configuration info',
            'labels': ['sys_id', 'sys_name', 'volume_group_ref', 'id', 'label', 'pool_name', 'raid_level', 'state', 'drive_media_type']
        },
        'free_space_bytes': {
            'name': 'eseries_storage_pool_free_space_bytes',
            'desc': 'Storage pool free space in bytes',
            'labels': ['sys_id', 'sys_name', 'volume_group_ref', 'id', 'label', 'pool_name']
        },
        'used_space_bytes': {
            'name': 'eseries_storage_pool_used_space_bytes',
            'desc': 'Storage pool used space in bytes',
            'labels': ['sys_id', 'sys_name', 'volume_group_ref', 'id', 'label', 'pool_name']
        },
        'total_raided_space_bytes': {
            'name': 'eseries_storage_pool_total_raided_space_bytes',
            'desc': 'Storage pool total raided space in bytes',
            'labels': ['sys_id', 'sys_name', 'volume_group_ref', 'id', 'label', 'pool_name']
        }
    },

    'config_host_groups': {
        'info': {
            'name': 'eseries_host_group_info',
            'desc': 'Host group configuration info',
            'labels': ['sys_id', 'sys_name', 'id', 'cluster_ref', 'label', 'name']
        }
    },
    'config_hosts': {
        'info': {
            'name': 'eseries_host_info',
            'desc': 'Host configuration info',
            'labels': ['sys_id', 'sys_name', 'id', 'host_ref', 'host_name', 'label', 'host_type_index', 'cluster_ref']
        }
    },
    'config_drives': {
        'info': {
            'name': 'eseries_drive_info',
            'desc': 'Drive configuration info',
            'labels': ['sys_id', 'sys_name', 'drive_ref', 'serial_number', 'product_id', 'drive_media_type', 'tray_id', 'slot_number', 'is_hot_spare', 'status', 'volume_group_ref', 'available', 'offline', 'removed']
        },
        'raw_capacity_bytes': {
            'name': 'eseries_drive_raw_capacity_bytes',
            'desc': 'Drive raw capacity in bytes',
            'labels': ['sys_id', 'sys_name', 'drive_ref', 'serial_number', 'tray_id', 'slot_number', 'volume_group_ref']
        },
        'usable_capacity_bytes': {
            'name': 'eseries_drive_usable_capacity_bytes',
            'desc': 'Drive usable capacity in bytes',
            'labels': ['sys_id', 'sys_name', 'drive_ref', 'serial_number', 'tray_id', 'slot_number', 'volume_group_ref']
        }
    },
    'config_controllers': {
        'info': {
            'name': 'eseries_controller_info',
            'desc': 'Controller configuration info',
            'labels': ['sys_id', 'sys_name', 'controller_id', 'controller_ref', 'physical_location_label']
        }
    },
    'config_interfaces': {
        'info': {
            'name': 'eseries_interface_info',
            'desc': 'Interface configuration info',
            'labels': ['sys_id', 'sys_name', 'interface_id', 'controller_id', 'interface_ref', 'protocol']
        }
    },
    'config_system': {
        'info': {
            'name': 'eseries_system_info',
            'desc': 'System configuration info',
            'labels': ['storage_system', 'storage_system_name'] + [x[1] for x in STORAGE_SYSTEM_INFO_KEYS]
        }
    },
    'interface_alerts': {
        'interface_alert': {
            'name': 'eseries_interface_alert',
            'desc': 'Interface alert status (1=down, 0=ok)',
            'labels': ['sys_id', 'sys_name', 'interface_ref', 'channel', 'interface_type']
        }
    }
}

SNAPSHOT_METRIC_DEFS = {
    'config_consistency_groups': ('eseries_consistency_group', 'Consistency group info', CONSISTENCY_GROUPS_MAPPING, '/consistency-groups'),
    'config_repositories': ('eseries_repository', 'Repository info', REPOSITORIES_CONCAT_MAPPING, '/repositories/concat'),
    'config_snapshot_groups': ('eseries_snapshot_group', 'Snapshot group info', SNAPSHOT_GROUPS_MAPPING, '/snapshot-groups'),
    'config_snapshot_images': ('eseries_snapshot_image', 'Snapshot image info', SNAPSHOT_IMAGES_MAPPING, '/snapshot-images'),
    'config_snapshot_volumes': ('eseries_snapshot_volume', 'Snapshot volume info', SNAPSHOT_VOLUMES_MAPPING, '/snapshot-volumes'),
    'config_snapshot_group_util': ('eseries_snapshot_group_utilization', 'Snapshot group utilization', SNAPSHOT_GROUP_REPOSITORY_UTILIZATION_MAPPING, '/snapshot-groups/repository-utilization'),
    'config_snapshot_volume_util': ('eseries_snapshot_volume_utilization', 'Snapshot volume utilization', SNAPSHOT_VOLUMES_REPOSITORY_UTILIZATION_MAPPING, '/snapshot-volumes/repository-utilization'),
    'config_consistency_group_members': ('eseries_consistency_group_member', 'CG member info', CONSISTENCY_GROUPS_MEMBER_VOLUMES_MAPPING, '/consistency-groups/member-volumes'),
    'config_snapshot_schedules': ('eseries_snapshot_schedule', 'Snapshot schedule info', SNAPSHOT_SCHEDULES_MAPPING, '/snapshot-schedules'),
}


# Auto-add config_system numeric gauges
for _key, _nice_name, _conv in STORAGE_SYSTEM_GAUGE_KEYS:
    PROMETHEUS_METRICS_CONFIG['config_system'][_nice_name] = {
        'name': f"eseries_system_{_nice_name}",
        'desc': f"System metric {_nice_name}",
        'labels': ['storage_system', 'storage_system_name']
    }

DRIVE_STATS_MAPPING = [
    ("diskId", "disk_id", None),
    ("volGroupId", "vol_group_id", None), # storage pool id
    ("volGroupName", "storage_pool_name", None), # storage pool name
    ("volGroupWWN", "storage_group_wwn", None), # storage pool wwn
    ("trayId", "tray_id", None),
    ("slot", "slot_number", None),
    ("diskManufacture", "disk_manufacturer", None),
    ("diskSoftwareVersion", "disk_software_version", None),
    ("idleTime", "idle_time_ms", None),
    ("otherOps", "other_ops", None),
    ("otherTimeMax", "other_time_max_ms", None),
    ("otherTimeTotal", "other_time_total_ms", None),
    ("otherTimeTotalSq", "other_time_total_sq_ms", None),
    ("readBytes", "read_bytes", None),
    ("readOps", "read_ops", None),
    ("readTimeMax", "read_time_max_ms", None),
    ("readTimeTotal", "read_time_total_ms", None),
    ("readTimeTotalSq", "read_time_total_sq_ms", None),
    ("recoveredErrors", "recovered_errors", None),
    ("retriedIos", "retried_ios", None),
    ("timeouts", "timeouts", None),
    ("unrecoveredErrors", "unrecovered_errors", None),
    ("writeBytes", "write_bytes", None),
    ("writeOps", "write_ops", None),
    ("writeTimeMax", "write_time_max_ms", None),
    ("writeTimeTotal", "write_time_total_ms", None),
    ("writeTimeTotalSq", "write_time_total_sq_ms", None),
    ("queueDepthTotal", "queue_depth_total", None),
    ("queueDepthMax", "queue_depth_max", None),
    ("randomIosTotal", "random_ios_total", None),
    ("randomBytesTotal", "random_bytes_total", None),
]

CONFIG_DRIVES_MAPPING = [
    ("driveRef", "drive_ref", None),
    ("serialNumber", "serial_number", None),
    ("productID", "product_id", None),
    ("driveMediaType", "drive_media_type", None),
    ("physicalLocation_trayRef", "tray_id", None),
    ("physicalLocation_slot", "slot_number", None),
    ("hotSpare", "is_hot_spare", None),
    ("status", "status", None),
    ("currentVolumeGroupRef", "volume_group_ref", None),
    ("available", "available", None),
    ("offline", "offline", None),
    ("removed", "removed", None),
    ("rawCapacity", "raw_capacity_bytes", _to_integer),
    ("usableCapacity", "usable_capacity_bytes", _to_integer)
]


CONFIG_STORAGE_POOLS_MAPPING = [
  ('name', 'pool_name', str),
  ('id', 'id', str),
  ('label', 'label', str),
  ('raidLevel', 'raid_level', str),
  ('worldWideName', 'wwn', str),
  ('volumeGroupRef', 'volume_group_ref', str),
  ('trayLossProtection', 'has_tray_loss_protection', bool),
  ('state', 'state', str),
  ('spindleSpeedMatch', 'is_spindle_speed_match', bool),
  ('spindleSpeed', 'spindle_speed', int),
  ('isInaccessible', 'is_inaccessible', bool),
  ('securityType', 'security_type', str),
  ('drawerLossProtection', 'has_drawer_loss_protection', bool),
  ('protectionInformationCapable', 'is_protection_information_capable', bool),
  ('drivePhysicalType', 'drive_physical_type', str),
  ('driveMediaType', 'drive_media_type', str),
  ('driveBlockFormat', 'drive_block_format', str),
  ('reservedSpaceAllocated', 'reserved_space_allocated_bytes', bool),
  ('securityLevel', 'security_level', str),
  ('dulbeEnabled', 'is_dulbe_enabled', bool),
  ('blkSizeSupported', 'sector_size_bytes_supported', lambda x: ';'.join(str(i) for i in x) if x else None),
  ('blkSizeRecommended', 'sector_size_recommended_bytes', int),
  ('usedSpace', 'used_space_bytes', float),
  ('totalRaidedSpace','total_raided_space_bytes' , float),
  ('freeSpace', 'free_space_bytes', float),
]


CONFIG_STORAGE_POOLS_MAPPING = [
  ('name', 'pool_name', str),
  ('id', 'id', str),
  ('label', 'label', str),
  ('raidLevel', 'raid_level', str),
  ('worldWideName', 'wwn', str),
  ('volumeGroupRef', 'volume_group_ref', str),
  ('trayLossProtection', 'has_tray_loss_protection', bool),
  ('state', 'state', str),
  ('spindleSpeedMatch', 'is_spindle_speed_match', bool),
  ('spindleSpeed', 'spindle_speed', int),
  ('isInaccessible', 'is_inaccessible', bool),
  ('securityType', 'security_type', str),
  ('drawerLossProtection', 'has_drawer_loss_protection', bool),
  ('protectionInformationCapable', 'is_protection_information_capable', bool),
  ('drivePhysicalType', 'drive_physical_type', str),
  ('driveMediaType', 'drive_media_type', str),
  ('driveBlockFormat', 'drive_block_format', str),
  ('reservedSpaceAllocated', 'reserved_space_allocated_bytes', bool),
  ('securityLevel', 'security_level', str),
  ('dulbeEnabled', 'is_dulbe_enabled', bool),
  ('blkSizeSupported', 'sector_size_bytes_supported', lambda x: ';'.join(str(i) for i in x) if x else None),
  ('blkSizeRecommended', 'sector_size_recommended_bytes', int),
  ('usedSpace', 'used_space_bytes', float),
  ('totalRaidedSpace','total_raided_space_bytes' , float),
  ('freeSpace', 'free_space_bytes', float),
]

DRIVE_MAPPING = [
    ("averageReadOpSize", "averageReadOpSize", float),
    ("averageWriteOpSize", "averageWriteOpSize", float),
    ("combinedIOps", "combinedIOps", float),
    ("combinedResponseTime", "combinedResponseTime", float),
    ("combinedThroughput", "combinedThroughput", float),
    ("otherIOps", "otherIOps", float),
    ("readIOps", "readIOps", float),
    ("readOps", "readOps", float),
    ("readPhysicalIOps", "readPhysicalIOps", float),
    ("readResponseTime", "readResponseTime", float),
    ("readThroughput", "readThroughput", float),
    ("writeIOps", "writeIOps", float),
    ("writeOps", "writeOps", float),
    ("writePhysicalIOps", "writePhysicalIOps", float),
    ("writeResponseTime", "writeResponseTime", float),
    ("writeThroughput", "writeThroughput", float),
    ("spareBlocksRemainingPercent", "spareBlocksRemainingPercent", float),
    ("percentEnduranceUsed", "percentEnduranceUsed", float),
]

VOLUME_LIVE_MAPPING = [
    ("readIOps", "readIOps", float),
    ("writeIOps", "writeIOps", float),
    ("otherIOps", "otherIOps", float),
    ("combinedIOps", "combinedIOps", float),
    ("readThroughput", "readThroughput", float),
    ("writeThroughput", "writeThroughput", float),
    ("combinedThroughput", "combinedThroughput", float),
    ("readResponseTime", "readResponseTime", float),
    ("writeResponseTime", "writeResponseTime", float),
    ("combinedResponseTime", "combinedResponseTime", float),
    ("averageReadOpSize", "averageReadOpSize", float),
    ("averageWriteOpSize", "averageWriteOpSize", float),
    ("readOps", "readOps", float),
    ("writeOps", "writeOps", float),
    ("otherOps", "otherOps", float),
    ("mapped_host_names", "mapped_host_names", str),
    ("mapped_host_count", "mapped_host_count", float),
]

SENSOR_MAPPING = [
    ("temp", "temp", int),
]

PSU_MAPPING = [
    ("totalPower", "totalPower", int),
]

CONFIG_WORKLOADS_MAPPING = [
    ("name", "workload_name_field", str),
    ("workloadAttributes_profileId", "workloadAttributes_profileId", str),
    ("workloadAttributes_isUserDefined", "workloadAttributes_isUserDefined", bool)
]
