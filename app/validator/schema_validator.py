"""
Schema-based data validator for E-Series Performance Analyzer.

This module validates and converts data using the model class definitions
to ensure proper field types before data reaches the InfluxDB writer.
"""

import logging
from typing import Dict, Any, List, Optional, Union, Type
from dataclasses import fields, is_dataclass
from app.schema.base_model import BaseModel
from app.schema.models import (
    VolumeConfig, DriveConfig, ControllerConfig, StoragePoolConfig,
    VolumeMappingsConfig, SystemConfig, TrayConfig, InterfaceConfig,
    HostConfig, HostGroupsConfig, ControllerConfigNetInterfaceEthernet, SnapshotGroups,
    AnalysedVolumeStatistics, AnalysedDriveStatistics, AnalysedSystemStatistics,
    AnalysedInterfaceStatistics, AnalyzedControllerStatistics
)

LOG = logging.getLogger(__name__)

class SchemaValidator:
    """
    Validates and converts measurement data using model schemas.
    
    Ensures that all fields have correct types according to the model definitions
    before data is sent to InfluxDB, preventing automatic type conversion issues.
    """
    
    def __init__(self):
        """Initialize the validator with model mappings."""
        # Map measurement names to model classes
        self.model_mapping = {
            # Configuration models (existing)
            'config_volumeconfig': VolumeConfig,
            'config_driveconfig': DriveConfig,
            'config_controllerconfig': ControllerConfig,
            'config_storagepoolconfig': StoragePoolConfig,
            'config_volumemappingsconfig': VolumeMappingsConfig,
            'config_systemconfig': SystemConfig,
            'config_trayconfig': TrayConfig,
            'config_interfaceconfig': InterfaceConfig,
            'config_hostconfig': HostConfig,
            
            # Configuration models (newly added)
            'config_ethernet': ControllerConfigNetInterfaceEthernet,
            'config_host_groups': HostGroupsConfig,  # Host groups (not individual hosts)
            'config_snapshot': SnapshotGroups,
            'config_storage': StoragePoolConfig,  # Storage pools config
            'config_volume': VolumeConfig,  # Single volume vs volumes collection
            'config_volumes': VolumeConfig,  # Already mapped but keeping for clarity
            
            # Statistics models
            'analyzed_volume_statistics': AnalysedVolumeStatistics,
            'analyzed_drive_statistics': AnalysedDriveStatistics,
            'analyzed_system_statistics': AnalysedSystemStatistics,
            'analyzed_interface_statistics': AnalysedInterfaceStatistics,
            'analyzed_controller_statistics': AnalyzedControllerStatistics,
        }
        
    def get_model_class(self, measurement_name: str) -> Optional[Type[BaseModel]]:
        """Get the model class for a measurement name."""
        return self.model_mapping.get(measurement_name)
    
    def validate_and_convert_field(self, field_name: str, field_type: type, value: Any) -> Optional[Any]:
        """
        Validate and convert a field value according to its expected type.
        
        Args:
            field_name: Name of the field
            field_type: Expected type from model annotation
            value: Raw value to validate/convert
            
        Returns:
            Properly typed value or None if conversion fails
        """
        if value is None:
            return None
            
        # Handle Optional types (extract the inner type)
        if hasattr(field_type, '__origin__') and field_type.__origin__ is Union:
            # Optional[T] is Union[T, None]
            non_none_types = [t for t in field_type.__args__ if t is not type(None)]
            if non_none_types:
                field_type = non_none_types[0]
        
        try:
            # Convert based on the expected type
            if field_type == int:
                if isinstance(value, int):
                    return value
                elif isinstance(value, str) and (value.isdigit() or (value.startswith('-') and value[1:].isdigit())):
                    return int(value)
                elif isinstance(value, float) and value == int(value):
                    return int(value)
                else:
                    LOG.debug(f"Cannot convert field '{field_name}' value {value} ({type(value).__name__}) to int")
                    return None
                    
            elif field_type == float:
                if isinstance(value, (int, float)):
                    return float(value)
                elif isinstance(value, str):
                    try:
                        return float(value)
                    except ValueError:
                        LOG.debug(f"Cannot convert field '{field_name}' string '{value}' to float")
                        return None
                else:
                    LOG.debug(f"Cannot convert field '{field_name}' value {value} ({type(value).__name__}) to float")
                    return None
                    
            elif field_type == bool:
                if isinstance(value, bool):
                    return value
                else:
                    LOG.debug(f"Cannot convert field '{field_name}' value {value} ({type(value).__name__}) to bool")
                    return None
                    
            elif field_type == str:
                return str(value) if value is not None else None
                
            else:
                # For complex types, return as-is or handle specially
                return value
                
        except (ValueError, TypeError) as e:
            LOG.debug(f"Error converting field '{field_name}': {e}")
            return None
            
    def convert_model_object_to_dict(self, model_obj: BaseModel) -> Dict[str, Any]:
        """
        Convert a model object to a dictionary with properly typed fields.
        
        Args:
            model_obj: BaseModel instance to convert
            
        Returns:
            Dictionary with validated and properly typed field values
        """
        if not is_dataclass(model_obj):
            LOG.warning(f"Object {type(model_obj)} is not a dataclass")
            return {}
            
        result = {}
        model_fields = {f.name: f for f in fields(model_obj)}
        
        for field_name, field_info in model_fields.items():
            # Skip internal fields and complex objects that shouldn't be InfluxDB fields
            if (field_name.startswith('_') or 
                field_name in ['listOfMappings', 'metadata', 'perms', 'cache', 'cacheSettings', 'mediaScan']):
                continue
                
            # Get the raw value from the model object
            try:
                value = getattr(model_obj, field_name, None)
            except AttributeError:
                continue
                
            if value is None:
                continue
                
            # Validate and convert the field value
            field_type = field_info.type
            converted_value = self.validate_and_convert_field(field_name, field_type, value)
            
            if converted_value is not None:
                result[field_name] = converted_value
                
                # Debug logging for capacity field
                if field_name == 'capacity':
                    LOG.info(f"🔍 SCHEMA VALIDATOR - Converted capacity: {converted_value} (type: {type(converted_value).__name__})")
                    
        return result
    
    def validate_measurement_data(self, measurement_name: str, measurement_data: Any) -> Any:
        """
        Validate and convert measurement data using the appropriate model schema.
        
        Args:
            measurement_name: Name of the measurement
            measurement_data: Raw measurement data (BaseModel objects, dicts, or lists)
            
        Returns:
            Validated data with proper types (converts BaseModel objects to dicts)
        """
        LOG.debug(f"Validating measurement data for: {measurement_name}")
        
        # Get the model class for this measurement
        model_class = self.get_model_class(measurement_name)
        if not model_class:
            LOG.debug(f"No model class found for measurement: {measurement_name}")
            return measurement_data
            
        # Handle different data structures
        if isinstance(measurement_data, list):
            validated_data = []
            for item in measurement_data:
                if isinstance(item, BaseModel):
                    # Convert BaseModel object to validated dict
                    validated_dict = self.convert_model_object_to_dict(item)
                    if validated_dict:
                        validated_data.append(validated_dict)
                elif isinstance(item, dict):
                    # Validate existing dict against model schema
                    validated_dict = self.validate_dict_against_model(item, model_class)
                    if validated_dict:
                        validated_data.append(validated_dict)
                else:
                    # Keep other types as-is
                    validated_data.append(item)
            return validated_data
            
        elif isinstance(measurement_data, BaseModel):
            # Single BaseModel object
            return self.convert_model_object_to_dict(measurement_data)
            
        elif isinstance(measurement_data, dict):
            # Single dict - validate against model
            return self.validate_dict_against_model(measurement_data, model_class)
            
        else:
            LOG.debug(f"Unknown data type for {measurement_name}: {type(measurement_data)}")
            return measurement_data
    
    def validate_dict_against_model(self, data_dict: Dict[str, Any], model_class: Type[BaseModel]) -> Dict[str, Any]:
        """
        Validate a dictionary against a model class schema.
        
        Args:
            data_dict: Dictionary to validate
            model_class: Model class to validate against
            
        Returns:
            Dictionary with validated and properly typed values
        """
        if not is_dataclass(model_class):
            return data_dict
            
        result = {}
        model_fields = {f.name: f for f in fields(model_class)}
        
        for field_name, field_info in model_fields.items():
            # Skip internal fields and complex objects
            if (field_name.startswith('_') or 
                field_name in ['listOfMappings', 'metadata', 'perms', 'cache', 'cacheSettings', 'mediaScan']):
                continue
                
            # Get value from dict
            value = data_dict.get(field_name)
            if value is None:
                continue
                
            # Validate and convert the field value
            field_type = field_info.type
            converted_value = self.validate_and_convert_field(field_name, field_type, value)
            
            if converted_value is not None:
                result[field_name] = converted_value
                
        # Include any additional fields that aren't in the model
        for key, value in data_dict.items():
            if key not in result and not key.startswith('_'):
                result[key] = value
                
        return result


# Global validator instance
validator = SchemaValidator()


def validate_measurements_for_influxdb(measurements: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to validate all measurements for InfluxDB writing.
    
    Args:
        measurements: Dictionary of measurement_name -> measurement_data
        
    Returns:
        Dictionary with validated measurements
    """
    LOG.info("🔍 Starting schema-based validation for InfluxDB measurements")
    
    validated_measurements = {}
    
    for measurement_name, measurement_data in measurements.items():
        try:
            validated_data = validator.validate_measurement_data(measurement_name, measurement_data)
            validated_measurements[measurement_name] = validated_data
            
            # Log validation results
            if isinstance(validated_data, list) and validated_data:
                LOG.debug(f"Validated {len(validated_data)} records for {measurement_name}")
                
                # Check if we have capacity fields in the first record
                first_record = validated_data[0] if validated_data else {}
                if isinstance(first_record, dict) and 'capacity' in first_record:
                    capacity_value = first_record['capacity']
                    LOG.info(f"🔍 VALIDATION SUCCESS - {measurement_name} capacity: {capacity_value} (type: {type(capacity_value).__name__})")
                    
        except Exception as e:
            LOG.error(f"Error validating measurement {measurement_name}: {e}")
            # Use original data if validation fails
            validated_measurements[measurement_name] = measurement_data
            
    return validated_measurements