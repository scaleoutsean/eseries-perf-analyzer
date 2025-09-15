"""
Controller Configuration Enrichment for E-Series Performance Analyzer

This module enriches controller configuration data with controller-specific
tags and context for optimal InfluxDB storage and performance monitoring.

Controller configs have high complexity (41+ keys) and warrant dedicated
enrichment to properly tag controllers by:
- Physical identification (slot, location, ID)
- Network interfaces and connectivity  
- Status and health indicators
- Performance and caching configuration
- Firmware and hardware versions
"""

import logging
from typing import Dict, Any, List
from app.enrichment.config_enrichment import BaseConfigEnricher

LOG = logging.getLogger(__name__)

class ControllerConfigEnricher(BaseConfigEnricher):
    """
    Dedicated enricher for controller configuration data.
    
    Handles complex controller configs by intelligently promoting
    critical fields to InfluxDB tags for efficient monitoring and alerting.
    """
    
    def __init__(self, system_enricher=None):
        """Initialize controller config enricher.""" 
        super().__init__(system_enricher)
        
        # Controller status mappings for normalization
        self.status_map = {
            'optimal': 'healthy',
            'ok': 'healthy',
            'good': 'healthy',
            'online': 'healthy',
            'degraded': 'warning',
            'warning': 'warning', 
            'failed': 'critical',
            'offline': 'critical',
            'error': 'critical',
            'unknown': 'unknown'
        }
    
    def enrich_item(self, raw_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Enrich controller config with controller-specific tags and context.
        
        Key enrichments:
        - Physical identification and location
        - Network interface details
        - Status and health monitoring
        - Cache and performance settings
        - Version information
        """
        enriched_item = raw_item.copy()
        
        # === CORE IDENTITY TAGS ===
        # Controller ID/Reference (critical for performance joins)
        controller_ref = (enriched_item.get('controllerRef') or 
                         enriched_item.get('id') or 
                         enriched_item.get('ref'))
        if controller_ref:
            enriched_item['controller_id'] = controller_ref
            enriched_item['controller_ref'] = controller_ref
        
        # === PHYSICAL IDENTIFICATION ===
        # Physical slot/location (for datacenter mapping)
        phys_location = enriched_item.get('physicalLocation', {})
        if isinstance(phys_location, dict):
            slot = phys_location.get('slot')
            location_parent = phys_location.get('locationParent', {})
            
            if slot is not None:
                enriched_item['controller_slot'] = str(slot)
                
            if isinstance(location_parent, dict):
                parent_type = location_parent.get('type')
                parent_ref = location_parent.get('ref')
                if parent_type and parent_ref:
                    enriched_item['controller_enclosure'] = f"{parent_type}_{parent_ref}"
        
        # Controller position (A/B controller identification)
        board_id = enriched_item.get('boardID')
        if board_id:
            enriched_item['controller_position'] = board_id
        
        # === STATUS AND HEALTH ===
        # Overall controller status 
        status = enriched_item.get('status', '').lower()
        if status:
            enriched_item['controller_status'] = status
            
            # Map to standardized health categories
            health = self.status_map.get(status, 'unknown')
            enriched_item['controller_health'] = health
        
        # Quiesced state (maintenance mode indicator)
        quiesced = enriched_item.get('quiesced')
        if quiesced is not None:
            enriched_item['controller_quiesced'] = str(quiesced).lower()
        
        # === NETWORK INTERFACES ===
        # Ethernet interface configuration (critical for network monitoring)
        ethernet_interfaces = enriched_item.get('ethernetInterfaces', [])
        if isinstance(ethernet_interfaces, list) and ethernet_interfaces:
            # Count total interfaces
            enriched_item['controller_ethernet_ports'] = len(ethernet_interfaces)
            
            # Collect interface details
            interface_speeds = []
            interface_states = []
            
            for i, interface in enumerate(ethernet_interfaces):
                if isinstance(interface, dict):
                    # Interface speed
                    speed = interface.get('linkSpeed')
                    if speed:
                        interface_speeds.append(str(speed))
                    
                    # Interface state
                    state = interface.get('linkState', '').lower()
                    if state:
                        interface_states.append(state)
                    
                    # Tag individual interface details (for first few interfaces)
                    if i < 4:  # Limit to first 4 interfaces to avoid tag explosion
                        enriched_item[f'controller_eth{i}_speed'] = speed or 'unknown'
                        enriched_item[f'controller_eth{i}_state'] = state or 'unknown'
            
            # Aggregate interface information
            if interface_speeds:
                enriched_item['controller_max_speed'] = max(interface_speeds, key=lambda x: self._parse_speed(x))
            
            if interface_states:
                # Check if all interfaces are up
                if all(state == 'up' for state in interface_states):
                    enriched_item['controller_network_health'] = 'all_up'
                elif any(state == 'up' for state in interface_states):
                    enriched_item['controller_network_health'] = 'partial'
                else:
                    enriched_item['controller_network_health'] = 'down'
        
        # Host-side interfaces (SAS/FC)
        host_interfaces = enriched_item.get('hostInterfaces', [])
        if isinstance(host_interfaces, list):
            enriched_item['controller_host_ports'] = len(host_interfaces)
            
            # Analyze host interface types
            interface_types = set()
            for interface in host_interfaces:
                if isinstance(interface, dict):
                    iface_type = interface.get('interfaceType', '').lower()
                    if iface_type:
                        interface_types.add(iface_type)
            
            if interface_types:
                enriched_item['controller_host_interface_types'] = ','.join(sorted(interface_types))
        
        # === CACHE CONFIGURATION ===
        # Cache memory size (affects performance)
        cache_memory = enriched_item.get('cacheMemorySize')
        if cache_memory:
            try:
                cache_mb = int(cache_memory) // (1024 * 1024)  # Convert to MB
                enriched_item['controller_cache_mb'] = cache_mb
                
                # Cache size tier
                if cache_mb >= 16000:  # 16GB+
                    enriched_item['controller_cache_tier'] = 'very_large'
                elif cache_mb >= 8000:   # 8GB+
                    enriched_item['controller_cache_tier'] = 'large'
                elif cache_mb >= 4000:   # 4GB+
                    enriched_item['controller_cache_tier'] = 'medium'
                else:
                    enriched_item['controller_cache_tier'] = 'small'
            except (ValueError, TypeError):
                LOG.warning(f"Could not parse cache memory size: {cache_memory}")
        
        # Cache settings
        cache_settings = enriched_item.get('cacheSettings', {})
        if isinstance(cache_settings, dict):
            # Read-ahead multiplier (performance tuning)
            read_ahead = cache_settings.get('readAheadMultiplier')
            if read_ahead is not None:
                enriched_item['controller_read_ahead_multiplier'] = read_ahead
            
            # Cache block size
            cache_block_size = cache_settings.get('cacheBlockSize')
            if cache_block_size:
                enriched_item['controller_cache_block_size'] = cache_block_size
        
        # === HARDWARE VERSIONS ===
        # Hardware revision (for compatibility tracking)
        hw_version = enriched_item.get('hardwareRevision')
        if hw_version:
            enriched_item['controller_hardware_revision'] = hw_version
        
        # Board revision
        board_revision = enriched_item.get('boardRevision')
        if board_revision:
            enriched_item['controller_board_revision'] = board_revision
        
        # === FIRMWARE VERSIONS ===
        # App firmware version (critical for support)
        app_version = enriched_item.get('appVersion')
        if app_version:
            enriched_item['controller_firmware_version'] = app_version
        
        # Boot firmware version
        boot_version = enriched_item.get('bootVersion') 
        if boot_version:
            enriched_item['controller_boot_version'] = boot_version
        
        # NVSRAM version (configuration data)
        nvsram_version = enriched_item.get('nvsramVersion')
        if nvsram_version:
            enriched_item['controller_nvsram_version'] = nvsram_version
        
        # === MANUFACTURING INFO ===
        # Manufacturing location and date (for warranty/support)
        mfg_location = enriched_item.get('manufacturerLocation')
        if mfg_location:
            enriched_item['controller_mfg_location'] = mfg_location
        
        mfg_date = enriched_item.get('manufactureDate')
        if mfg_date:
            enriched_item['controller_mfg_date'] = mfg_date
        
        # Serial numbers
        board_serial = enriched_item.get('boardSerialNumber')
        if board_serial:
            enriched_item['controller_serial'] = board_serial
        
        # === THERMAL MANAGEMENT ===
        # Temperature sensors and thermal data
        thermal_sensors = enriched_item.get('thermalSensors', [])
        if isinstance(thermal_sensors, list) and thermal_sensors:
            enriched_item['controller_temp_sensors'] = len(thermal_sensors)
            
            # Find current temperatures
            temperatures = []
            for sensor in thermal_sensors:
                if isinstance(sensor, dict):
                    current_temp = sensor.get('currentTemperature')
                    if current_temp is not None:
                        try:
                            temperatures.append(float(current_temp))
                        except (ValueError, TypeError):
                            pass
            
            if temperatures:
                max_temp = max(temperatures)
                avg_temp = sum(temperatures) / len(temperatures)
                
                enriched_item['controller_max_temperature'] = max_temp
                enriched_item['controller_avg_temperature'] = avg_temp
                
                # Temperature health assessment
                if max_temp >= 80:
                    enriched_item['controller_thermal_health'] = 'critical'
                elif max_temp >= 70:
                    enriched_item['controller_thermal_health'] = 'warning'
                elif max_temp >= 55:
                    enriched_item['controller_thermal_health'] = 'warm'
                else:
                    enriched_item['controller_thermal_health'] = 'normal'
        
        # === REDUNDANCY AND FAILOVER ===
        # Preferred owner status (for load balancing analysis)
        preferred_owner = enriched_item.get('preferredOwner')
        if preferred_owner is not None:
            enriched_item['controller_preferred_owner'] = str(preferred_owner).lower()
        
        LOG.debug(f"Enriched controller config: {enriched_item.get('controller_id', 'unknown')} "
                 f"(slot {enriched_item.get('controller_slot', 'unknown')}, "
                 f"{enriched_item.get('controller_health', 'unknown')} health, "
                 f"{enriched_item.get('controller_ethernet_ports', 0)} eth ports)")
        
        return enriched_item
    
    def _parse_speed(self, speed_str: str) -> int:
        """
        Parse speed string to numeric value for comparison.
        
        Handles common formats like '1000', '10G', '25Gbps', etc.
        """
        if not speed_str:
            return 0
        
        speed_str = str(speed_str).lower().replace('gbps', '').replace('g', '').replace('mbps', '')
        
        try:
            # Handle common multipliers
            if 'k' in speed_str:
                return int(float(speed_str.replace('k', '')) * 1000)
            elif 'm' in speed_str:
                return int(float(speed_str.replace('m', '')) * 1000000)
            else:
                return int(float(speed_str))
        except (ValueError, TypeError):
            return 0