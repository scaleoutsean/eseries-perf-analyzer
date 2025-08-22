#!/usr/bin/env python3
"""
Grafana Initialization Script
Replaces the complex Ansible workflow with a simple Python script
that imports dashboards and configures Grafana via API
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from grafana_client import GrafanaApi
from grafana_client.client import GrafanaClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GrafanaInitializer:
    def __init__(self):
        self.grafana_url = os.getenv('GRAFANA_URL', 'http://grafana:3000')
        self.grafana_user = os.getenv('GRAFANA_USER', 'admin')
        self.grafana_password = os.getenv('GRAFANA_PASSWORD', 'admin')
        self.dashboards_dir = Path('/dashboards')
        self.max_retries = 30
        self.retry_delay = 2
        
        # Parse URL components
        if '://' in self.grafana_url:
            protocol, rest = self.grafana_url.split('://', 1)
            if ':' in rest:
                host, port = rest.split(':', 1)
                port = int(port.split('/')[0])  # Remove any path
            else:
                host = rest.split('/')[0]
                port = 3000
        else:
            protocol = 'http'
            host = 'grafana'
            port = 3000
            
        self.grafana = GrafanaApi(
            auth=(self.grafana_user, self.grafana_password),
            host=host,
            port=port,
            protocol=protocol
        )
        
    def wait_for_grafana(self):
        """Wait for Grafana to be ready"""
        logger.info(f"Waiting for Grafana at {self.grafana_url}")
        
        for attempt in range(self.max_retries):
            try:
                # Try to list datasources as a simple health check
                datasources = self.grafana.datasource.list_datasources()
                logger.info("Grafana is ready!")
                return True
            except Exception as e:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}: Grafana not ready yet ({e})")
                time.sleep(self.retry_delay)
                
        logger.error("Grafana failed to become ready after maximum retries")
        return False
        
    def create_influxdb_datasource(self):
        """Create InfluxDB datasource if it doesn't exist"""
        logger.info("Setting up InfluxDB datasource")
        
        try:
            # Check if datasource already exists
            datasources = self.grafana.datasource.list_datasources()
            for ds in datasources:
                if ds.get('name') == 'EPA':
                    logger.info("EPA datasource already exists")
                    return True
                    
            # Create InfluxDB datasource
            datasource_config = {
                "name": "EPA",
                "type": "influxdb",
                "url": "http://influxdb:8086",
                "access": "proxy",
                "database": "eseries",
                "isDefault": True,
                "jsonData": {
                    "timeInterval": "10s"
                }
            }
            
            result = self.grafana.datasource.create_datasource(datasource_config)
            logger.info(f"Created EPA datasource: {result}")
            return True
            
        except GrafanaClientError as e:
            logger.error(f"Failed to create InfluxDB datasource: {e}")
            return False
            
    def import_dashboards(self):
        """Import all JSON dashboards from the dashboards directory"""
        if not self.dashboards_dir.exists():
            logger.warning(f"Dashboards directory {self.dashboards_dir} does not exist")
            return True
            
        dashboard_files = list(self.dashboards_dir.glob('*.json'))
        if not dashboard_files:
            logger.info("No dashboard files found")
            return True
            
        logger.info(f"Found {len(dashboard_files)} dashboard files")
        
        success_count = 0
        for dashboard_file in dashboard_files:
            try:
                logger.info(f"Importing dashboard: {dashboard_file.name}")
                
                with open(dashboard_file, 'r') as f:
                    dashboard_json = json.load(f)
                
                # Prepare dashboard for import
                dashboard_payload = {
                    'dashboard': dashboard_json,
                    'overwrite': True,
                    'inputs': [],
                    'folderId': 0
                }
                
                # Remove id and uid if present (let Grafana assign new ones)
                if 'id' in dashboard_payload['dashboard']:
                    del dashboard_payload['dashboard']['id']
                if 'uid' in dashboard_payload['dashboard']:
                    del dashboard_payload['dashboard']['uid']
                
                result = self.grafana.dashboard.update_dashboard(dashboard_payload)
                logger.info(f"Successfully imported {dashboard_file.name}: {result.get('slug', 'unknown')}")
                success_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import {dashboard_file.name}: {e}")
                
        logger.info(f"Successfully imported {success_count}/{len(dashboard_files)} dashboards")
        return success_count > 0
        
    def run(self):
        """Main initialization process"""
        logger.info("Starting Grafana initialization")
        
        # Wait for Grafana to be ready
        if not self.wait_for_grafana():
            logger.error("Grafana initialization failed - service not ready")
            sys.exit(1)
            
        # Set up datasource
        if not self.create_influxdb_datasource():
            logger.error("Failed to create InfluxDB datasource")
            sys.exit(1)
            
        # Import dashboards
        if not self.import_dashboards():
            logger.warning("Dashboard import had issues, but continuing")
            
        logger.info("Grafana initialization completed successfully")
        
if __name__ == "__main__":
    initializer = GrafanaInitializer()
    initializer.run()
