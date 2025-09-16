import logging
from typing import Dict, List, Optional, Any

from app.collectors.collector import ESeriesCollector
from app.config.collection_schedules import ConfigCollectionScheduler, ScheduleFrequency
from app.schema.models import (
    DriveConfig, VolumeConfig, ControllerConfig, SystemConfig,
    HostConfig, HostGroupsConfig, StoragePoolConfig, VolumeMappingsConfig,
    InterfaceConfig, TrayConfig, VolumeCGMembersConfig
)

class ConfigCollector:
    """Collects configuration data from API with smart scheduling"""
    
    def __init__(self, session=None, headers=None, api_endpoints=None, config_cache=None, scheduler=None, from_json=False, json_directory=None, base_url=None, system_id='1'):
        self.session = session
        self.headers = headers
        self.api_endpoints = api_endpoints
        self.config_cache = config_cache
        self.scheduler = scheduler
        self.logger = logging.getLogger(__name__)
        
        # Initialize ESeriesCollector for actual data collection
        collector_config = {
            'from_json': from_json,
            'json_directory': json_directory or './json_data',
            'base_url': base_url,
            'system_id': system_id,
            'session': session,
            'headers': headers or {'Accept': 'application/json'}
        }
        self.eseries_collector = ESeriesCollector(collector_config)
        
    def collect_config(self, sys_info):
        """Collect configuration data based on scheduler."""
        if not self.scheduler:
            return {"status": "ok", "note": "no_scheduler"}
        
        # Get config types to collect on this iteration
        collections_needed = self.scheduler.get_config_types_for_collection()
        
        if collections_needed:
            self.logger.info(f"Scheduler indicates collection needed for {len(collections_needed)} frequencies")
            for frequency, config_types in collections_needed.items():
                self.logger.info(f"  {frequency.value}: {config_types}")
            
            # Actually collect the data for each scheduled type
            collected_data = {}
            for frequency, config_types in collections_needed.items():
                for config_type in config_types:
                    try:
                        data = self._collect_config_type(config_type, sys_info)
                        if data:
                            collected_data[config_type] = data
                            self.logger.info(f"Collected {len(data) if isinstance(data, list) else 1} items for {config_type}")
                    except Exception as e:
                        self.logger.error(f"Failed to collect {config_type}: {e}")
            
            return {
                "status": "scheduled_collection",
                "iteration": self.scheduler.iteration_count,
                "collections": {freq.value: types for freq, types in collections_needed.items()},
                "collected_data": collected_data
            }
        else:
            self.logger.info(f"No config collection needed on iteration {self.scheduler.iteration_count}")
            return {"status": "no_collection_needed", "iteration": self.scheduler.iteration_count}
    
    def _collect_config_type(self, config_type: str, sys_info: Dict[str, Any]) -> Optional[List[Any]]:
        """Collect a specific configuration type."""
        try:
            if config_type == "VolumeConfig":
                return self.eseries_collector.collect_volumes(VolumeConfig)
            elif config_type == "VolumeMappingsConfig":
                return self.eseries_collector.collect_volume_mappings(VolumeMappingsConfig)
            elif config_type == "HostConfig":
                return self.eseries_collector.collect_hosts(HostConfig)
            elif config_type == "StoragePoolConfig":
                return self.eseries_collector.collect_storage_pools(StoragePoolConfig)
            elif config_type == "HostGroupsConfig":
                return self.eseries_collector.collect_host_groups(HostGroupsConfig)
            elif config_type == "ControllerConfig":
                return self.eseries_collector.collect_controllers(ControllerConfig)
            elif config_type == "SystemConfig":
                system_config = self.eseries_collector.collect_system_config(SystemConfig)
                return [system_config] if system_config else []
            elif config_type == "DriveConfig":
                return self.eseries_collector.collect_drives(DriveConfig)
            elif config_type == "InterfaceConfig":
                return self.eseries_collector.collect_hierarchical_data('interfaces_config', InterfaceConfig)
            elif config_type == "TrayConfig":
                return self.eseries_collector.collect_hierarchical_data('tray_config', TrayConfig)
            elif config_type == "VolumeCGMembersConfig":
                # Volume consistency group members - use the correct endpoint from your manual collector
                return self.eseries_collector.collect_hierarchical_data('volume_consistency_group_members', VolumeCGMembersConfig)
            elif config_type in ["SnapshotConfig", "EthernetConfig", "HardwareConfig", "AsyncMirrorsConfig"]:
                # These config types don't have corresponding schema models yet
                self.logger.debug(f"Config type {config_type} not implemented - no schema model available")
                return None
            else:
                self.logger.warning(f"Unknown config type: {config_type}")
                return None
        except Exception as e:
            self.logger.error(f"Error collecting {config_type}: {e}")
            return None