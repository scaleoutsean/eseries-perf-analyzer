"""
Writer factory for E-Series Performance Analyzer.
"""

import logging
from typing import Dict, Any, Optional

from app.writer.base import Writer
from app.writer.influxdb_writer import InfluxDBWriter
from app.writer.json_writer import JsonWriter
from app.writer.prometheus_writer import PrometheusWriter
from app.writer.multi_writer import MultiWriter

# Initialize logger
LOG = logging.getLogger(__name__)

class WriterFactory:
    """
    Factory for creating writer instances based on configuration.
    """
    
    @staticmethod
    def create_writer(args, influxdb_url=None, influxdb_database=None, influxdb_token=None, system_id="1") -> Writer:
        """
        Create a writer based on command line arguments.
        
        Args:
            args: Command line arguments
            influxdb_url: InfluxDB server URL
            influxdb_database: InfluxDB database name
            influxdb_token: InfluxDB authentication token
            
        Returns:
            Appropriate Writer instance
        """
        # JSON output takes precedence for debugging/replay
        if hasattr(args, 'toJson') and args.toJson:
            LOG.info(f"Creating JSON writer with output directory: {args.toJson}")
            return JsonWriter(args.toJson, system_id)
        
        # Check for output preference (influxdb, prometheus, both)
        output_choice = getattr(args, 'output', 'influxdb')
        
        if output_choice == 'prometheus':
            LOG.info("Creating Prometheus writer")
            prometheus_port = getattr(args, 'prometheus_port', 8000)
            return PrometheusWriter(port=prometheus_port)
            
        elif output_choice == 'influxdb':
            # InfluxDB output
            if influxdb_url and influxdb_database and influxdb_token:
                LOG.info(f"Creating InfluxDB writer with URL: {influxdb_url}, database: {influxdb_database}")
                config = {
                    'influxdb_url': influxdb_url,
                    'influxdb_database': influxdb_database,
                    'influxdb_token': influxdb_token,
                    'tls_ca': getattr(args, 'tlsCa', None),
                    'tls_validation': getattr(args, 'tls_validation', 'strict')
                }
                return InfluxDBWriter(config)
            else:
                LOG.error("InfluxDB output selected but missing connection parameters")
                # Fall back to stub writer for testing
                return _create_stub_writer()
                
        elif output_choice == 'both':
            # Create multi-writer that supports both InfluxDB and Prometheus
            LOG.info("Creating MultiWriter for both InfluxDB and Prometheus output")
            writers = []
            
            # Add InfluxDB writer if configured
            if influxdb_url and influxdb_database and influxdb_token:
                config = {
                    'influxdb_url': influxdb_url,
                    'influxdb_database': influxdb_database,
                    'influxdb_token': influxdb_token,
                    'tls_ca': getattr(args, 'tlsCa', None),
                    'tls_validation': getattr(args, 'tls_validation', 'strict')
                }
                influxdb_writer = InfluxDBWriter(config)
                writers.append(influxdb_writer)
                LOG.info("✅ Added InfluxDB writer to MultiWriter")
            else:
                LOG.error("InfluxDB configuration missing for 'both' output")
            
            # Add Prometheus writer
            prometheus_port = getattr(args, 'prometheus_port', 8000)
            prometheus_writer = PrometheusWriter(port=prometheus_port)
            writers.append(prometheus_writer)
            LOG.info("✅ Added Prometheus writer to MultiWriter")
            
            if writers:
                return MultiWriter(writers)
            else:
                LOG.error("No writers configured for 'both' output, falling back to stub")
                return _create_stub_writer()
        
        # Fall back to stub writer for testing if nothing else works
        LOG.warning("No valid output destination configured, using stub writer")
        return _create_stub_writer()

def _create_stub_writer() -> Writer:
    """Create a stub writer for testing purposes."""
    from app.writer.base import Writer
    
    class StubWriter(Writer):
        def write(self, data) -> bool:
            LOG.info(f"Stub writer: Would write data with {len(data)} measurements")
            return True
    
    return StubWriter()