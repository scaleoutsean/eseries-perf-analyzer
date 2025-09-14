"""
JSON reader for E-Series performance analyzer.
Handles reading from previously saved JSON files.

Recommended file naming convention:
    <function>_<system_id>_<timestamp>.json

Where:
    - function: The API function or data type (e.g., 'analysed_drive_statistics')
    - system_id: The WWN or other unique identifier of the storage system
    - timestamp: Unix timestamp (seconds since epoch)

Example:
    analysed_drive_statistics_600A098000F63714000000005E79C17C_1757410112.json

This naming convention ensures files can be properly sorted chronologically,
even when copied between systems or when filesystem timestamps are not reliable.
"""
import json
import logging
from pathlib import Path
import datetime
from typing import Dict, List, Any, Optional, Union, Type, TypeVar

from app.schema.models import (
    AnalysedVolumeStatistics,
    AnalysedDriveStatistics,
    AnalysedSystemStatistics,
    AnalysedInterfaceStatistics,
    AnalyzedControllerStatistics,
    SystemConfig,
    ControllerConfig,
    DriveConfig,
    VolumeConfig,
    StoragePoolConfig,
    VolumeMappingsConfig,
    HostConfig,
    HostGroupsConfig,
)

logger = logging.getLogger(__name__)

# Type variable for generic model handling
T = TypeVar('T')


class JsonReader:
    """Reads data from JSON files and converts them to appropriate models."""
    
    @staticmethod
    def extract_timestamp_from_filename(filename: Union[str, Path]) -> Optional[datetime.datetime]:
        """
        Extract timestamp from filename following the recommended naming convention:
        <function>_<system_id>_<timestamp>.json
        
        Args:
            filename: The filename to parse
            
        Returns:
            A datetime object if a timestamp was extracted, None otherwise
        """
        filename_str = str(filename)
        
        try:
            # Extract the timestamp part (last part before .json)
            parts = filename_str.split('_')
            if len(parts) >= 3:
                # The timestamp should be the last part before .json
                timestamp_part = parts[-1].split('.')[0]
                timestamp = int(timestamp_part)
                return datetime.datetime.fromtimestamp(timestamp)
        except (ValueError, IndexError):
            pass
            
        return None
    
    @staticmethod
    def extract_timestamp(data: Dict[str, Any]) -> Optional[datetime.datetime]:
        """
        Extract timestamp from API response data.
        Looks for common timestamp fields in the data.
        
        Args:
            data: The API response data
            
        Returns:
            A datetime object if a timestamp was found, None otherwise
        """
        # Look for common timestamp fields
        timestamp_fields = ['observedTime', 'collectionTime', 'timestamp', 'dateTime']
        
        for field in timestamp_fields:
            if field in data and data[field]:
                try:
                    # Try to parse ISO format datetime
                    return datetime.datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                except (ValueError, AttributeError, TypeError):
                    continue
                    
        # Look for epoch milliseconds
        ms_fields = ['observedTimeInMS', 'timestampMs', 'epochMs']
        for field in ms_fields:
            if field in data and data[field]:
                try:
                    ms_value = int(data[field])
                    return datetime.datetime.fromtimestamp(ms_value / 1000)
                except (ValueError, TypeError):
                    continue
                    
        return None

    @staticmethod
    def read_file(filepath: Union[str, Path]) -> Dict[str, Any]:
        """Read a JSON file and return its contents as a dictionary."""
        try:
            filepath = Path(filepath)
            if not filepath.exists():
                logger.error(f"File not found: {filepath}")
                return {}
            
            with open(filepath, 'r', encoding='utf-8') as file:
                return json.load(file)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"Error parsing JSON from {filepath}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error reading {filepath}: {e}")
            return {}

    @staticmethod
    def read_model_from_file(filepath: Union[str, Path], model_class: Type[T]) -> Optional[T]:
        """
        Read JSON file and convert to the specified model.
        
        Args:
            filepath: Path to the JSON file
            model_class: The class to convert the data to
            
        Returns:
            An instance of the model_class if successful, None otherwise
        """
        data = JsonReader.read_file(filepath)
        if not data:
            return None
            
        try:
            # All our models have from_api_response method
            return model_class.from_api_response(data)
        except Exception as e:
            logger.error(f"Error converting data to {model_class.__name__}: {e}")
            return None
            
    @staticmethod
    def read_models_from_file(filepath: Union[str, Path], model_class: Type[T]) -> List[T]:
        """
        Read JSON file containing a list of items and convert each to the specified model.
        
        Args:
            filepath: Path to the JSON file
            model_class: The class to convert each item to
            
        Returns:
            A list of model_class instances if successful, empty list otherwise
        """
        data = JsonReader.read_file(filepath)
        if not data or not isinstance(data, list):
            return []
            
        result = []
        for item in data:
            try:
                model = model_class.from_api_response(item)
                result.append(model)
            except Exception as e:
                logger.error(f"Error converting item to {model_class.__name__}: {e}")
                
        return result


# Convenience functions for common model types
def read_volume_statistics(filepath: Union[str, Path]) -> List[AnalysedVolumeStatistics]:
    """Read volume statistics data from JSON file."""
    return JsonReader.read_models_from_file(filepath, AnalysedVolumeStatistics)

def read_drive_statistics(filepath: Union[str, Path]) -> List[AnalysedDriveStatistics]:
    """Read drive statistics data from JSON file."""
    return JsonReader.read_models_from_file(filepath, AnalysedDriveStatistics)

def read_system_statistics(filepath: Union[str, Path]) -> Optional[AnalysedSystemStatistics]:
    """Read system statistics data from JSON file."""
    return JsonReader.read_model_from_file(filepath, AnalysedSystemStatistics)

def read_interface_statistics(filepath: Union[str, Path]) -> List[AnalysedInterfaceStatistics]:
    """Read interface statistics data from JSON file."""
    return JsonReader.read_models_from_file(filepath, AnalysedInterfaceStatistics)

def read_controller_statistics(filepath: Union[str, Path]) -> Optional[AnalyzedControllerStatistics]:
    """Read controller statistics data from JSON file."""
    return JsonReader.read_model_from_file(filepath, AnalyzedControllerStatistics)

def read_system_config(filepath: Union[str, Path]) -> Optional[SystemConfig]:
    """Read system configuration data from JSON file."""
    return JsonReader.read_model_from_file(filepath, SystemConfig)

def read_controller_config(filepath: Union[str, Path]) -> List[ControllerConfig]:
    """Read controller configuration data from JSON file."""
    return JsonReader.read_models_from_file(filepath, ControllerConfig)

def read_drive_config(filepath: Union[str, Path]) -> List[DriveConfig]:
    """Read drive configuration data from JSON file."""
    return JsonReader.read_models_from_file(filepath, DriveConfig)

def read_volume_config(filepath: Union[str, Path]) -> List[VolumeConfig]:
    """Read volume configuration data from JSON file."""
    return JsonReader.read_models_from_file(filepath, VolumeConfig)

def read_storage_pool_config(filepath: Union[str, Path]) -> List[StoragePoolConfig]:
    """Read storage pool configuration data from JSON file."""
    return JsonReader.read_models_from_file(filepath, StoragePoolConfig)

def read_volume_mappings_config(filepath: Union[str, Path]) -> List[VolumeMappingsConfig]:
    """Read volume mappings configuration data from JSON file."""
    return JsonReader.read_models_from_file(filepath, VolumeMappingsConfig)

def read_host_config(filepath: Union[str, Path]) -> List[HostConfig]:
    """Read host configuration data from JSON file."""
    return JsonReader.read_models_from_file(filepath, HostConfig)

def read_host_groups_config(filepath: Union[str, Path]) -> List[HostGroupsConfig]:
    """Read host groups configuration data from JSON file."""
    return JsonReader.read_models_from_file(filepath, HostGroupsConfig)