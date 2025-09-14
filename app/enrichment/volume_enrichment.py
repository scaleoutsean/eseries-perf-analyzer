"""
Volume Performance Enrichment

Enriches volume performance metrics with:
- host: Comma-separated list of host names mapped to the volume
- host_group: Host group name (single value or empty)
- storage_pool: Storage pool name where volume resides
"""

from typing import Dict, List, Set, Optional, Any
import logging

logger = logging.getLogger(__name__)

class VolumeEnrichmentProcessor:
    """Processes volume performance enrichment with host, host group, and storage pool information"""
    
    def __init__(self):
        self.host_lookup = {}           # host_id -> host_config
        self.hostgroup_lookup = {}      # hostgroup_id -> hostgroup_config  
        self.pool_lookup = {}           # pool_id -> pool_config
        self.volume_lookup = {}         # volume_id -> volume_config
        self.volume_mappings = {}       # volume_id -> [mapping_configs]
        
    def load_configuration_data(self, 
                              hosts: List[Dict], 
                              host_groups: List[Dict],
                              storage_pools: List[Dict],
                              volumes: List[Dict],
                              volume_mappings: List[Dict]):
        """Load all configuration data needed for enrichment"""
        
        # Build lookup tables
        self.host_lookup = {h['id']: h for h in hosts}
        self.hostgroup_lookup = {hg['id']: hg for hg in host_groups}
        self.pool_lookup = {p['id']: p for p in storage_pools}
        self.volume_lookup = {v['id']: v for v in volumes}
        
        # Group mappings by volume
        self.volume_mappings = {}
        for mapping in volume_mappings:
            vol_ref = mapping['volumeRef']
            if vol_ref not in self.volume_mappings:
                self.volume_mappings[vol_ref] = []
            self.volume_mappings[vol_ref].append(mapping)
            
        logger.info(f"Loaded enrichment data: {len(hosts)} hosts, {len(host_groups)} host groups, "
                   f"{len(storage_pools)} pools, {len(volumes)} volumes, {len(volume_mappings)} mappings")
    
    def enrich_volume_performance(self, volume_performance: Dict) -> Dict:
        """Enrich a single volume performance measurement with host/pool tags"""
        
        volume_id = volume_performance.get('volumeId')
        if not volume_id:
            logger.warning("Volume performance record missing volumeId")
            return volume_performance
            
        # Get volume configuration
        volume = self.volume_lookup.get(volume_id)
        if not volume:
            logger.warning(f"Volume {volume_id} not found in configuration")
            return volume_performance
            
        # Get storage pool name
        pool_ref = volume.get('volumeGroupRef')
        pool = self.pool_lookup.get(pool_ref)
        pool_name = pool.get('name') if pool else 'unknown'
        
        # Get mappings for this volume
        vol_mappings = self.volume_mappings.get(volume_id, [])
        
        # Build host and host group lists
        host_names = []
        host_group_names = set()
        
        for mapping in vol_mappings:
            map_ref = mapping['mapRef'] 
            mapping_type = mapping['type']
            
            if mapping_type == 'host':
                # Direct host mapping
                host = self.host_lookup.get(map_ref)
                if host:
                    host_name = host.get('label', host.get('name', 'unknown'))
                    host_names.append(host_name)
                    # Check if host is in a group
                    cluster_ref = host.get('clusterRef')
                    if cluster_ref:
                        hostgroup = self.hostgroup_lookup.get(cluster_ref)
                        if hostgroup:
                            host_group_names.add(hostgroup.get('name', 'unknown'))
            
            elif mapping_type == 'cluster':
                # Host group mapping - get all hosts in the group
                hostgroup = self.hostgroup_lookup.get(map_ref)
                if hostgroup:
                    host_group_names.add(hostgroup.get('name', 'unknown'))
                    # Find all hosts that are members of this group
                    for host_id, host in self.host_lookup.items():
                        if host.get('clusterRef') == map_ref:
                            host_name = host.get('label', host.get('name', 'unknown'))
                            host_names.append(host_name)
        
        # Build enrichment tags
        enriched = volume_performance.copy()
        enriched['host'] = ','.join(sorted(set(host_names))) if host_names else ''
        enriched['host_group'] = ','.join(sorted(host_group_names)) if host_group_names else ''
        enriched['storage_pool'] = pool_name
        
        return enriched
    
    def enrich_volume_performance_batch(self, volume_performances: List[Dict]) -> List[Dict]:
        """Enrich a batch of volume performance measurements"""
        
        enriched_results = []
        for perf_record in volume_performances:
            enriched = self.enrich_volume_performance(perf_record)
            enriched_results.append(enriched)
            
        logger.info(f"Enriched {len(enriched_results)} volume performance records")
        return enriched_results