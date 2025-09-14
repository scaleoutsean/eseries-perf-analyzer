from typing import Dict, List, Optional
import logging

from app.cache.cache_manager import CacheManager
from app.schema.models import (
    DriveConfig, 
    VolumeConfig,
    StoragePoolConfig,
    ControllerConfig,
    SystemConfig,
    # Import other models as needed
)

class ConfigCache:
    """
    Cache for configuration objects
    
    Provides:
    - Type-specific retrieval methods
    - Collection scheduling
    - Cross-object relationships
    """
    
    # Default collection intervals in seconds
    DRIVE_CONFIG_INTERVAL = 3600  # 1 hour
    VOLUME_CONFIG_INTERVAL = 3600  # 1 hour
    SYSTEM_CONFIG_INTERVAL = 3600  # 1 hour
    POOL_CONFIG_INTERVAL = 3600    # 1 hour
    
    def __init__(self, ttl_seconds: int = 14400):  # 4 hours
        """
        Initialize configuration cache
        
        Args:
            ttl_seconds: Time-to-live for cached objects
        """
        self._cache = CacheManager(ttl_seconds=ttl_seconds)
        self.logger = logging.getLogger(__name__)
    
    # Drive methods
    def store_drive(self, system_id: str, drive: DriveConfig) -> None:
        """Store a drive configuration"""
        key = f"{system_id}:{drive.id}"
        self._cache.set('drives', key, drive)
    
    def get_drive(self, system_id: str, drive_id: str) -> Optional[DriveConfig]:
        """Get a drive configuration by ID"""
        return self._cache.get('drives', f"{system_id}:{drive_id}")
    
    def get_all_drives(self, system_id: str) -> Dict[str, DriveConfig]:
        """Get all drives for a system"""
        all_drives = self._cache.get_all('drives')
        # Filter to only this system's drives
        return {k.split(':')[1]: v for k, v in all_drives.items() 
                if k.startswith(f"{system_id}:")}
    
    def should_collect_drives(self, system_id: str) -> bool:
        """Check if drive configuration should be collected"""
        return self._cache.should_collect(f"drives:{system_id}", self.DRIVE_CONFIG_INTERVAL)
    
    # Volume methods
    def store_volume(self, system_id: str, volume: VolumeConfig) -> None:
        """Store a volume configuration"""
        key = f"{system_id}:{volume.id}"
        self._cache.set('volumes', key, volume)
    
    def get_volume(self, system_id: str, volume_id: str) -> Optional[VolumeConfig]:
        """Get a volume configuration by ID"""
        return self._cache.get('volumes', f"{system_id}:{volume_id}")
    
    def get_all_volumes(self, system_id: str) -> Dict[str, VolumeConfig]:
        """Get all volumes for a system"""
        all_volumes = self._cache.get_all('volumes')
        # Filter to only this system's volumes
        return {k.split(':')[1]: v for k, v in all_volumes.items() 
                if k.startswith(f"{system_id}:")}
    
    def should_collect_volumes(self, system_id: str) -> bool:
        """Check if volume configuration should be collected"""
        return self._cache.should_collect(f"volumes:{system_id}", self.VOLUME_CONFIG_INTERVAL)
    
    # Storage Pool methods
    def store_storage_pool(self, system_id: str, pool: StoragePoolConfig) -> None:
        """Store a storage pool configuration"""
        key = f"{system_id}:{pool.id}"
        self._cache.set('pools', key, pool)
    
    def get_storage_pool(self, system_id: str, pool_id: str) -> Optional[StoragePoolConfig]:
        """Get a storage pool configuration by ID"""
        return self._cache.get('pools', f"{system_id}:{pool_id}")
    
    def should_collect_pools(self, system_id: str) -> bool:
        """Check if pool configuration should be collected"""
        return self._cache.should_collect(f"pools:{system_id}", self.POOL_CONFIG_INTERVAL)
    
    # System methods
    def store_system(self, system: SystemConfig) -> None:
        """Store system configuration"""
        self._cache.set('systems', system.id, system)
    
    def get_system(self, system_id: str) -> Optional[SystemConfig]:
        """Get system configuration"""
        return self._cache.get('systems', system_id)
    
    def should_collect_system(self, system_id: str) -> bool:
        """Check if system configuration should be collected"""
        return self._cache.should_collect(f"system:{system_id}", self.SYSTEM_CONFIG_INTERVAL)
    
    # Helper methods to find relationships between objects
    def get_volumes_for_pool(self, system_id: str, pool_id: str) -> List[VolumeConfig]:
        """Get all volumes that belong to a storage pool"""
        volumes = self.get_all_volumes(system_id)
        return [v for v in volumes.values() 
                if v.get_raw('volumeGroupRef') == pool_id]
    
    def get_drives_for_pool(self, system_id: str, pool_id: str) -> List[DriveConfig]:
        """Get all drives that belong to a storage pool"""
        # This might require additional logic depending on your data model
        # and how drives are associated with pools
        pass
