import time
import logging
from typing import Dict, Generic, List, Optional, Type, TypeVar, Any
from functools import lru_cache

# Type variable for our cache generic
T = TypeVar('T')

class CacheManager(Generic[T]):
    """
    Generic cache manager for API response objects
    
    Provides:
    - Time-based expiration
    - Collection frequency control
    - Access to cached objects by ID and type
    """
    
    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize cache manager
        
        Args:
            ttl_seconds: Default time-to-live in seconds
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._timestamps: Dict[str, float] = {}
        self._ttl_seconds = ttl_seconds
        self._last_collection: Dict[str, float] = {}
        self.logger = logging.getLogger(__name__)
    
    def set(self, cache_type: str, key: str, value: T) -> None:
        """
        Store an object in the cache
        
        Args:
            cache_type: Type of cached object (e.g., 'drives', 'volumes')
            key: Unique identifier for the object
            value: Object to cache
        """
        if cache_type not in self._cache:
            self._cache[cache_type] = {}
        
        self._cache[cache_type][key] = value
        self._timestamps[f"{cache_type}:{key}"] = time.time()
    
    def get(self, cache_type: str, key: str) -> Optional[T]:
        """
        Retrieve an object from the cache
        
        Args:
            cache_type: Type of cached object
            key: Unique identifier for the object
            
        Returns:
            The cached object or None if not found or expired
        """
        if cache_type not in self._cache or key not in self._cache[cache_type]:
            return None
        
        # Check expiration
        timestamp_key = f"{cache_type}:{key}"
        if timestamp_key in self._timestamps:
            if time.time() - self._timestamps[timestamp_key] > self._ttl_seconds:
                # Expired
                del self._cache[cache_type][key]
                del self._timestamps[timestamp_key]
                return None
        
        return self._cache[cache_type][key]
    
    def get_all(self, cache_type: str) -> Dict[str, T]:
        """
        Get all non-expired objects of a specific type
        
        Args:
            cache_type: Type of cached objects to retrieve
            
        Returns:
            Dictionary of objects by key
        """
        if cache_type not in self._cache:
            return {}
        
        # Filter out expired items
        result = {}
        expired_keys = []
        
        for key, value in self._cache[cache_type].items():
            timestamp_key = f"{cache_type}:{key}"
            if timestamp_key in self._timestamps:
                if time.time() - self._timestamps[timestamp_key] > self._ttl_seconds:
                    expired_keys.append(key)
                else:
                    result[key] = value
        
        # Clean up expired items
        for key in expired_keys:
            del self._cache[cache_type][key]
            del self._timestamps[f"{cache_type}:{key}"]
        
        return result
    
    def should_collect(self, collection_type: str, interval_seconds: int) -> bool:
        """
        Determine if data collection should happen based on interval
        
        Args:
            collection_type: Type of collection (e.g., 'drives', 'volumes')
            interval_seconds: Minimum interval between collections
            
        Returns:
            True if collection should happen, False otherwise
        """
        current_time = time.time()
        last_time = self._last_collection.get(collection_type, 0)
        
        if current_time - last_time >= interval_seconds:
            self._last_collection[collection_type] = current_time
            return True
        return False
    
    def mark_collected(self, collection_type: str) -> None:
        """
        Mark a collection type as collected now
        
        Args:
            collection_type: Type of collection to mark
        """
        self._last_collection[collection_type] = time.time()
    
    def clear(self, cache_type: Optional[str] = None) -> None:
        """
        Clear cache entries
        
        Args:
            cache_type: Type to clear or None for all
        """
        if cache_type is None:
            self._cache = {}
            # Only clear timestamps that belong to cache entries
            self._timestamps = {k: v for k, v in self._timestamps.items() if k.split(":")[0] not in self._cache}
        elif cache_type in self._cache:
            # Remove all entries of this type
            keys = list(self._cache[cache_type].keys())
            for key in keys:
                timestamp_key = f"{cache_type}:{key}"
                if timestamp_key in self._timestamps:
                    del self._timestamps[timestamp_key]
            del self._cache[cache_type]
