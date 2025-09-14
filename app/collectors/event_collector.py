#!/usr/bin/env python3
"""
Event Collector for E-Series Performance Analyzer

Handles collection of dynamic status, jobs, alerts, and transient events
that don't fit into performance metrics or static configuration.

Event data characteristics:
- Frequently empty (returns [])  
- Should be written immediately when data exists
- Not cached for enrichment
- Not typically exported via Prometheus
- Includes: system events, job status, lockdown status, etc.
"""

import logging
from typing import Dict, List, Optional, Any

from app.collectors.collector import ESeriesCollector
from app.config.endpoint_categories import EndpointCategory, get_endpoints_by_category
from app.schema.models import BaseModel

class EventCollector:
    """Collects event/status data from API with immediate write behavior"""
    
    def __init__(self, session=None, headers=None, api_endpoints=None, from_json=False, 
                 json_directory=None, base_url=None, system_id='1'):
        self.session = session
        self.headers = headers
        self.api_endpoints = api_endpoints
        self.logger = logging.getLogger(__name__)
        
        # Initialize ESeriesCollector for actual data collection
        collector_config = {
            'from_json': from_json,
            'json_directory': json_directory or './json_data',
            'base_url': base_url,
            'system_id': system_id,
            'session': session,
            'headers': headers or {'Accept': 'application/json'}
        }
        self.eseries_collector = ESeriesCollector(collector_config)
        
        # Get all event endpoints from categorization
        self.event_endpoints = get_endpoints_by_category(EndpointCategory.EVENTS)
        
    def collect_events(self, sys_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect all event/status data that has active content
        
        Args:
            sys_info: System information dictionary
            
        Returns:
            Dictionary with collection results
        """
        collected_events = {}
        empty_responses = []
        errors = []
        
        self.logger.info(f"Checking {len(self.event_endpoints)} event endpoints")
        
        for endpoint_name in self.event_endpoints:
            try:
                # Attempt to collect data for this event endpoint
                data = self._collect_event_endpoint(endpoint_name)
                
                if data and len(data) > 0:
                    # Only store non-empty responses
                    collected_events[endpoint_name] = data
                    self.logger.info(f"Event data found for {endpoint_name}: {len(data)} items")
                else:
                    # Track empty responses for logging
                    empty_responses.append(endpoint_name)
                    
            except Exception as e:
                self.logger.error(f"Failed to collect event endpoint {endpoint_name}: {e}")
                errors.append({'endpoint': endpoint_name, 'error': str(e)})
                
        self.logger.info(f"Event collection complete: {len(collected_events)} active, "
                        f"{len(empty_responses)} empty, {len(errors)} errors")
        
        return {
            "status": "success" if not errors else "partial_success",
            "active_events": collected_events,
            "empty_endpoints": empty_responses,
            "errors": errors,
            "total_active": len(collected_events),
            "total_checked": len(self.event_endpoints)
        }
    
    def _collect_event_endpoint(self, endpoint_name: str) -> List[Any]:
        """
        Collect data from a specific event endpoint
        
        Args:
            endpoint_name: Name of the event endpoint
            
        Returns:
            List of data items (may be empty)
        """
        try:
            if self.eseries_collector.from_json:
                # In JSON mode, try to find matching files
                pattern = f"*{endpoint_name.replace('_', '*')}*"
                return self.eseries_collector.collect_from_json_directory(
                    directory=self.eseries_collector.json_directory,
                    pattern=pattern,
                    model_class=BaseModel,  # Generic model for event data
                    sort_by='timestamp'
                )
            else:
                # In live API mode, check if endpoint requires ID dependency
                if endpoint_name in self.eseries_collector.ID_DEPENDENCIES:
                    return self.eseries_collector._collect_with_id_dependency(endpoint_name, BaseModel)
                else:
                    return self.eseries_collector._collect_from_api(endpoint_name, BaseModel)
                
        except Exception as e:
            self.logger.error(f"Error collecting {endpoint_name}: {e}")
            return []
    
    def collect_specific_events(self, event_types: List[str], sys_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect specific types of events only
        
        Args:
            event_types: List of event endpoint names to collect
            sys_info: System information dictionary
            
        Returns:
            Dictionary with collection results for specified events
        """
        collected_events = {}
        
        for event_type in event_types:
            if event_type not in self.event_endpoints:
                self.logger.warning(f"Unknown event type: {event_type}")
                continue
                
            try:
                data = self._collect_event_endpoint(event_type)
                if data and len(data) > 0:
                    collected_events[event_type] = data
                    self.logger.info(f"Collected {len(data)} items for {event_type}")
            except Exception as e:
                self.logger.error(f"Failed to collect {event_type}: {e}")
        
        return {
            "status": "success",
            "events": collected_events,
            "requested": event_types,
            "collected": len(collected_events)
        }
    
    def collect_lockdown_status(self, sys_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect system lockdown status (high priority event)
        
        Args:
            sys_info: System information dictionary
            
        Returns:
            Dictionary with lockdown status or empty if not locked
        """
        try:
            data = self._collect_event_endpoint('lockdown_status')
            
            # Check if system is actually in lockdown by examining isLockdown field
            if data and len(data) > 0:
                lockdown_info = data[0] if isinstance(data, list) else data
                
                # Check for actual lockdown condition
                is_locked_down = lockdown_info.get('isLockdown', False)
                
                if is_locked_down:
                    self.logger.warning(f"System lockdown detected: {lockdown_info}")
                    return {
                        "status": "lockdown",
                        "lockdown_data": [lockdown_info],
                        "alert_level": "critical",
                        "lockdown_type": lockdown_info.get('lockdownType', 'unknown'),
                        "lockdown_clearable": lockdown_info.get('lockdownClearable', False),
                        "limited_access_state": lockdown_info.get('limitedAccessState', 'unknown')
                    }
                else:
                    self.logger.debug(f"System not in lockdown: isLockdown={is_locked_down}")
                    return {
                        "status": "normal",
                        "lockdown_data": [],
                        "alert_level": "none"
                    }
            else:
                self.logger.warning("No lockdown status data received")
                return {
                    "status": "unknown",
                    "lockdown_data": [],
                    "alert_level": "warning"
                }
                
        except Exception as e:
            error_str = str(e).lower()
            
            # Check if the error suggests system lockdown (authentication/access issues)
            lockdown_indicators = [
                '401',  # Unauthorized
                '403',  # Forbidden  
                'unauthorized',
                'authentication failed',
                'access denied',
                'connection refused',
                'connection timeout'
            ]
            
            if any(indicator in error_str for indicator in lockdown_indicators):
                self.logger.warning(f"Lockdown status check failed with access error - possible system lockdown: {e}")
                return {
                    "status": "possible_lockdown",
                    "lockdown_data": [],
                    "alert_level": "critical", 
                    "error": str(e),
                    "inferred_from_error": True,
                    "lockdown_type": "inferred_from_api_failure"
                }
            else:
                self.logger.error(f"Failed to check lockdown status: {e}")
                return {
                    "status": "error",
                    "error": str(e),
                    "alert_level": "unknown"
                }
    
    def collect_job_status(self, sys_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Collect status of all background jobs
        
        Args:
            sys_info: System information dictionary
            
        Returns:
            Dictionary with active job information
        """
        job_endpoints = [
            'volume_parity_check_status',
            'volume_parity_job_check_errors', 
            'data_parity_scan_job_status',
            'volume_copy_jobs',
            'volume_copy_job_progress',
            'drives_erase_progress',
            'storage_pools_action_progress'
        ]
        
        return self.collect_specific_events(job_endpoints, sys_info)
    
    def get_event_endpoints(self) -> List[str]:
        """
        Get list of all available event endpoints
        
        Returns:
            List of event endpoint names
        """
        return sorted(list(self.event_endpoints))
    
    def is_event_endpoint(self, endpoint_name: str) -> bool:
        """
        Check if an endpoint is categorized as an event endpoint
        
        Args:
            endpoint_name: Name of the endpoint to check
            
        Returns:
            True if it's an event endpoint
        """
        return endpoint_name in self.event_endpoints