"""
JSON file writer for E-Series Performance Analyzer.
"""

import logging
import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from app.config.endpoint_categories import ENDPOINT_CATEGORIES, EndpointCategory

from app.writer.base import Writer

# Initialize logger
LOG = logging.getLogger(__name__)

class JsonWriter(Writer):
    """
    Writer that outputs data to JSON files.
    """
    
    def __init__(self, output_dir: str, system_id: str = "1"):
        """
        Initialize the JSON writer.
        
        Args:
            output_dir: Directory where JSON files will be written
            system_id: E-Series system ID for filename generation
        """
        self.output_dir = output_dir
        self.system_id = system_id
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        logging.info(f"JSON Writer initialized with output directory: {output_dir}")
        
        # Build reverse lookup for endpoint categories
        self.endpoint_to_category = {}
        for category, endpoints in ENDPOINT_CATEGORIES.items():
            for endpoint in endpoints:
                self.endpoint_to_category[endpoint] = category.value
    
    def _make_serializable(self, obj):
        """
        Recursively convert objects to JSON-serializable format.
        
        Args:
            obj: Object to convert
            
        Returns:
            JSON-serializable representation
        """
        if isinstance(obj, (list, tuple)):
            # Handle lists/tuples - convert each item
            return [self._make_serializable(item) for item in obj]
        elif isinstance(obj, dict):
            # Handle dictionaries - convert each value
            return {key: self._make_serializable(value) for key, value in obj.items()}
        elif hasattr(obj, '_raw_data') and obj._raw_data:
            # Use the raw API response data (BaseModel objects)
            return obj._raw_data
        elif hasattr(obj, 'dict'):
            # Fallback to Pydantic's dict() method
            return obj.dict()
        elif hasattr(obj, '__dict__'):
            # Convert dataclass to dictionary using __dict__
            item_dict = {}
            for key, value in obj.__dict__.items():
                if not key.startswith('_'):  # Skip private attributes
                    item_dict[key] = self._make_serializable(value)  # Recursive call
            return item_dict
        else:
            # Already serializable (str, int, float, bool, None) or convert to string
            if obj is None or isinstance(obj, (str, int, float, bool)):
                return obj
            else:
                return str(obj)
    
    def _generate_filename(self, endpoint: str, timestamp_str: str, object_id: Optional[str] = None) -> str:
        """
        Generate smart filename using category_endpoint_sysid_objectid_timestamp pattern.
        
        Args:
            endpoint: API endpoint name
            timestamp_str: Formatted timestamp string
            object_id: Optional object ID for ID-dependent endpoints
            
        Returns:
            Filename following the pattern: category_endpoint_sysid_[objectid_]timestamp.json
        """
        # Get category for this endpoint
        category = self.endpoint_to_category.get(endpoint, "unknown")
        
        # Build filename components
        parts = [category, endpoint, self.system_id]
        
        # Add object ID if provided (for ID-dependent endpoints)
        if object_id:
            # Clean object ID for filesystem safety
            clean_object_id = str(object_id).replace('/', '_').replace('\\', '_')
            parts.append(clean_object_id)
        
        parts.append(timestamp_str)
        
        return f"{'_'.join(parts)}.json"
    
    def write(self, data: Dict[str, Any]) -> bool:
        """
        Write data to JSON files.
        
        Args:
            data: Dictionary containing data to write
            
        Returns:
            True if write was successful, False otherwise
        """
        LOG.info(f"Writing data to JSON files in {self.output_dir}")
        
        timestamp = int(time.time())
        timestamp_str = datetime.fromtimestamp(timestamp).strftime('%Y%m%d%H%M')
        
        # Write each data type - handle ID-dependent endpoints with individual files
        for data_type, items in data.items():
            if items is None:
                continue
            
            try:
                # Convert items to serializable format first
                json_data = self._make_serializable(items)
                
                # Check if this is an ID-dependent endpoint with multiple objects
                if isinstance(json_data, list) and len(json_data) > 0:
                    # Check if items have identifiable IDs (volumeRef, volumeGroupRef, etc.)
                    id_fields = ['volumeRef', 'volumeGroupRef', 'pitGroupRef', 'id', 'wwn', 'volumeId', 'poolId', 'controllerId', 'diskId']
                    
                    # Look for ID fields in the first item
                    object_id_field = None
                    first_item = json_data[0] if json_data else {}
                    for field in id_fields:
                        if isinstance(first_item, dict) and field in first_item:
                            object_id_field = field
                            break
                    
                    # If we found an ID field, write separate files per object
                    if object_id_field:
                        for item in json_data:
                            if isinstance(item, dict) and object_id_field in item:
                                object_id = str(item[object_id_field])
                                filename = self._generate_filename(data_type, timestamp_str, object_id)
                                filepath = os.path.join(self.output_dir, filename)
                                
                                with open(filepath, 'w') as f:
                                    json.dump(item, f, indent=2)
                                LOG.info(f"Wrote {data_type} item for {object_id_field}={object_id} to {filepath}")
                    else:
                        # No ID field found, write as single array file
                        filename = self._generate_filename(data_type, timestamp_str)
                        filepath = os.path.join(self.output_dir, filename)
                        
                        with open(filepath, 'w') as f:
                            json.dump(json_data, f, indent=2)
                        LOG.info(f"Wrote {len(json_data)} {data_type} items to {filepath}")
                else:
                    # Single object or empty list - write as single file
                    filename = self._generate_filename(data_type, timestamp_str)
                    filepath = os.path.join(self.output_dir, filename)
                    
                    with open(filepath, 'w') as f:
                        json.dump(json_data, f, indent=2)
                    LOG.info(f"Wrote {data_type} data to {filepath}")
                    
            except Exception as e:
                LOG.error(f"Failed to write {data_type} data: {e}")
                return False
        
        return True