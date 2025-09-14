#!/usr/bin/env python3
"""
System statistics enrichment processor for E-Series Performance Analyzer

This module provides enrichment for system-level performance statistics by adding
system configuration metadata as tags and fields for enhanced analytics and monitoring.
"""

import logging
from typing import Dict, List, Any, Optional

LOG = logging.getLogger(__name__)

class SystemEnrichmentProcessor:
    """
    Enrichment processor for system performance statistics.
    
    Adds system configuration metadata to system performance metrics for better
    analytics and cross-system monitoring capabilities.
    """
    
    def __init__(self):
        """Initialize the system enrichment processor."""
        self.system_config_cache: Dict[str, Dict[str, Any]] = {}
        
    def build_system_config_cache(self, system_configs: List[Dict[str, Any]]) -> None:
        """
        Build cache of system configuration data for enrichment.
        
        Args:
            system_configs: List of system configuration objects
        """
        self.system_config_cache.clear()
        
        for config in system_configs:
            if isinstance(config, dict):
                system_wwn = config.get('wwn')
                system_id = config.get('id')  
                
                if system_wwn:
                    self.system_config_cache[system_wwn] = config
                    LOG.debug(f"Cached system config for WWN {system_wwn}: {config.get('name', 'Unknown')}")
                
                if system_id:
                    # Also cache by ID as fallback
                    self.system_config_cache[system_id] = config
                    
        LOG.info(f"Built system config cache with {len(self.system_config_cache)} entries")
        
    def enrich_system_statistics(self, stats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich system performance statistics with configuration metadata.
        
        Args:
            stats: List of system performance statistics
            
        Returns:
            List of enriched system statistics with tags and fields
        """
        enriched_stats = []
        
        for stat in stats:
            if not isinstance(stat, dict):
                LOG.warning(f"Skipping non-dict system statistic: {type(stat)}")
                enriched_stats.append(stat)
                continue
                
            # Extract system identifiers 
            system_wwn = stat.get('storageSystemWWN')
            system_id = stat.get('storageSystemId')
            system_name = stat.get('storageSystemName')
            
            # Look up system config
            system_config = None
            if system_wwn:
                system_config = self.system_config_cache.get(system_wwn)
            if not system_config and system_id:
                system_config = self.system_config_cache.get(system_id)
                
            # Create enriched copy
            enriched_stat = stat.copy()
            
            if system_config:
                # Add system configuration tags for analytics
                enriched_stat.update({
                    # Core system identification tags
                    'system_id': system_config.get('id'),
                    'system_name': system_config.get('name', system_name),
                    'system_wwn': system_config.get('wwn', system_wwn),
                    'system_model': system_config.get('model'),
                    'system_status': system_config.get('status'),
                    'system_sub_model': system_config.get('subModel'),
                    
                    # System configuration tags
                    'firmware_version': system_config.get('fwVersion'),
                    'app_version': system_config.get('appVersion'),
                    'boot_version': system_config.get('bootVersion'),
                    'nvsram_version': system_config.get('nvsramVersion'),
                    'chassis_serial_number': system_config.get('chassisSerialNumber'),
                    
                    # System capacity and hardware fields 
                    'drive_count': system_config.get('driveCount'),
                    'tray_count': system_config.get('trayCount'),
                    'hot_spare_count': system_config.get('hotSpareCount'),
                    'used_pool_space': system_config.get('usedPoolSpace'),
                    'free_pool_space': system_config.get('freePoolSpace'),
                    'unconfigured_space': system_config.get('unconfiguredSpace'),
                    
                    # System feature flags
                    'auto_load_balancing_enabled': system_config.get('autoLoadBalancingEnabled'),
                    'host_connectivity_reporting_enabled': system_config.get('hostConnectivityReportingEnabled'),
                    'remote_mirroring_enabled': system_config.get('remoteMirroringEnabled'),
                    'security_key_enabled': system_config.get('securityKeyEnabled'),
                    'simplex_mode_enabled': system_config.get('simplexModeEnabled'),
                    
                    # Drive type information
                    'drive_types': ','.join(system_config.get('driveTypes', [])) if system_config.get('driveTypes') else None,
                })
                
                LOG.debug(f"Enriched system statistics for {system_name} with config metadata")
            else:
                LOG.warning(f"No system config found for system {system_name} (WWN: {system_wwn}, ID: {system_id})")
                # Still add basic tags from the statistics themselves
                enriched_stat.update({
                    'system_id': system_id,
                    'system_name': system_name,
                    'system_wwn': system_wwn,
                })
                
            enriched_stats.append(enriched_stat)
            
        LOG.info(f"Enriched {len(enriched_stats)} system statistics entries")
        return enriched_stats
        
    def get_enrichment_fields(self) -> List[str]:
        """
        Get list of fields added by this enrichment processor.
        
        Returns:
            List of field names added during enrichment
        """
        return [
            'system_id', 'system_name', 'system_wwn', 'system_model', 'system_status',
            'system_sub_model', 'firmware_version', 'app_version', 'boot_version',
            'nvsram_version', 'chassis_serial_number', 'drive_count', 'tray_count',
            'hot_spare_count', 'used_pool_space', 'free_pool_space', 'unconfigured_space',
            'auto_load_balancing_enabled', 'host_connectivity_reporting_enabled',
            'remote_mirroring_enabled', 'security_key_enabled', 'simplex_mode_enabled',
            'drive_types'
        ]
        
    def get_enrichment_tags(self) -> List[str]:
        """
        Get list of recommended tags from enriched fields for InfluxDB.
        
        Returns:
            List of field names that should be used as InfluxDB tags
        """
        return [
            'system_id', 'system_name', 'system_wwn', 'system_model', 'system_status',
            'firmware_version', 'chassis_serial_number', 'drive_types'
        ]