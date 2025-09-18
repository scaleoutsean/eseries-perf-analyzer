#!/usr/bin/env python3
"""
API Endpoint Categorization for E-Series Performance Analyzer

This module categorizes E-Series API endpoints into three main types:
- PERFORMANCE: Real-time metrics and statistics 
- CONFIGURATION: Static/semi-static system configuration
- EVENTS: Dynamic status, jobs, alerts, and transient events

Each category has different collection patterns and storage requirements.
"""

from enum import Enum
from typing import Dict, List, Set, Any

class EndpointCategory(Enum):
    """Categories for API endpoint collection"""
    PERFORMANCE = "performance"     # Real-time metrics, always collected
    CONFIGURATION = "configuration" # Static config, cached and collected per schedule
    EVENTS = "events"              # Dynamic status/jobs, immediate write to DB

# Endpoint categorization based on tools/collect_items.py
ENDPOINT_CATEGORIES = {
    
    # PERFORMANCE: Real-time metrics and statistics
    EndpointCategory.PERFORMANCE: {
        'analyzed_volume_statistics',
        'analyzed_drive_statistics', 
        'analyzed_system_statistics',
        'analyzed_interface_statistics',
        'analyzed_controller_statistics',
        
        # Aggregate data keys from main collection
        'performance_data',
        'total_records',
        'status',
    },
    
    # CONFIGURATION: Static/semi-static system configuration
    EndpointCategory.CONFIGURATION: {
        # System-level configuration
        'system_config',
        'controller_config',
        'hardware_inventory',
        'tray_config',
        'ethernet_interface_config',
        'interfaces_config',
        
        # Storage configuration
        'storage_pools',
        'volumes_config',
        'volume_mappings_config',
        'drive_config',
        'ssd_cache',
        
        # Host connectivity
        'hosts',
        'host_groups',
        'interfaces',
        
        # Advanced storage features
        'snapshot_schedules',
        'snapshot_groups',
        'snapshot_volumes',
        'snapshot_images',
        'mirrors',
        'async_mirrors',
        'volume_consistency_group_config',
        'volume_consistency_group_members',
        
        # ID-dependent configuration endpoints
        'snapshot_groups_repository_utilization',
        'volume_expansion_progress',
    },
    
    # EVENTS: Dynamic status, jobs, alerts, and transient events
    EndpointCategory.EVENTS: {
        # System status and events
        'system_events',
        'lockdown_status',
        'system_failures',
        
        # Job status and progress
        'volume_parity_check_status',
        'volume_parity_job_check_errors',
        'data_parity_scan_job_status',
        'volume_copy_jobs',
        'volume_copy_job_progress',
        'drives_erase_progress',
        'storage_pools_action_progress',
        'volume_expansion_progress',
        
        # Alert and failure information
        # Note: Add more event-type endpoints here as discovered
    }
}

def get_endpoint_category(endpoint_name: str) -> EndpointCategory:
    """
    Get the category for a given endpoint name
    
    Args:
        endpoint_name: Name of the API endpoint
        
    Returns:
        EndpointCategory enum value
        
    Raises:
        ValueError: If endpoint is not categorized
    """
    for category, endpoints in ENDPOINT_CATEGORIES.items():
        if endpoint_name in endpoints:
            return category
    
    raise ValueError(f"Endpoint '{endpoint_name}' is not categorized")

def get_endpoints_by_category(category: EndpointCategory) -> Set[str]:
    """
    Get all endpoints for a specific category
    
    Args:
        category: The endpoint category
        
    Returns:
        Set of endpoint names in that category
    """
    return ENDPOINT_CATEGORIES.get(category, set())

def get_all_categorized_endpoints() -> Set[str]:
    """
    Get all endpoints that have been categorized
    
    Returns:
        Set of all categorized endpoint names
    """
    all_endpoints = set()
    for endpoints in ENDPOINT_CATEGORIES.values():
        all_endpoints.update(endpoints)
    return all_endpoints

def validate_endpoint_coverage(all_known_endpoints: Set[str]) -> Dict[str, List[str]]:
    """
    Validate that all known endpoints are categorized
    
    Args:
        all_known_endpoints: Set of all endpoints that should be categorized
        
    Returns:
        Dictionary with 'categorized' and 'uncategorized' lists
    """
    categorized = get_all_categorized_endpoints()
    uncategorized = all_known_endpoints - categorized
    
    return {
        'categorized': sorted(list(categorized)),
        'uncategorized': sorted(list(uncategorized))
    }

# Collection behavior definitions
COLLECTION_BEHAVIORS = {
    EndpointCategory.PERFORMANCE: {
        'write_immediately': True,     # Write to DB immediately
        'cache_data': False,           # Don't cache performance data
        'use_scheduler': False,        # Always collect (no scheduling)
        'export_prometheus': True,     # Export via Prometheus
        'typical_frequency': 'FREQUENT_REFRESH',  # Every 5 minutes
        'enable_enrichment': True,     # Performance data is always enriched
        'enrichment_type': 'performance',  # Use performance enrichment pipeline
    },
    
    EndpointCategory.CONFIGURATION: {
        'write_immediately': False,     # Cache and write periodically
        'cache_data': True,            # Cache config data for enrichment
        'use_scheduler': True,         # Use scheduling system
        'export_prometheus': False,    # Don't export via Prometheus (too static)
        'typical_frequency': 'STANDARD_REFRESH',  # Every 10 minutes
    },
    
    EndpointCategory.EVENTS: {
        'write_immediately': True,      # Write to DB immediately when data exists
        'cache_data': False,           # Don't cache event data
        'use_scheduler': False,        # Check frequently, write only when data exists
        'export_prometheus': False,    # Events are more suited to logs/alerts
        'typical_frequency': 'FREQUENT_REFRESH',  # Check every 5 minutes
        'write_only_when_data': True,  # Only write when response is not empty
        'enable_enrichment': True,     # Enable event enrichment for alerting
        'enrichment_type': 'event',    # Use event enrichment pipeline
        'enable_deduplication': True,  # Enable event deduplication
        'dedup_window_minutes': 5,     # Deduplication window in minutes
        'enable_grafana_annotations': False,  # Optional Grafana annotation integration
    }
}

def get_collection_behavior(category: EndpointCategory) -> Dict[str, Any]:
    """
    Get the collection behavior configuration for a category
    
    Args:
        category: The endpoint category
        
    Returns:
        Dictionary with collection behavior settings
    """
    return COLLECTION_BEHAVIORS.get(category, {})

# Enrichment processor mapping for reference
# This documents which enrichment processors handle which endpoints
ENRICHMENT_PROCESSOR_MAPPING = {
    # Performance endpoints → specific enrichment processors
    'analyzed_volume_statistics': 'VolumeEnrichmentProcessor',
    'analyzed_drive_statistics': 'DriveEnrichmentProcessor', 
    'analyzed_system_statistics': 'SystemEnrichmentProcessor',
    'analyzed_interface_statistics': 'ControllerEnrichmentProcessor',
    'analyzed_controller_statistics': 'ControllerEnrichmentProcessor',
    
    # Event endpoints → event enrichment processor
    'system_events': 'EventEnrichment',
    'system_failures': 'EventEnrichment',
    'lockdown_status': 'EventEnrichment',
    'volume_parity_check_status': 'EventEnrichment',
    # ... other event endpoints use EventEnrichment
}

def get_enrichment_processor(endpoint_name: str) -> str:
    """
    Get the enrichment processor class name for a given endpoint
    
    Args:
        endpoint_name: Name of the API endpoint
        
    Returns:
        Name of the enrichment processor class
        
    Raises:
        ValueError: If no enrichment processor is defined for the endpoint
    """
    processor = ENRICHMENT_PROCESSOR_MAPPING.get(endpoint_name)
    if not processor:
        # Check category-level enrichment
        try:
            category = get_endpoint_category(endpoint_name)
            behavior = get_collection_behavior(category)
            if behavior.get('enable_enrichment'):
                enrichment_type = behavior.get('enrichment_type', 'unknown')
                return f"{enrichment_type.title()}Enrichment"
        except ValueError:
            pass
        
        raise ValueError(f"No enrichment processor defined for endpoint '{endpoint_name}'")
    
    return processor