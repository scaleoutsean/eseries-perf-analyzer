"""
Drive Configuration Enrichment for E-Series Performance Analyzer

This module enriches drive configuration data with drive-specific tags
and context for optimal InfluxDB storage and Grafana visualization.

Drive configs are the most complex config type (64+ keys) and warrant
dedicated enrichment logic to properly tag drives by:
- Physical attributes (slot, tray, drawer, type, capacity)
- Performance characteristics (interface, rpm, form_factor)  
- Status and health (status, availability, drive_errors)
- Logical organization (volume_group, pool assignment)
"""

import logging
from typing import Dict, Any
from app.enrichment.config_enrichment import BaseConfigEnricher

LOG = logging.getLogger(__name__)

class DriveConfigEnricher(BaseConfigEnricher):
    """
    Dedicated enricher for drive configuration data.
    
    Handles complex drive configs with 60+ fields by intelligently promoting
    key fields to InfluxDB tags for efficient querying and visualization.
    """
    
    def __init__(self, system_enricher=None):
        """Initialize drive config enricher."""
        super().__init__(system_enricher)
        
        # Drive interface types for normalization
        self.interface_types = {
            'sas', 'sata', 'nvme', 'fibre', 'fc', 'scsi'
        }
        
        # Drive type mappings for standardization
        self.drive_type_map = {
            'ssd': 'ssd',
            'hdd': 'hdd', 
            'hybrid': 'hybrid',
            'unknown': 'unknown'
        }
    
    def enrich_item(self, raw_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Enrich drive config with drive-specific tags and context.
        
        Key enrichments:
        - Physical location (tray, slot, drawer)
        - Drive characteristics (type, capacity, interface, rpm)
        - Status and health indicators
        - Performance-related fields as tags
        """
        enriched_item = raw_item.copy()
        
        # === CORE IDENTITY TAGS ===
        # Drive ID/Reference (critical for joins)
        drive_ref = enriched_item.get('driveRef') or enriched_item.get('id') or enriched_item.get('ref')
        if drive_ref:
            enriched_item['drive_id'] = drive_ref
            enriched_item['drive_ref'] = drive_ref
        
        # === PHYSICAL LOCATION TAGS ===
        # Physical slot information (key for datacenter visualization)
        phys_location = enriched_item.get('physicalLocation', {})
        if isinstance(phys_location, dict):
            tray_ref = phys_location.get('trayRef')
            slot = phys_location.get('slot')
            drawer = phys_location.get('drawer')
            
            if tray_ref:
                enriched_item['drive_tray'] = tray_ref
            if slot is not None:
                enriched_item['drive_slot'] = str(slot)
            if drawer is not None:
                enriched_item['drive_drawer'] = str(drawer)
                
            # Create composite location tag for easy filtering
            location_parts = []
            if tray_ref:
                location_parts.append(f"tray{tray_ref}")
            if slot is not None:
                location_parts.append(f"slot{slot}")
            if drawer is not None:
                location_parts.append(f"drawer{drawer}")
            if location_parts:
                enriched_item['drive_location'] = "_".join(location_parts)
        
        # === DRIVE TYPE AND CHARACTERISTICS ===
        # Drive type (critical for performance analysis)
        drive_type = enriched_item.get('driveMediaType', '').lower()
        if drive_type in self.drive_type_map:
            enriched_item['drive_type'] = self.drive_type_map[drive_type]
        else:
            # Fallback detection from other fields
            if 'ssd' in str(enriched_item.get('productID', '')).lower():
                enriched_item['drive_type'] = 'ssd'
            elif enriched_item.get('spindleSpeed', 0) > 0:
                enriched_item['drive_type'] = 'hdd'
            else:
                enriched_item['drive_type'] = 'unknown'
        
        # Interface type (affects performance characteristics)
        interface = enriched_item.get('interfaceType', {})
        if isinstance(interface, dict):
            interface_type = interface.get('interfaceType', '').lower()
            if interface_type:
                enriched_item['drive_interface'] = interface_type
        
        # Capacity (normalized to GB for consistent analysis) 
        raw_capacity = enriched_item.get('rawCapacity')
        if raw_capacity:
            try:
                # Assume raw capacity is in bytes, convert to GB
                capacity_gb = int(raw_capacity) // (1024**3)
                enriched_item['drive_capacity_gb'] = capacity_gb
                
                # Create capacity tier for easy grouping
                if capacity_gb >= 10000:  # 10TB+
                    enriched_item['drive_capacity_tier'] = 'very_large'
                elif capacity_gb >= 2000:  # 2TB+
                    enriched_item['drive_capacity_tier'] = 'large'
                elif capacity_gb >= 500:   # 500GB+
                    enriched_item['drive_capacity_tier'] = 'medium' 
                else:
                    enriched_item['drive_capacity_tier'] = 'small'
            except (ValueError, TypeError):
                LOG.warning(f"Could not parse drive capacity: {raw_capacity}")
        
        # === PERFORMANCE CHARACTERISTICS ===
        # Spindle speed (RPM) for HDD performance analysis
        spindle_speed = enriched_item.get('spindleSpeed')
        if spindle_speed and spindle_speed > 0:
            enriched_item['drive_rpm'] = spindle_speed
            
            # RPM performance tier
            if spindle_speed >= 15000:
                enriched_item['drive_performance_tier'] = 'high_perf'
            elif spindle_speed >= 10000:
                enriched_item['drive_performance_tier'] = 'enterprise'
            elif spindle_speed >= 7200:
                enriched_item['drive_performance_tier'] = 'standard'
            else:
                enriched_item['drive_performance_tier'] = 'low_power'
        elif enriched_item.get('drive_type') == 'ssd':
            enriched_item['drive_performance_tier'] = 'ssd'
        
        # Form factor (affects density and performance)
        form_factor = enriched_item.get('formFactor')
        if form_factor:
            enriched_item['drive_form_factor'] = form_factor
        
        # === STATUS AND HEALTH ===
        # Drive status (critical for health monitoring)
        status = enriched_item.get('status', '').lower()
        if status:
            enriched_item['drive_status'] = status
            
            # Categorize status for alerting
            if status in ['optimal', 'ok', 'good']:
                enriched_item['drive_health'] = 'healthy'
            elif status in ['degraded', 'warning']:
                enriched_item['drive_health'] = 'warning'
            elif status in ['failed', 'error', 'critical']:
                enriched_item['drive_health'] = 'critical'
            else:
                enriched_item['drive_health'] = 'unknown'
        
        # Availability status
        available = enriched_item.get('available')
        if available is not None:
            enriched_item['drive_available'] = str(available).lower()
        
        # === LOGICAL ORGANIZATION ===
        # Volume group assignment (for capacity planning)
        volume_group_ref = enriched_item.get('currentVolumeGroupRef')
        if volume_group_ref and volume_group_ref != '0000000000000000000000000000000000000000':
            enriched_item['drive_volume_group'] = volume_group_ref
            enriched_item['drive_assigned'] = 'true'
        else:
            enriched_item['drive_assigned'] = 'false'
        
        # Pool assignment
        pool_id = enriched_item.get('poolId')
        if pool_id:
            enriched_item['drive_pool_id'] = pool_id
        
        # === VENDOR AND MODEL INFO ===
        # Vendor (for vendor-specific monitoring)
        vendor = enriched_item.get('vendorID', '').strip()
        if vendor:
            enriched_item['drive_vendor'] = vendor
        
        # Product ID/Model
        product_id = enriched_item.get('productID', '').strip()
        if product_id:
            enriched_item['drive_model'] = product_id
        
        # Serial number (for warranty tracking) 
        serial = enriched_item.get('serialNumber', '').strip()
        if serial:
            enriched_item['drive_serial'] = serial
        
        # === TEMPERATURE MONITORING ===
        # Current temperature (critical for drive health)
        current_temp = enriched_item.get('currentTemperature')
        if current_temp is not None:
            try:
                temp_c = float(current_temp)
                enriched_item['drive_temperature_c'] = temp_c
                
                # Temperature alert thresholds
                if temp_c >= 70:
                    enriched_item['drive_temp_status'] = 'critical'
                elif temp_c >= 60:
                    enriched_item['drive_temp_status'] = 'warning'
                elif temp_c >= 45:
                    enriched_item['drive_temp_status'] = 'warm'
                else:
                    enriched_item['drive_temp_status'] = 'normal'
            except (ValueError, TypeError):
                LOG.warning(f"Could not parse drive temperature: {current_temp}")
        
        # Max/Min temperature thresholds
        max_temp = enriched_item.get('maximumTemperature')
        if max_temp is not None:
            enriched_item['drive_max_temp_c'] = max_temp
        
        # === SMART DATA ===
        # SMART attribute count (indicates monitoring richness)
        smart_data = enriched_item.get('smartData', {})
        if isinstance(smart_data, dict) and smart_data:
            enriched_item['drive_smart_enabled'] = 'true'
            enriched_item['drive_smart_attributes'] = len(smart_data)
        else:
            enriched_item['drive_smart_enabled'] = 'false'
        
        # === SECURITY FEATURES ===
        # Encryption status
        fde_capable = enriched_item.get('fdeCapable')
        if fde_capable is not None:
            enriched_item['drive_encryption_capable'] = str(fde_capable).lower()
        
        fde_enabled = enriched_item.get('fdeEnabled')
        if fde_enabled is not None:
            enriched_item['drive_encryption_enabled'] = str(fde_enabled).lower()
        
        LOG.debug(f"Enriched drive config: {enriched_item.get('drive_id', 'unknown')} "
                 f"({enriched_item.get('drive_type', 'unknown')} "
                 f"{enriched_item.get('drive_capacity_gb', 0)}GB "
                 f"@ {enriched_item.get('drive_location', 'unknown')})")
        
        return enriched_item