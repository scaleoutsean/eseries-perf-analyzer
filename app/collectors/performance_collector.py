import logging
from typing import Dict, List, Any

from app.collectors.collector import ESeriesCollector
from app.schema.models import (
    AnalysedVolumeStatistics, AnalysedDriveStatistics, 
    AnalysedSystemStatistics, AnalysedInterfaceStatistics,
    AnalyzedControllerStatistics
)

class PerformanceCollector:
    """Collects performance data from API"""
    
    def __init__(self, session=None, headers=None, api_endpoints=None, from_json=False, json_directory=None, base_url=None, system_id='1'):
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
    
    def collect_metrics(self, sys_info):
        """Collect performance metrics."""
        try:
            # Collect all performance metrics
            performance_data = {}
            
            # Volume performance
            volume_perf = self.eseries_collector.collect_performance_data(
                AnalysedVolumeStatistics, 'analysed-volume-statistics'
            )
            if volume_perf:
                performance_data['volume_performance'] = volume_perf
                self.logger.info(f"Collected {len(volume_perf)} volume performance records")
            
            # Drive performance
            drive_perf = self.eseries_collector.collect_performance_data(
                AnalysedDriveStatistics, 'analysed-drive-statistics'
            )
            if drive_perf:
                performance_data['drive_performance'] = drive_perf
                self.logger.info(f"Collected {len(drive_perf)} drive performance records")
            
            # Controller performance
            controller_perf = self.eseries_collector.collect_performance_data(
                AnalyzedControllerStatistics, 'analysed-controller-statistics'
            )
            if controller_perf:
                performance_data['controller_performance'] = controller_perf
                self.logger.info(f"Collected {len(controller_perf)} controller performance records")
            
            # System performance
            system_perf = self.eseries_collector.collect_performance_data(
                AnalysedSystemStatistics, 'analysed-system-statistics'
            )
            if system_perf:
                performance_data['system_performance'] = system_perf
                self.logger.info(f"Collected {len(system_perf)} system performance records")
            
            # Interface performance
            interface_perf = self.eseries_collector.collect_performance_data(
                AnalysedInterfaceStatistics, 'analysed-interface-statistics'
            )
            if interface_perf:
                performance_data['interface_performance'] = interface_perf
                self.logger.info(f"Collected {len(interface_perf)} interface performance records")
            
            return {
                "status": "success",
                "performance_data": performance_data,
                "total_records": sum(len(data) for data in performance_data.values())
            }
            
        except Exception as e:
            self.logger.error(f"Error collecting performance metrics: {e}")
            return {"status": "error", "error": str(e)}