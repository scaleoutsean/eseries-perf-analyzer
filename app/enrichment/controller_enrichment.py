"""
Controller Performance Enrichment

Enriches controller performance metrics with:
- controller_id: Controller identifier (from statistics data)
- active: Controller active status from configuration
- model_name: Controller model from configuration  
- status: Controller status from configuration
- cache_memory_size: Controller cache size from configuration
- flash_cache_memory_size: Controller flash cache size from configuration
"""

from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class ControllerEnrichmentProcessor:
    """Processes controller performance enrichment with configuration data"""
    
    def __init__(self):
        self.controller_lookup = {}     # controller_id -> controller_config
        self.interface_lookup = {}      # interface_ref -> interface enrichment data
        
    def load_configuration_data(self, controllers: List[Dict]):
        """Load controller configuration data needed for enrichment"""
        
        # Build lookup tables
        self.controller_lookup = {c['id']: c for c in controllers}
        # Also index by controllerRef in case they differ
        for controller in controllers:
            if controller.get('controllerRef') and controller['controllerRef'] != controller['id']:
                self.controller_lookup[controller['controllerRef']] = controller
        
        # Build interface reference mapping for interface statistics enrichment
        self.interface_lookup = {}
        for controller in controllers:
            controller_id = controller.get('id')
            
            # Process host interfaces (IB, iSCSI, FC, SAS, etc.)
            for host_interface in controller.get('hostInterfaces', []):
                interface_type = host_interface.get('interfaceType')
                interface_ref = None
                
                # Extract interface reference based on type
                if interface_type and interface_type in host_interface:
                    interface_data = host_interface[interface_type]
                    interface_ref = interface_data.get('interfaceRef')
                    
                if interface_ref:
                    # Determine controller label (A/B logic - customize as needed)
                    # This is a simplified example - you may need different logic
                    controller_label = self._get_controller_label(controller)
                    
                    self.interface_lookup[interface_ref] = {
                        'controller_id': controller_id,
                        'controller_ref': controller.get('controllerRef', controller_id),
                        'controller_label': controller_label,
                        'controller_active': controller.get('active'),
                        'controller_model': controller.get('modelName'),
                        'interface_type': interface_type,
                        'interface_data': interface_data  # Full interface config for detailed enrichment
                    }
            
            # Process network interfaces (management - typically Ethernet)
            for net_interface in controller.get('netInterfaces', []):
                interface_type = net_interface.get('interfaceType')
                if interface_type and interface_type in net_interface:
                    interface_data = net_interface[interface_type]
                    interface_ref = interface_data.get('interfaceRef')
                    
                    if interface_ref:
                        controller_label = self._get_controller_label(controller)
                        
                        self.interface_lookup[interface_ref] = {
                            'controller_id': controller_id,
                            'controller_ref': controller.get('controllerRef', controller_id),
                            'controller_label': controller_label,
                            'controller_active': controller.get('active'),
                            'controller_model': controller.get('modelName'),
                            'interface_type': interface_type,
                            'interface_data': interface_data,
                            'is_management': True  # Flag for management vs host interfaces
                        }
            
        logger.info(f"Loaded controller enrichment data: {len(controllers)} controllers, {len(self.interface_lookup)} interface references")
    
    def _get_controller_label(self, controller: Dict) -> str:
        """Get controller label (A/B) for enrichment - customize logic as needed"""
        # Simple example: use controller ID or active status to determine label
        # You may need to customize this based on your specific E-Series configuration
        controller_id = controller.get('id', '')
        
        # Example logic - customize for your environment
        if controller_id.endswith('1'):
            return 'A'
        elif controller_id.endswith('2'):
            return 'B'
        else:
            # Fallback - could use active status, position, or other logic
            return 'A' if controller.get('active', True) else 'B'
    
    def enrich_interface_statistics(self, interface_stats: Dict) -> Dict:
        """Enrich interface statistics with controller and interface configuration data"""
        
        # Get interface ID from statistics
        interface_id = interface_stats.get('interfaceId')
        if not interface_id:
            logger.warning("Interface statistics record missing interfaceId")
            return interface_stats
        
        # Get interface enrichment data
        interface_enrichment = self.interface_lookup.get(interface_id)
        if not interface_enrichment:
            logger.warning(f"Interface {interface_id} not found in configuration")
            return interface_stats
        
        # Start with original statistics
        enriched = interface_stats.copy()
        
        # Add controller tags
        enriched['controller_id'] = interface_enrichment['controller_id']
        enriched['controller_label'] = interface_enrichment['controller_label']
        enriched['controller_active'] = interface_enrichment['controller_active']
        enriched['controller_model'] = interface_enrichment['controller_model']
        
        # Add interface tags
        enriched['interface_type'] = interface_enrichment['interface_type']
        enriched['is_management_interface'] = interface_enrichment.get('is_management', False)
        
        # Add interface-type specific enrichment
        interface_data = interface_enrichment.get('interface_data', {})
        interface_type = interface_enrichment['interface_type']
        
        if interface_type == 'ib':
            # InfiniBand specific enrichment
            enriched['link_state'] = interface_data.get('linkState')
            enriched['current_speed'] = interface_data.get('currentSpeed')
            enriched['link_width'] = interface_data.get('currentLinkWidth')
            enriched['port_state'] = interface_data.get('portState')
            enriched['channel'] = interface_data.get('channel')
            enriched['global_identifier'] = interface_data.get('globalIdentifier')
            enriched['mtu'] = interface_data.get('maximumTransmissionUnit')
        elif interface_type == 'iscsi':
            # iSCSI specific enrichment
            enriched['link_status'] = interface_data.get('linkStatus')
            enriched['current_speed'] = interface_data.get('currentSpeed')
            enriched['channel'] = interface_data.get('channel')
            enriched['ipv4_address'] = interface_data.get('ipv4Address')
            enriched['ipv4_enabled'] = interface_data.get('ipv4Enabled')
            enriched['tcp_port'] = interface_data.get('tcpListenPort')
        elif interface_type == 'ethernet':
            # Ethernet specific enrichment (management interfaces)
            enriched['link_status'] = interface_data.get('linkStatus')
            enriched['current_speed'] = interface_data.get('currentSpeed')
            enriched['interface_name'] = interface_data.get('interfaceName')
            enriched['mac_address'] = interface_data.get('macAddr')
            enriched['ipv4_address'] = interface_data.get('ipv4Address')
            enriched['full_duplex'] = interface_data.get('fullDuplex')
        
        return enriched
    
    def enrich_interface_statistics_batch(self, interface_statistics: List[Dict]) -> List[Dict]:
        """Enrich a batch of interface statistics"""
        
        enriched_results = []
        for stats_record in interface_statistics:
            enriched = self.enrich_interface_statistics(stats_record)
            enriched_results.append(enriched)
        
        logger.info(f"Enriched {len(enriched_results)} interface statistics records")
        return enriched_results
    
    def enrich_controller_performance(self, controller_performance: Dict) -> Dict:
        """Enrich a single controller performance measurement with configuration data"""
        
        # Get controller ID from statistics (try both fields)
        controller_id = controller_performance.get('controllerId') or controller_performance.get('sourceController')
        if not controller_id:
            logger.warning("Controller performance record missing controllerId/sourceController")
            return controller_performance
            
        # Get controller configuration
        controller_config = self.controller_lookup.get(controller_id)
        if not controller_config:
            logger.warning(f"Controller {controller_id} not found in configuration")
            return controller_performance
            
        # Start with original performance data
        enriched = controller_performance.copy()
        
        # Add tags
        enriched['controller_id'] = controller_id
        enriched['active'] = controller_config.get('active', False)
        enriched['model_name'] = controller_config.get('modelName', 'unknown')
        enriched['status'] = controller_config.get('status', 'unknown')
        
        # Add fields (additional data points)
        enriched['cache_memory_size'] = controller_config.get('cacheMemorySize', 0)
        enriched['flash_cache_memory_size'] = controller_config.get('flashCacheMemorySize', 0)
        
        # Optional: Add other useful controller config data as fields
        enriched['manufacturer'] = controller_config.get('manufacturer', 'unknown')
        enriched['serial_number'] = controller_config.get('serialNumber', 'unknown')
        enriched['part_number'] = controller_config.get('partNumber', 'unknown')
        
        return enriched
    
    def enrich_controller_performance_batch(self, controller_performances: List[Dict]) -> List[Dict]:
        """Enrich a batch of controller performance measurements"""
        
        enriched_results = []
        for perf_record in controller_performances:
            enriched = self.enrich_controller_performance(perf_record)
            enriched_results.append(enriched)
            
        logger.info(f"Enriched {len(enriched_results)} controller performance records")
        return enriched_results
    
    def process(self, controller_stats_response: Dict) -> Dict:
        """
        Process and enrich controller statistics response with special handling for list format
        
        Handles cases where API returns:
        - [] (empty list) - returns empty statistics
        - 1-2 items - processes all items
        - >2 items - sorts by observedTimeInMS descending and takes 2 most recent
        
        Format: {'statistics': [...], 'tokenId': '...'}
        """
        
        if not isinstance(controller_stats_response, dict) or 'statistics' not in controller_stats_response:
            logger.warning("Invalid controller statistics response format")
            return controller_stats_response
            
        statistics = controller_stats_response.get('statistics', [])
        
        # Handle empty list case
        if not statistics:
            logger.info("Controller statistics response contains no data")
            enriched_response = controller_stats_response.copy()
            enriched_response['statistics'] = []
            return enriched_response
        
        # Handle case with more than 2 items - sort by observedTimeInMS descending and take 2 most recent
        if len(statistics) > 2:
            logger.info(f"Controller statistics has {len(statistics)} items, sorting by observedTimeInMS and taking 2 most recent")
            # Sort by observedTimeInMS in descending order (most recent first)
            try:
                statistics_sorted = sorted(
                    statistics, 
                    key=lambda x: int(x.get('observedTimeInMS', 0)), 
                    reverse=True
                )
                statistics = statistics_sorted[:2]  # Take 2 most recent
                logger.info(f"Selected {len(statistics)} most recent controller statistics")
            except (ValueError, TypeError) as e:
                logger.warning(f"Error sorting controller statistics by observedTimeInMS: {e}")
                # If sorting fails, just take first 2 items
                statistics = statistics[:2]
        
        # Enrich the statistics array
        enriched_statistics = self.enrich_controller_performance_batch(statistics)
        
        # Return enriched response
        enriched_response = controller_stats_response.copy()
        enriched_response['statistics'] = enriched_statistics
        
        logger.info(f"Processed controller statistics response with {len(enriched_statistics)} controller records")
        return enriched_response
    
    def enrich_controller_statistics_response(self, controller_stats_response: Dict) -> Dict:
        """
        Legacy method - use process() instead
        Enrich the entire controller statistics response (which contains a statistics array)
        This handles the specific format: {'statistics': [...], 'tokenId': '...'}
        """
        return self.process(controller_stats_response)