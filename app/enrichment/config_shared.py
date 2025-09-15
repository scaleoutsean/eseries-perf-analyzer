"""
Shared Configuration Enrichment for E-Series Performance Analyzer

This module provides enrichment for simpler configuration types that don't
warrant dedicated enrichers due to lower complexity or field counts.

Handles config types with < 30 keys or simple structure:
- Volume configs (8 keys) - Volume mappings and basic volume info
- Host configs - Host group and individual host configurations
- Ethernet configs - Network interface configurations  
- Hardware configs - Basic hardware component info
- System configs - High-level system settings
- Snapshot configs - Point-in-time snapshot configurations

Uses shared enrichment patterns while maintaining type-specific logic.
"""

import logging
from typing import Dict, Any
from app.enrichment.config_enrichment import BaseConfigEnricher

LOG = logging.getLogger(__name__)

class SharedConfigEnricher(BaseConfigEnricher):
    """
    Shared enricher for simpler configuration types.
    
    Provides type-appropriate enrichment without the complexity
    needed for drive/controller/storage configs.
    """
    
    def __init__(self, system_enricher=None):
        """Initialize shared config enricher."""
        super().__init__(system_enricher)
        
        # Common status mappings across config types
        self.status_map = {
            'optimal': 'healthy',
            'ok': 'healthy', 
            'good': 'healthy',
            'online': 'healthy',
            'active': 'healthy',
            'degraded': 'warning',
            'warning': 'warning',
            'inactive': 'warning',
            'failed': 'critical',
            'offline': 'critical',
            'error': 'critical',
            'unknown': 'unknown'
        }
        
        # Volume types for classification
        self.volume_types = {
            'thick': 'thick_provisioned',
            'thin': 'thin_provisioned',  
            'repository': 'repository',
            'snapshot': 'snapshot'
        }
    
    def enrich_item(self, raw_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Apply type-appropriate enrichment based on config type.
        
        Dispatches to specific enrichment methods based on config type
        while maintaining shared patterns and standardization.
        """
        enriched_item = raw_item.copy()
        
        # Dispatch to type-specific enrichment
        config_type_lower = config_type.lower()
        
        if 'volume' in config_type_lower:
            return self._enrich_volume_config(enriched_item, config_type)
        elif 'host' in config_type_lower:
            return self._enrich_host_config(enriched_item, config_type)
        elif 'ethernet' in config_type_lower or 'interface' in config_type_lower:
            return self._enrich_ethernet_config(enriched_item, config_type)
        elif 'snapshot' in config_type_lower:
            return self._enrich_snapshot_config(enriched_item, config_type)
        elif 'hardware' in config_type_lower:
            return self._enrich_hardware_config(enriched_item, config_type)
        elif 'system' in config_type_lower:
            return self._enrich_system_config(enriched_item, config_type)
        else:
            # Generic enrichment for unknown types
            return self._enrich_generic_config(enriched_item, config_type)
    
    def _enrich_volume_config(self, enriched_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Enrich volume configuration data.
        
        Focus on volume identity, capacity, and pool assignment.
        """
        # === VOLUME IDENTITY ===
        volume_ref = (enriched_item.get('volumeRef') or 
                     enriched_item.get('id') or 
                     enriched_item.get('ref'))
        if volume_ref:
            enriched_item['volume_id'] = volume_ref
            enriched_item['volume_ref'] = volume_ref
        
        # Volume name/label
        volume_name = enriched_item.get('label') or enriched_item.get('name')
        if volume_name:
            enriched_item['volume_name'] = volume_name
        
        # === CAPACITY INFORMATION ===
        # Volume capacity
        capacity = enriched_item.get('capacity')
        if capacity:
            try:
                capacity_gb = int(capacity) // (1024**3)
                enriched_item['volume_capacity_gb'] = capacity_gb
                
                # Size tier
                if capacity_gb >= 10000:  # 10TB+
                    enriched_item['volume_size_tier'] = 'very_large'
                elif capacity_gb >= 1000:  # 1TB+
                    enriched_item['volume_size_tier'] = 'large'
                elif capacity_gb >= 100:   # 100GB+
                    enriched_item['volume_size_tier'] = 'medium'
                else:
                    enriched_item['volume_size_tier'] = 'small'
            except (ValueError, TypeError):
                pass
        
        # === POOL ASSIGNMENT ===
        # Volume group (storage pool) reference
        volume_group_ref = enriched_item.get('volumeGroupRef')
        if volume_group_ref:
            enriched_item['volume_pool_ref'] = volume_group_ref
        
        # === VOLUME CHARACTERISTICS ===
        # Provisioning type
        thin_provisioned = enriched_item.get('thinProvisioned')
        if thin_provisioned is not None:
            if str(thin_provisioned).lower() == 'true':
                enriched_item['volume_provisioning'] = 'thin'
            else:
                enriched_item['volume_provisioning'] = 'thick'
        
        # Volume status
        status = enriched_item.get('status', '').lower()
        if status:
            enriched_item['volume_status'] = status
            enriched_item['volume_health'] = self.status_map.get(status, 'unknown')
        
        # === MAPPING INFORMATION ===  
        # LUN mapping (for host connectivity)
        lun = enriched_item.get('lun')
        if lun is not None:
            enriched_item['volume_lun'] = lun
        
        # Mapped host reference
        mapped_to_ref = enriched_item.get('mapRef')
        if mapped_to_ref:
            enriched_item['volume_mapped_to'] = mapped_to_ref
            enriched_item['volume_mapped'] = 'true'
        else:
            enriched_item['volume_mapped'] = 'false'
        
        return enriched_item
    
    def _enrich_host_config(self, enriched_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Enrich host and host group configuration data.
        
        Focus on host identity, group membership, and initiator info.
        """
        # === HOST IDENTITY ===
        host_ref = (enriched_item.get('hostRef') or 
                   enriched_item.get('id') or 
                   enriched_item.get('ref'))
        if host_ref:
            enriched_item['host_id'] = host_ref
            enriched_item['host_ref'] = host_ref
        
        # Host name/label
        host_name = enriched_item.get('label') or enriched_item.get('name')
        if host_name:
            enriched_item['host_name'] = host_name
        
        # === HOST TYPE AND OS ===
        # Host type (affects driver and optimization)
        host_type = enriched_item.get('hostTypeIndex')
        if host_type is not None:
            enriched_item['host_type_index'] = host_type
        
        # Operating system (if available in hostType)
        host_type_info = enriched_item.get('hostType', {})
        if isinstance(host_type_info, dict):
            os_name = host_type_info.get('name', '').lower()
            if 'linux' in os_name:
                enriched_item['host_os'] = 'linux'
            elif 'windows' in os_name:
                enriched_item['host_os'] = 'windows'
            elif 'vmware' in os_name:
                enriched_item['host_os'] = 'vmware'
            elif 'aix' in os_name:
                enriched_item['host_os'] = 'aix'
            else:
                enriched_item['host_os'] = 'other'
        
        # === GROUP MEMBERSHIP ===
        # Host group assignment
        cluster_ref = enriched_item.get('clusterRef')
        if cluster_ref:
            enriched_item['host_group_ref'] = cluster_ref
            enriched_item['host_clustered'] = 'true'
        else:
            enriched_item['host_clustered'] = 'false'
        
        # === INITIATOR INFORMATION ===
        # Initiator count and types
        initiators = enriched_item.get('initiators', [])
        if isinstance(initiators, list):
            enriched_item['host_initiator_count'] = len(initiators)
            
            # Analyze initiator types
            initiator_types = set()
            for initiator in initiators:
                if isinstance(initiator, dict):
                    itype = initiator.get('initiatorType', '').lower()
                    if itype:
                        initiator_types.add(itype)
            
            if initiator_types:
                if len(initiator_types) == 1:
                    enriched_item['host_initiator_type'] = list(initiator_types)[0]
                else:
                    enriched_item['host_initiator_type'] = 'mixed'
        
        # === PORT CONNECTIVITY ===
        # Host port information
        host_ports = enriched_item.get('hostSidePorts', [])
        if isinstance(host_ports, list):
            enriched_item['host_port_count'] = len(host_ports)
        
        return enriched_item
    
    def _enrich_ethernet_config(self, enriched_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Enrich ethernet/network interface configuration data.
        
        Focus on network connectivity and interface characteristics.
        """
        # === INTERFACE IDENTITY ===
        interface_ref = (enriched_item.get('interfaceRef') or 
                        enriched_item.get('id') or 
                        enriched_item.get('ref'))
        if interface_ref:
            enriched_item['interface_id'] = interface_ref
        
        # === NETWORK CONFIGURATION ===
        # IP address information
        ipv4_config = enriched_item.get('ipv4Config', {})
        if isinstance(ipv4_config, dict):
            ip_address = ipv4_config.get('ipAddress')
            if ip_address:
                enriched_item['interface_ip_address'] = ip_address
            
            # IP configuration method
            config_method = ipv4_config.get('configMethod', '').lower()
            if config_method:
                enriched_item['interface_ip_method'] = config_method
        
        # === LINK CHARACTERISTICS ===
        # Link speed and state
        link_speed = enriched_item.get('linkSpeed')
        if link_speed:
            enriched_item['interface_speed'] = link_speed
        
        link_state = enriched_item.get('linkState', '').lower() 
        if link_state:
            enriched_item['interface_state'] = link_state
            
            # Map to health status
            if link_state == 'up':
                enriched_item['interface_health'] = 'healthy'
            elif link_state == 'down':
                enriched_item['interface_health'] = 'critical'
            else:
                enriched_item['interface_health'] = 'unknown'
        
        # === INTERFACE TYPE ===
        # Physical interface characteristics
        interface_type = enriched_item.get('interfaceType', '').lower()
        if interface_type:
            enriched_item['interface_type'] = interface_type
        
        return enriched_item
    
    def _enrich_snapshot_config(self, enriched_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Enrich snapshot configuration data.
        
        Focus on snapshot identity, base volume, and state.
        """
        # === SNAPSHOT IDENTITY ===
        snapshot_ref = (enriched_item.get('pitRef') or 
                       enriched_item.get('id') or 
                       enriched_item.get('ref'))
        if snapshot_ref:
            enriched_item['snapshot_id'] = snapshot_ref
            enriched_item['snapshot_ref'] = snapshot_ref
        
        # Snapshot name/label
        snapshot_name = enriched_item.get('label') or enriched_item.get('name')
        if snapshot_name:
            enriched_item['snapshot_name'] = snapshot_name
        
        # === BASE VOLUME REFERENCE ===
        # Source volume for the snapshot
        base_volume_ref = enriched_item.get('baseVolumeRef')
        if base_volume_ref:
            enriched_item['snapshot_base_volume'] = base_volume_ref
        
        # === SNAPSHOT CHARACTERISTICS ===
        # Creation timestamp
        creation_time = enriched_item.get('creationTime')
        if creation_time:
            enriched_item['snapshot_creation_time'] = creation_time
        
        # Snapshot status
        status = enriched_item.get('status', '').lower()
        if status:
            enriched_item['snapshot_status'] = status
            enriched_item['snapshot_health'] = self.status_map.get(status, 'unknown')
        
        return enriched_item
    
    def _enrich_hardware_config(self, enriched_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Enrich hardware component configuration data.
        
        Focus on component identity and basic characteristics.
        """
        # === COMPONENT IDENTITY ===
        component_ref = (enriched_item.get('componentRef') or 
                        enriched_item.get('id') or 
                        enriched_item.get('ref'))
        if component_ref:
            enriched_item['hardware_component_id'] = component_ref
        
        # Component type
        component_type = enriched_item.get('componentType', '').lower()
        if component_type:
            enriched_item['hardware_component_type'] = component_type
        
        # === LOCATION INFORMATION ===
        # Physical location
        location = enriched_item.get('location')
        if location:
            enriched_item['hardware_location'] = location
        
        # === STATUS ===
        # Component status
        status = enriched_item.get('status', '').lower()
        if status:
            enriched_item['hardware_status'] = status
            enriched_item['hardware_health'] = self.status_map.get(status, 'unknown')
        
        return enriched_item
    
    def _enrich_system_config(self, enriched_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Enrich system-level configuration data.
        
        Focus on system identity and high-level settings.
        """
        # System name is often already handled by base enricher
        # Add any system-specific enrichments here
        
        # System model information
        model = enriched_item.get('model')
        if model:
            enriched_item['system_model'] = model
        
        # Firmware version
        firmware = enriched_item.get('fwVersion')
        if firmware:
            enriched_item['system_firmware'] = firmware
        
        return enriched_item
    
    def _enrich_generic_config(self, enriched_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Generic enrichment for unknown or unspecified config types.
        
        Provides basic standardization without type-specific logic.
        """
        # Generic ID field handling
        generic_id = (enriched_item.get('id') or 
                     enriched_item.get('ref') or
                     enriched_item.get('objectId'))
        if generic_id:
            enriched_item[f'{config_type}_id'] = generic_id
        
        # Generic name field handling 
        generic_name = (enriched_item.get('label') or 
                       enriched_item.get('name'))
        if generic_name:
            enriched_item[f'{config_type}_name'] = generic_name
        
        # Generic status handling
        status = enriched_item.get('status', '').lower()
        if status:
            enriched_item[f'{config_type}_status'] = status
            enriched_item[f'{config_type}_health'] = self.status_map.get(status, 'unknown')
        
        LOG.debug(f"Applied generic enrichment to {config_type}")
        return enriched_item