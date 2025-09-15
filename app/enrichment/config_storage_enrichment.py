"""
Storage Configuration Enrichment for E-Series Performance Analyzer

This module enriches storage pool configuration data with pool-specific
tags and context for capacity planning and performance monitoring.

Storage configs have medium-high complexity (37+ keys) and require dedicated
enrichment to properly tag storage pools by:
- Capacity and utilization metrics
- RAID configuration and protection
- Performance characteristics
- Pool state and health
- Drive composition and allocation
"""

import logging
from typing import Dict, Any, List
from app.enrichment.config_enrichment import BaseConfigEnricher

LOG = logging.getLogger(__name__)

class StorageConfigEnricher(BaseConfigEnricher):
    """
    Dedicated enricher for storage pool configuration data.
    
    Handles complex storage pool configs by promoting critical capacity,
    performance, and RAID fields to InfluxDB tags for monitoring.
    """
    
    def __init__(self, system_enricher=None):
        """Initialize storage pool config enricher."""
        super().__init__(system_enricher)
        
        # RAID level mappings for standardization
        self.raid_level_map = {
            'raid0': '0',
            'raid1': '1', 
            'raid5': '5',
            'raid6': '6',
            'raid10': '10',
            'raidDiskPool': 'diskpool',
            'unknown': 'unknown'
        }
        
        # Pool state mappings
        self.state_map = {
            'optimal': 'healthy',
            'complete': 'healthy',
            'ok': 'healthy',
            'degraded': 'warning',
            'critical': 'critical',
            'failed': 'critical',
            'offline': 'critical',
            'unknown': 'unknown'
        }
    
    def enrich_item(self, raw_item: Dict[str, Any], config_type: str) -> Dict[str, Any]:
        """
        Enrich storage pool config with pool-specific tags and metrics.
        
        Key enrichments:
        - Pool identification and labeling
        - Capacity metrics and utilization 
        - RAID configuration details
        - Pool state and health
        - Drive allocation and composition
        """
        enriched_item = raw_item.copy()
        
        # === CORE IDENTITY TAGS ===
        # Pool ID/Reference (critical for capacity joins)
        pool_ref = (enriched_item.get('volumeGroupRef') or 
                   enriched_item.get('id') or 
                   enriched_item.get('ref'))
        if pool_ref:
            enriched_item['pool_id'] = pool_ref
            enriched_item['pool_ref'] = pool_ref
        
        # Pool name/label (human-readable identifier)
        pool_name = enriched_item.get('label') or enriched_item.get('name')
        if pool_name:
            enriched_item['pool_name'] = pool_name
        else:
            # Fallback to ID-based name
            enriched_item['pool_name'] = f"pool_{pool_ref[:8] if pool_ref else 'unknown'}"
        
        # === CAPACITY METRICS ===
        # Total capacity (critical for capacity planning)
        total_capacity = enriched_item.get('totalRaidedSpace')
        if total_capacity:
            try:
                capacity_gb = int(total_capacity) // (1024**3)  # Convert bytes to GB
                enriched_item['pool_capacity_gb'] = capacity_gb
                
                # Capacity tier for grouping
                if capacity_gb >= 100000:  # 100TB+
                    enriched_item['pool_capacity_tier'] = 'massive'
                elif capacity_gb >= 10000:  # 10TB+
                    enriched_item['pool_capacity_tier'] = 'very_large'
                elif capacity_gb >= 1000:   # 1TB+
                    enriched_item['pool_capacity_tier'] = 'large'
                elif capacity_gb >= 100:    # 100GB+
                    enriched_item['pool_capacity_tier'] = 'medium'
                else:
                    enriched_item['pool_capacity_tier'] = 'small'
            except (ValueError, TypeError):
                LOG.warning(f"Could not parse total capacity: {total_capacity}")
        
        # Free space (for utilization monitoring)
        free_space = enriched_item.get('freeSpace')
        if free_space and total_capacity:
            try:
                free_gb = int(free_space) // (1024**3)
                total_gb = int(total_capacity) // (1024**3)
                
                enriched_item['pool_free_gb'] = free_gb
                
                # Calculate utilization percentage
                if total_gb > 0:
                    utilization = ((total_gb - free_gb) / total_gb) * 100
                    enriched_item['pool_utilization_pct'] = round(utilization, 2)
                    
                    # Utilization status for alerting
                    if utilization >= 95:
                        enriched_item['pool_capacity_status'] = 'critical'
                    elif utilization >= 85:
                        enriched_item['pool_capacity_status'] = 'warning'
                    elif utilization >= 75:
                        enriched_item['pool_capacity_status'] = 'high'
                    else:
                        enriched_item['pool_capacity_status'] = 'normal'
            except (ValueError, TypeError):
                LOG.warning(f"Could not calculate pool utilization")
        
        # Used space (calculated or direct)
        used_space = enriched_item.get('usedSpace')
        if used_space:
            try:
                used_gb = int(used_space) // (1024**3)
                enriched_item['pool_used_gb'] = used_gb
            except (ValueError, TypeError):
                pass
        
        # === RAID CONFIGURATION ===
        # RAID level (affects performance and protection)
        raid_level = enriched_item.get('raidLevel', '').lower()
        if raid_level:
            # Normalize RAID level
            normalized_raid = self.raid_level_map.get(raid_level, raid_level)
            enriched_item['pool_raid_level'] = normalized_raid
            
            # RAID characteristics for performance analysis
            if normalized_raid in ['0']:
                enriched_item['pool_raid_type'] = 'performance'
                enriched_item['pool_protection_level'] = 'none'
            elif normalized_raid in ['1', '10']:
                enriched_item['pool_raid_type'] = 'mirrored'
                enriched_item['pool_protection_level'] = 'high'
            elif normalized_raid in ['5']:
                enriched_item['pool_raid_type'] = 'parity_single'
                enriched_item['pool_protection_level'] = 'medium'
            elif normalized_raid in ['6']:
                enriched_item['pool_raid_type'] = 'parity_dual'
                enriched_item['pool_protection_level'] = 'high'
            elif normalized_raid in ['diskpool']:
                enriched_item['pool_raid_type'] = 'dynamic'
                enriched_item['pool_protection_level'] = 'adaptive'
        
        # Stripe depth (affects I/O patterns)
        stripe_depth = enriched_item.get('stripeDepth')
        if stripe_depth:
            enriched_item['pool_stripe_depth'] = stripe_depth
        
        # === POOL STATE AND HEALTH ===
        # Overall pool state
        state = enriched_item.get('state', '').lower()
        if state:
            enriched_item['pool_state'] = state
            
            # Map to health categories
            health = self.state_map.get(state, 'unknown')
            enriched_item['pool_health'] = health
        
        # Offline state indicator
        offline = enriched_item.get('offline')
        if offline is not None:
            enriched_item['pool_offline'] = str(offline).lower()
        
        # === DRIVE COMPOSITION ===
        # Drive count and allocation
        drive_block_format = enriched_item.get('driveBlockFormat', {})
        if isinstance(drive_block_format, dict):
            # Raw capacity before RAID overhead
            raw_capacity = drive_block_format.get('rawCapacity')
            if raw_capacity:
                try:
                    raw_gb = int(raw_capacity) // (1024**3)
                    enriched_item['pool_raw_capacity_gb'] = raw_gb
                    
                    # Calculate RAID overhead if we have both raw and usable
                    if total_capacity:
                        usable_gb = int(total_capacity) // (1024**3)
                        if raw_gb > 0:
                            overhead_pct = ((raw_gb - usable_gb) / raw_gb) * 100
                            enriched_item['pool_raid_overhead_pct'] = round(overhead_pct, 2)
                except (ValueError, TypeError):
                    pass
            
            # Block size (affects I/O performance)
            block_size = drive_block_format.get('blockSize')
            if block_size:
                enriched_item['pool_block_size'] = block_size
        
        # Associated drives (for drive composition analysis)
        drives = enriched_item.get('drives', [])
        if isinstance(drives, list):
            enriched_item['pool_drive_count'] = len(drives)
            
            # Analyze drive types if drive details are available
            drive_types = set()
            drive_sizes = []
            
            for drive in drives:
                if isinstance(drive, dict):
                    # Drive type analysis
                    drive_type = drive.get('driveMediaType', '').lower()
                    if drive_type:
                        drive_types.add(drive_type)
                    
                    # Drive size analysis
                    capacity = drive.get('rawCapacity')
                    if capacity:
                        try:
                            drive_sizes.append(int(capacity))
                        except (ValueError, TypeError):
                            pass
            
            # Drive composition tags
            if drive_types:
                if len(drive_types) == 1:
                    enriched_item['pool_drive_composition'] = 'homogeneous'
                    enriched_item['pool_drive_type'] = list(drive_types)[0]
                else:
                    enriched_item['pool_drive_composition'] = 'mixed'
                    enriched_item['pool_drive_type'] = 'mixed'
            
            # Drive size uniformity
            if drive_sizes and len(set(drive_sizes)) == 1:
                enriched_item['pool_drive_size_uniform'] = 'true'
            elif drive_sizes:
                enriched_item['pool_drive_size_uniform'] = 'false'
        
        # === PERFORMANCE CHARACTERISTICS ===
        # Segment size (affects sequential performance)
        segment_size = enriched_item.get('segmentSize')
        if segment_size:
            enriched_item['pool_segment_size'] = segment_size
            
            # Segment size performance category
            try:
                seg_kb = int(segment_size) // 1024
                if seg_kb >= 512:
                    enriched_item['pool_segment_category'] = 'large_sequential'
                elif seg_kb >= 128:
                    enriched_item['pool_segment_category'] = 'balanced'
                elif seg_kb >= 32:
                    enriched_item['pool_segment_category'] = 'small_random'
                else:
                    enriched_item['pool_segment_category'] = 'very_small'
            except (ValueError, TypeError):
                pass
        
        # === VOLUME ALLOCATION ===
        # Count of volumes in this pool
        volumes = enriched_item.get('volumes', [])
        if isinstance(volumes, list):
            enriched_item['pool_volume_count'] = len(volumes)
            
            if len(volumes) == 0:
                enriched_item['pool_allocation_status'] = 'empty'
            elif len(volumes) >= 10:
                enriched_item['pool_allocation_status'] = 'heavily_used'
            elif len(volumes) >= 5:
                enriched_item['pool_allocation_status'] = 'moderately_used'
            else:
                enriched_item['pool_allocation_status'] = 'lightly_used'
        
        # === SECURITY AND COMPLIANCE ===
        # Encryption status
        secure_capable = enriched_item.get('securityCapable')
        if secure_capable is not None:
            enriched_item['pool_security_capable'] = str(secure_capable).lower()
        
        secure_enabled = enriched_item.get('securityEnabled') 
        if secure_enabled is not None:
            enriched_item['pool_security_enabled'] = str(secure_enabled).lower()
        
        # Protection information (PI) for data integrity
        pi_capable = enriched_item.get('protectionInformationCapable')
        if pi_capable is not None:
            enriched_item['pool_pi_capable'] = str(pi_capable).lower()
        
        LOG.debug(f"Enriched storage pool config: {enriched_item.get('pool_name', 'unknown')} "
                 f"({enriched_item.get('pool_capacity_gb', 0)}GB "
                 f"RAID{enriched_item.get('pool_raid_level', 'unknown')}, "
                 f"{enriched_item.get('pool_drive_count', 0)} drives, "
                 f"{enriched_item.get('pool_health', 'unknown')} health)")
        
        return enriched_item