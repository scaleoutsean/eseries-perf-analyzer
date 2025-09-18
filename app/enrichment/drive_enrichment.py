"""
Drive Performance Enrichment

Enriches drive performance metrics with:
- trayId: Already present in performance data, but we can validate/enrich from config
- volGroupName: Enhanced storage pool name lookup from drive config -> storage pool config  
- hasDegradedChannel: Drive health status from drive configuration
"""

from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class DriveEnrichmentProcessor:
    """Processes drive performance enrichment with configuration data"""
    
    def __init__(self):
        self.drive_lookup = {}          # drive_id -> drive_config
        self.pool_lookup = {}           # pool_id -> pool_config
        self.system_lookup = {}         # system_id/system_wwn -> system_config
        
    def load_configuration_data(self, 
                              drives: List[Dict], 
                              storage_pools: List[Dict],
                              system_configs_data: Optional[List[Dict]] = None):
        """Load drive configuration and storage pool data needed for enrichment"""
        
        # Build lookup tables
        self.drive_lookup = {d['id']: d for d in drives}
        # Also index by driveRef in case they differ
        for drive in drives:
            if drive.get('driveRef') and drive['driveRef'] != drive['id']:
                self.drive_lookup[drive['driveRef']] = drive
        
        self.pool_lookup = {p['id']: p for p in storage_pools}
        
        # Load system configurations if provided
        self.system_lookup = {}
        if system_configs_data:
            # Handle both single system config dict and list of system configs
            if isinstance(system_configs_data, dict):
                system_configs_data = [system_configs_data]
            
            for system_config in system_configs_data:
                system_id = system_config.get('id')
                system_wwn = system_config.get('wwn')
                if system_id:
                    self.system_lookup[system_id] = system_config
                if system_wwn:
                    self.system_lookup[system_wwn] = system_config
            
        logger.info(f"Loaded drive enrichment data: {len(drives)} drives, {len(storage_pools)} storage pools, {len(self.system_lookup)} systems")
    
    def enrich_drive_performance(self, drive_performance: Dict) -> Dict:
        """Enrich a single drive performance measurement with configuration data"""
        
        disk_id = drive_performance.get('diskId')
        if not disk_id:
            logger.warning("Drive performance record missing diskId")
            return drive_performance
            
        # Get drive configuration
        drive_config = self.drive_lookup.get(disk_id)
        if not drive_config:
            logger.warning(f"Drive {disk_id} not found in configuration")
            return drive_performance
            
        # Start with original performance data
        enriched = drive_performance.copy()
        
        # Add tags
        enriched['tray_id'] = drive_performance.get('trayId', 'unknown')
        
        # Get enhanced storage pool name from drive config -> storage pools lookup
        vol_group_ref = drive_config.get('currentVolumeGroupRef')
        pool = self.pool_lookup.get(vol_group_ref)
        if pool:
            enriched['vol_group_name'] = pool.get('name', 'unknown')
        else:
            # Fallback to the volGroupName already in performance data
            enriched['vol_group_name'] = drive_performance.get('volGroupName', 'unknown')
        
        # Add fields (additional data points)
        enriched['has_degraded_channel'] = drive_config.get('hasDegradedChannel', False)
        
        # Add system tags if system config is available
        # Try to find system from drive config or storage pool
        system_config = None
        system_id = drive_config.get('storage_system_id') or drive_config.get('system_id')
        if system_id and system_id in self.system_lookup:
            system_config = self.system_lookup[system_id]
        elif vol_group_ref and vol_group_ref in self.pool_lookup:
            # Try to get system from storage pool
            pool = self.pool_lookup[vol_group_ref]
            system_id = pool.get('storage_system_id') or pool.get('system_id')
            if system_id and system_id in self.system_lookup:
                system_config = self.system_lookup[system_id]
        
        if system_config:
            enriched['system_name'] = system_config.get('name', 'unknown')
            enriched['system_wwn'] = system_config.get('wwn', 'unknown')
            enriched['system_id'] = system_config.get('id', 'unknown')
            enriched['system_model'] = system_config.get('model', 'unknown')
            enriched['system_firmware_version'] = system_config.get('firmwareVersion', 'unknown')
        else:
            # Fallback to unknown values if no system config
            enriched['system_name'] = 'unknown'
            enriched['system_wwn'] = 'unknown'
            enriched['system_id'] = 'unknown'
            enriched['system_model'] = 'unknown'
            enriched['system_firmware_version'] = 'unknown'
        
        # Optional: Add drive physical location info as tags
        physical_location = drive_config.get('physicalLocation', {})
        enriched['drive_slot'] = physical_location.get('slot', drive_performance.get('driveSlot', 'unknown'))
        enriched['tray_ref'] = physical_location.get('trayRef', drive_performance.get('trayRef', 'unknown'))
        
        return enriched
    
    def enrich_drive_performance_batch(self, drive_performances: List[Dict]) -> List[Dict]:
        """Enrich a batch of drive performance measurements"""
        
        enriched_results = []
        for perf_record in drive_performances:
            enriched = self.enrich_drive_performance(perf_record)
            enriched_results.append(enriched)
            
        logger.info(f"Enriched {len(enriched_results)} drive performance records")
        return enriched_results