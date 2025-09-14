#!/usr/bin/env python3
"""
Event Enrichment for E-Series Performance Analyzer

Enriches event data with alerting metadata for InfluxDB storage and Grafana integration.
This module:
- Adds alert severity levels and tags
- Prepares events for InfluxDB alerting queries  
- Supports optional Grafana annotation integration
- Handles deduplication logic for repetitive events
"""

import logging
import json
import hashlib
import time
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.schema.base_model import BaseModel
from app.config.endpoint_categories import get_endpoint_category, get_collection_behavior, EndpointCategory

logger = logging.getLogger(__name__)

class EventEnrichment:
    """
    Enriches event data with alerting metadata and handles deduplication.
    """
    
    # Alert severity mapping for different event types
    ALERT_SEVERITY = {
        'system_failures': 'critical',
        'lockdown_status': 'critical', 
        'system_events': 'medium',
        'volume_parity_check_status': 'medium',
        'volume_parity_job_check_errors': 'high',
        'data_parity_scan_job_status': 'medium',
        'volume_copy_jobs': 'low',
        'volume_copy_job_progress': 'low',
        'drives_erase_progress': 'medium',
        'storage_pools_action_progress': 'low',
        'volume_expansion_progress': 'low',
    }
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize event enrichment
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.enable_deduplication = config.get('enable_event_deduplication', True)
        self.dedup_window_minutes = config.get('event_dedup_window_minutes', 5)
        self.enable_grafana_annotations = config.get('enable_grafana_annotations', False)
        
        # In-memory cache for recent event checksums (for deduplication)
        self._recent_events = {}  # {endpoint: {checksum: timestamp}}
        
        logger.info(f"EventEnrichment initialized: dedup={self.enable_deduplication}, "
                   f"window={self.dedup_window_minutes}min, grafana={self.enable_grafana_annotations}")
    
    def enrich_event_data(self, endpoint_name: str, raw_data: List[Dict[str, Any]], 
                         system_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Enrich event data with alerting metadata
        
        Args:
            endpoint_name: Name of the event endpoint
            raw_data: Raw event data from API
            system_info: System information for tagging
            
        Returns:
            List of enriched event records ready for InfluxDB
        """
        if not raw_data:
            return []
        
        # Check if this is a duplicate event (if deduplication enabled)
        if self.enable_deduplication and self._is_duplicate_event(endpoint_name, raw_data):
            logger.debug(f"Skipping duplicate event for {endpoint_name}")
            return []
        
        enriched_records = []
        current_time = int(time.time())
        
        for event_item in raw_data:
            # Create enriched record with alert metadata
            enriched_record = {
                # Original event data
                **event_item,
                
                # Alert metadata
                'alert_type': endpoint_name,
                'alert_severity': self.ALERT_SEVERITY.get(endpoint_name, 'medium'),
                'alert_timestamp': current_time,
                'system_id': system_info.get('id', 'unknown'),
                'system_wwn': system_info.get('wwn', 'unknown'),
                'system_name': system_info.get('name', 'unknown'),
                
                # Event categorization
                'event_category': 'system_event',
                'source': 'eseries_api',
                
                # For InfluxDB measurement routing
                'measurement_type': 'alert',
            }
            
            enriched_records.append(enriched_record)
        
        # Optional: Generate Grafana annotation
        if self.enable_grafana_annotations:
            self._create_grafana_annotation(endpoint_name, raw_data, system_info)
        
        logger.info(f"Enriched {len(enriched_records)} {endpoint_name} events for system {system_info.get('name')}")
        return enriched_records
    
    def _is_duplicate_event(self, endpoint_name: str, raw_data: List[Dict[str, Any]]) -> bool:
        """
        Check if this event data is a duplicate of recent data
        
        Args:
            endpoint_name: Name of the event endpoint
            raw_data: Raw event data to check
            
        Returns:
            True if this is a duplicate within the deduplication window
        """
        # Generate checksum for the event data
        data_str = json.dumps(raw_data, sort_keys=True)
        checksum = hashlib.md5(data_str.encode('utf-8')).hexdigest()
        
        current_time = time.time()
        
        # Clean up old entries beyond the deduplication window
        cutoff_time = current_time - (self.dedup_window_minutes * 60)
        if endpoint_name in self._recent_events:
            self._recent_events[endpoint_name] = {
                cs: ts for cs, ts in self._recent_events[endpoint_name].items() 
                if ts > cutoff_time
            }
        
        # Check if we've seen this checksum recently
        if endpoint_name in self._recent_events:
            if checksum in self._recent_events[endpoint_name]:
                return True  # Duplicate found
        
        # Store this checksum with current timestamp
        if endpoint_name not in self._recent_events:
            self._recent_events[endpoint_name] = {}
        self._recent_events[endpoint_name][checksum] = current_time
        
        return False
    
    def _create_grafana_annotation(self, endpoint_name: str, raw_data: List[Dict[str, Any]], 
                                  system_info: Dict[str, Any]):
        """
        Create Grafana annotation for this event (if enabled)
        
        Args:
            endpoint_name: Name of the event endpoint
            raw_data: Raw event data
            system_info: System information
        """
        # This would integrate with Grafana API
        # Implementation depends on your Grafana setup
        annotation = {
            'time': int(time.time() * 1000),  # Grafana expects milliseconds
            'text': f"Event: {endpoint_name} - {len(raw_data)} items on {system_info.get('name')}",
            'tags': ['eseries-alert', endpoint_name, system_info.get('name', 'unknown')],
            'severity': self.ALERT_SEVERITY.get(endpoint_name, 'medium')
        }
        
        logger.debug(f"Grafana annotation created: {annotation}")
        # TODO: Implement Grafana API integration
        # post_to_grafana_annotations(annotation)
    
    def get_alert_summary(self) -> Dict[str, Any]:
        """
        Get summary of recent alert activity
        
        Returns:
            Dictionary with alert statistics
        """
        total_endpoints = len(self._recent_events)
        total_recent_events = sum(len(checksums) for checksums in self._recent_events.values())
        
        return {
            'total_alert_endpoints': total_endpoints,
            'total_recent_events': total_recent_events,
            'deduplication_enabled': self.enable_deduplication,
            'dedup_window_minutes': self.dedup_window_minutes
        }