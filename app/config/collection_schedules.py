#!/usr/bin/env python3
"""
Configuration collection scheduling for E-Series Performance Analyzer

This module defines collection schedules for different types of configuration data,
allowing fine-grained control over how frequently different config objects are collected.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Set, Optional
import time
import logging
from datetime import datetime, timedelta

LOG = logging.getLogger(__name__)

class ScheduleFrequency(Enum):
    """User-configurable collection frequencies with multipliers"""
    HIGH_FREQUENCY = "high"       # Every collection cycle (1x base interval)
    MEDIUM_FREQUENCY = "medium"   # Every 15x base interval
    LOW_FREQUENCY = "low"         # Every 360x base interval (6 hours at 60s base)
    DAILY = "daily"               # Every 1440x base interval (24 hours at 60s base)
    WEEKLY = "weekly"             # Every 10080x base interval (7 days at 60s base)

# Supported base intervals that users can choose from
SUPPORTED_BASE_INTERVALS = [60, 120, 180, 300]  # seconds

# Multipliers for each frequency relative to base interval
FREQUENCY_MULTIPLIERS = {
    ScheduleFrequency.HIGH_FREQUENCY: 1,     # Same as base interval
    ScheduleFrequency.MEDIUM_FREQUENCY: 15,  # 15x base (15min at 60s, 75min at 300s)
    ScheduleFrequency.LOW_FREQUENCY: 360,    # 6 hours at 60s base, 30 hours at 300s base
    ScheduleFrequency.DAILY: 1440,           # 24 hours at 60s base, 5 days at 300s base 
    ScheduleFrequency.WEEKLY: 10080          # 7 days at 60s base, 35 days at 300s base
}

@dataclass
class CollectionSchedule:
    """Definition of a collection schedule with iteration-based timing"""
    name: str
    frequency: ScheduleFrequency
    multiplier: int
    base_interval: int
    effective_interval: int  # multiplier * base_interval
    description: str
    
    def should_collect_on_iteration(self, iteration_count: int) -> bool:
        """
        Determine if collection should occur on this iteration
        
        Args:
            iteration_count: Current iteration number (starts at 1)
            
        Returns:
            True if collection should occur on this iteration
        """
        return iteration_count % self.multiplier == 0

def create_collection_schedules(base_interval: int) -> Dict[ScheduleFrequency, CollectionSchedule]:
    """
    Create collection schedules based on user's base interval
    
    Args:
        base_interval: User's --interval setting in seconds
        
    Returns:
        Dictionary mapping frequencies to schedule objects
        
    Raises:
        ValueError: If base_interval is not supported
    """
    if base_interval not in SUPPORTED_BASE_INTERVALS:
        raise ValueError(f"Base interval {base_interval}s not supported. "
                        f"Choose from: {SUPPORTED_BASE_INTERVALS}")
    
    schedules = {}
    for frequency, multiplier in FREQUENCY_MULTIPLIERS.items():
        effective_interval = base_interval * multiplier
        
        schedules[frequency] = CollectionSchedule(
            name=frequency.value,
            frequency=frequency,
            multiplier=multiplier,
            base_interval=base_interval,
            effective_interval=effective_interval,
            description=f"Collect every {multiplier}x base interval "
                       f"({effective_interval}s = {effective_interval//60:.1f}min)"
        )
    
    return schedules

# Configuration object to schedule mapping
CONFIG_COLLECTION_MAPPING = {
    # High frequency - data that changes frequently or is critical for enrichment
    ScheduleFrequency.HIGH_FREQUENCY: [
        "VolumeConfig",           # Volume mappings change frequently
        "VolumeMappingsConfig",   # Critical for volume enrichment
        "HostConfig",             # Host connectivity can change
        "TrayConfig",             # DEBUG: Tray configuration rarely changes
    ],
    
    # Medium frequency - moderately changing configuration
    ScheduleFrequency.MEDIUM_FREQUENCY: [
        "StoragePoolConfig",      # Pool utilization changes, but not rapidly
        "HostGroupsConfig",       # Host group membership changes occasionally  
        "ControllerConfig",       # Controller status/interfaces change occasionally
    ],
    
    # Low frequency - slowly changing hardware/system config
    ScheduleFrequency.LOW_FREQUENCY: [
        "SystemConfig",           # System-level settings change infrequently
        "DriveConfig",            # Drive configuration changes slowly
        "SnapshotConfig",         # Snapshot configurations change infrequently
        "EthernetConfig",         # Ethernet interface configs change infrequently
        "AsyncMirrorsConfig",     # Async mirror configurations change infrequently
    ],
    
    # Daily - very static configuration
    ScheduleFrequency.DAILY: [
        "InterfaceConfig",        # Interface config changes infrequently
        "HardwareConfig",         # Hardware component configs are static
    ],
    
    # Weekly - essentially static data (mainly for auditing)
    ScheduleFrequency.WEEKLY: [
        "VolumeCGMembersConfig",  # Consistency groups rarely used, check weekly only
    ]
}

class ConfigCollectionScheduler:
    """
    Manager for configuration collection scheduling with iteration-based timing
    """
    
    def __init__(self, base_interval: int):
        """
        Initialize the scheduler with base interval
        
        Args:
            base_interval: User's --interval setting in seconds
        """
        self.base_interval = base_interval
        self.schedules = create_collection_schedules(base_interval)
        self.iteration_count = 0
        self.last_collection_iterations: Dict[str, int] = {}
        
    def increment_iteration(self):
        """Call this at the start of each main collection loop"""
        self.iteration_count += 1
        
    def should_collect_config(self, config_type: str) -> tuple[bool, ScheduleFrequency]:
        """
        Determine if a specific config type should be collected on this iteration
        
        Args:
            config_type: Name of the configuration class (e.g., "SystemConfig")
            
        Returns:
            Tuple of (should_collect, schedule_frequency)
        """
        # Find the schedule for this config type
        schedule_frequency = self._get_schedule_for_config(config_type)
        if not schedule_frequency:
            # Default to medium frequency if not explicitly mapped
            schedule_frequency = ScheduleFrequency.MEDIUM_FREQUENCY
            
        schedule = self.schedules[schedule_frequency]
        
        # Check if we should collect on this iteration
        should_collect = schedule.should_collect_on_iteration(self.iteration_count)
        
        if should_collect:
            # Update last collection iteration
            self.last_collection_iterations[config_type] = self.iteration_count
            
        return should_collect, schedule_frequency
    
    def _get_schedule_for_config(self, config_type: str) -> Optional[ScheduleFrequency]:
        """Find the schedule frequency for a given config type"""
        for frequency, config_types in CONFIG_COLLECTION_MAPPING.items():
            if config_type in config_types:
                return frequency
        return None
    
    def get_config_types_for_collection(self) -> Dict[ScheduleFrequency, List[str]]:
        """
        Get all config types that should be collected on this iteration, grouped by frequency
        
        Special behavior for iteration 1: Collect ALL config types to establish initial
        baseline in InfluxDB for downstream users (dashboards, alerts, etc.)
        
        Returns:
            Dictionary mapping frequencies to lists of config types to collect
        """
        collections_needed = {}
        
        # FIRST ITERATION CHECKPOINT: Collect ALL config types to establish baseline
        if self.iteration_count == 1:
            LOG.info("First iteration checkpoint: collecting ALL config types for InfluxDB baseline")
            for frequency, config_types in CONFIG_COLLECTION_MAPPING.items():
                collections_needed[frequency] = config_types.copy()
                # Update tracking for all types
                for config_type in config_types:
                    self.last_collection_iterations[config_type] = self.iteration_count
            return collections_needed
        
        # NORMAL SCHEDULING: Follow regular frequency-based collection
        for frequency, config_types in CONFIG_COLLECTION_MAPPING.items():
            schedule = self.schedules[frequency]
            types_to_collect = []
            
            if schedule.should_collect_on_iteration(self.iteration_count):
                for config_type in config_types:
                    types_to_collect.append(config_type)
                    # Update tracking
                    self.last_collection_iterations[config_type] = self.iteration_count
                    
            if types_to_collect:
                collections_needed[frequency] = types_to_collect
                
        return collections_needed
    
    def force_collection(self, config_type: Optional[str] = None):
        """
        Force collection of specific config type or all types on next iteration
        
        Args:
            config_type: Specific type to force, or None for all types
        """
        if config_type:
            # Reset last collection iteration to force collection
            self.last_collection_iterations[config_type] = 0
        else:
            # Reset all collection iterations
            self.last_collection_iterations.clear()
    
    def get_schedule_info(self) -> Dict[str, Dict]:
        """
        Get information about all schedules and their mappings
        
        Returns:
            Dictionary with schedule information for debugging/logging
        """
        info = {}
        
        for frequency, config_types in CONFIG_COLLECTION_MAPPING.items():
            schedule = self.schedules[frequency]
            info[frequency.value] = {
                'base_interval': self.base_interval,
                'multiplier': schedule.multiplier,
                'effective_interval': schedule.effective_interval,
                'description': schedule.description,
                'config_types': config_types,
                'last_collections': {
                    config_type: self.last_collection_iterations.get(config_type, 0)
                    for config_type in config_types
                }
            }
            
        return info
