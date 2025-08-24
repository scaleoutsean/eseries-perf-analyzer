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
        
        # Handle multiple databases
        db_list_str = os.getenv('DB_LIST', '').strip()
        if db_list_str:
            # Parse comma-separated list: "EPA1,CUSTOM" -> ["EPA1", "CUSTOM"]
            self.database_names = [db.strip() for db in db_list_str.split(',') if db.strip()]
            logger.info(f"Multiple databases configured: {self.database_names}")
        else:
            # Single database mode (backward compatibility)
            single_db = os.getenv('DB_NAME', 'eseries')
            self.database_names = [single_db]
            logger.info(f"Single database mode: {single_db}")
            
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
        
    def create_influxdb_datasources(self):
        """Create InfluxDB datasources for all configured databases"""
        logger.info("Setting up InfluxDB datasources")
        
        try:
            # Check existing datasources
            datasources = self.grafana.datasource.list_datasources()
            existing_names = {ds.get('name') for ds in datasources}
            
            created_count = 0
            for i, db_name in enumerate(self.database_names):
                # Determine datasource name
                if len(self.database_names) == 1:
                    # Single database: use "EPA" for backward compatibility
                    datasource_name = "EPA"
                else:
                    # Multiple databases: use database name as datasource name
                    datasource_name = db_name
                
                if datasource_name in existing_names:
                    logger.info(f"Datasource '{datasource_name}' already exists")
                    continue
                    
                # Create InfluxDB datasource
                datasource_config = {
                    "name": datasource_name,
                    "type": "influxdb",
                    "url": "http://influxdb:8086",
                    "access": "proxy",
                    "database": db_name,
                    "isDefault": i == 0,  # First datasource is default
                    "jsonData": {
                        "timeInterval": "10s"
                    }
                }
                
                result = self.grafana.datasource.create_datasource(datasource_config)
                logger.info(f"Created datasource '{datasource_name}' -> database '{db_name}': {result}")
                created_count += 1
                
            logger.info(f"Created {created_count} new datasources")
            return True
            
        except GrafanaClientError as e:
            logger.error(f"Failed to create InfluxDB datasources: {e}")
            return False
            
    def create_epa_folder(self):
        """Create EPA folder for organizing dashboards"""
        logger.info("Creating EPA folder")
        
        try:
            # Check if EPA folder already exists
            folders = self.grafana.folder.get_all_folders()
            for folder in folders:
                if folder.get('title') == 'EPA':
                    folder_id = folder.get('id')
                    folder_uid = folder.get('uid')
                    logger.info(f"EPA folder already exists with ID: {folder_id}, UID: {folder_uid}")
                    return folder_id
            
            # Create EPA folder
            folder_config = {
                "title": "EPA",
                "uid": "epa-folder"  # Explicit UID for consistency
            }
            
            result = self.grafana.folder.create_folder(**folder_config)
            folder_id = result.get('id')
            folder_uid = result.get('uid')
            logger.info(f"Created EPA folder with ID: {folder_id}, UID: {folder_uid}")
            return folder_id
            
        except GrafanaClientError as e:
            logger.error(f"Failed to create EPA folder: {e}")
            return None
            
    def _fix_datasource_references(self, dashboard_json):
        """Fix datasource references in dashboard JSON to point to EPA datasource"""
        import json
        
        # Convert to string to do global replacements
        dashboard_str = json.dumps(dashboard_json)
        
        # Replace template variables
        dashboard_str = dashboard_str.replace('${DS_EPA}', 'EPA')
        dashboard_str = dashboard_str.replace('${__datasource}', 'EPA')
        
        # Convert back to dict
        fixed_dashboard = json.loads(dashboard_str)
        
        # Also ensure templating section has correct datasource
        if 'templating' in fixed_dashboard:
            if 'list' in fixed_dashboard['templating']:
                for template in fixed_dashboard['templating']['list']:
                    if template.get('type') == 'datasource':
                        template['current'] = {'text': 'EPA', 'value': 'EPA'}
                        template['options'] = [{'text': 'EPA', 'value': 'EPA', 'selected': True}]
        
        # Update the original dashboard_json in place
        dashboard_json.clear()
        dashboard_json.update(fixed_dashboard)
        
    def import_dashboards(self, folder_id=None):
        """Import all JSON dashboards from the dashboards directory"""
        if not self.dashboards_dir.exists():
            logger.warning(f"Dashboards directory {self.dashboards_dir} does not exist")
            return 0, 0
            
        dashboard_files = list(self.dashboards_dir.glob('*.json'))
        if not dashboard_files:
            logger.info("No dashboard files found")
            return 0, 0
            
        logger.info(f"Found {len(dashboard_files)} dashboard files")
        
        success_count = 0
        for dashboard_file in dashboard_files:
            try:
                logger.info(f"Importing dashboard: {dashboard_file.name}")
                
                with open(dashboard_file, 'r') as f:
                    dashboard_data = json.load(f)
                
                # Extract the actual dashboard object if it's wrapped
                if 'dashboard' in dashboard_data:
                    dashboard_json = dashboard_data['dashboard']
                else:
                    dashboard_json = dashboard_data
                
                # Extract title from filename (remove .json extension)
                dashboard_title = dashboard_file.stem
                
                # Set the title in the dashboard JSON
                dashboard_json['title'] = dashboard_title
                
                # Remove id and uid if present (let Grafana assign new ones)
                if 'id' in dashboard_json:
                    del dashboard_json['id']
                if 'uid' in dashboard_json:
                    del dashboard_json['uid']
                
                # Fix datasource references - replace template variables and ensure EPA datasource
                self._fix_datasource_references(dashboard_json)
                
                # Prepare dashboard payload (title is now in dashboard_json)
                dashboard_payload = {
                    'dashboard': dashboard_json,
                    'overwrite': True,
                    'message': f"Imported {dashboard_title} via grafana-init",
                    'allowUiUpdates': True  # Allow editing in Grafana UI
                }
                
                # Add folder ID if provided
                if folder_id:
                    dashboard_payload['folderId'] = folder_id
                
                result = self.grafana.dashboard.update_dashboard(dashboard_payload)
                logger.info(f"Successfully imported {dashboard_file.name}: {result.get('slug', 'unknown')}")
                success_count += 1
                
            except Exception as e:
                logger.error(f"Failed to import {dashboard_file.name}: {e}")
                
        logger.info(f"Successfully imported {success_count}/{len(dashboard_files)} dashboards")
        return success_count, len(dashboard_files)
        
    def verify_epa_setup(self, expected_dashboards=4):
        """Verify that EPA folder exists and contains expected number of dashboards"""
        logger.info("Verifying EPA setup...")
        
        try:
            # Check if EPA folder exists
            folders = self.grafana.folder.get_all_folders()
            epa_folder = None
            for folder in folders:
                if folder.get('title') == 'EPA':
                    epa_folder = folder
                    break
            
            if not epa_folder:
                logger.warning("EPA folder not found! Checking General folder as fallback...")
                
                # Fallback: check dashboards with NetAppESeries tag (works regardless of folder)
                search_results = self.grafana.search.search_dashboards(tag="NetAppESeries")
                
                if search_results:
                    logger.info(f"Found {len(search_results)} EPA dashboards with NetAppESeries tag:")
                    for dashboard in search_results:
                        folder_info = f"(folder: {dashboard.get('folderTitle', 'General')})" if dashboard.get('folderTitle') else "(folder: General)"
                        logger.info(f"  - {dashboard.get('title', 'Unknown')} {folder_info}")
                    logger.warning("Dashboards are in General folder instead of EPA folder - this may cause issues")
                    return len(search_results) >= expected_dashboards
                else:
                    logger.error("EPA folder not found and no dashboards found with NetAppESeries tag!")
                    return False
                
            folder_uid = epa_folder.get('uid')
            logger.info(f"EPA folder found with UID: {folder_uid}")
            
            # Check dashboards in EPA folder using tag-based search
            search_results = self.grafana.search.search_dashboards(tag="NetAppESeries", folder_id=folder_uid)
            dashboard_count = len(search_results)
            
            if dashboard_count == 0:
                logger.error("No dashboards with NetAppESeries tag found in EPA folder!")
                return False
            elif dashboard_count < expected_dashboards:
                logger.warning(f"Only {dashboard_count}/{expected_dashboards} EPA dashboards found in EPA folder")
                for dashboard in search_results:
                    logger.info(f"  - {dashboard.get('title', 'Unknown')}")
                return False
            else:
                logger.info(f"EPA folder contains {dashboard_count} dashboards with NetAppESeries tag:")
                for dashboard in search_results:
                    logger.info(f"  - {dashboard.get('title', 'Unknown')}")
                return True
                
        except GrafanaClientError as e:
            logger.error(f"Failed to verify EPA setup: {e}")
            return False
        
    def run(self):
        """Main initialization process"""
        logger.info("Starting Grafana initialization")
        
        # Wait for Grafana to be ready
        if not self.wait_for_grafana():
            logger.error("Grafana initialization failed - service not ready")
            sys.exit(1)
            
        # Set up datasources
        if not self.create_influxdb_datasources():
            logger.error("Failed to create InfluxDB datasources")
            sys.exit(1)
            
        # Create EPA folder for better organization
        folder_id = self.create_epa_folder()
        if not folder_id:
            logger.warning("Failed to create EPA folder, dashboards will go to General folder")
            
        # Import dashboards
        success_count, total_count = self.import_dashboards(folder_id)
        if success_count == 0 and total_count > 0:
            logger.error("Failed to import any dashboards")
            sys.exit(1)
        elif success_count < total_count:
            logger.warning(f"Only imported {success_count}/{total_count} dashboards")
            
        # Verify the final setup
        if folder_id and not self.verify_epa_setup(expected_dashboards=success_count):
            logger.error("EPA setup verification failed")
            sys.exit(1)
            
        logger.info("Grafana initialization completed successfully")
        
if __name__ == "__main__":
    initializer = GrafanaInitializer()
    initializer.run()
