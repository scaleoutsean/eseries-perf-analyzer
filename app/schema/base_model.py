from dataclasses import dataclass, field, fields
from typing import Dict, Any, Optional, get_type_hints, TypeVar, Type, ClassVar
import re

T = TypeVar('T')

@dataclass
class BaseModel:
    """
    Base model class that automatically converts camelCase keys to snake_case 
    properties when accessing them.
    
    All dataclasses should inherit from this class to get automatic case conversion.
    """
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def camel_to_snake(cls, camel_case: str) -> str:
        """Convert camelCase string to snake_case"""
        # Handle empty strings
        if not camel_case:
            return camel_case
            
        # Replace first camelCase capital with underscore and lowercase
        snake_case = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', camel_case)
        return snake_case.lower()
        
    @classmethod
    def snake_to_camel(cls, snake_case: str) -> str:
        """Convert snake_case string to camelCase"""
        # Handle empty strings
        if not snake_case:
            return snake_case
            
        # Handle special case for first component
        components = snake_case.split('_')
        camel_case = components[0]
        
        # Convert remaining components to camelCase
        for component in components[1:]:
            if component:
                camel_case += component[0].upper() + component[1:]
                
        return camel_case

    @classmethod
    def from_api_response(cls: Type[T], data: Dict[str, Any]) -> T:
        """Create an instance from API response data"""
        # Initialize with empty values
        instance_args = {}
        
        # Get all field names and types
        class_fields = {f.name: f for f in fields(cls)}
        
        # Set values from data based on camelCase equivalents
        for field_name in class_fields:
            # Skip _raw_data and class variables
            if field_name == '_raw_data' or isinstance(class_fields[field_name].type, ClassVar):
                continue
                
            # Look for direct match first (for fields already in camelCase)
            if field_name in data:
                instance_args[field_name] = data.get(field_name)
            else:
                # Try to find camelCase equivalent
                camel_name = cls.snake_to_camel(field_name)
                if camel_name in data:
                    instance_args[field_name] = data.get(camel_name)
        
        # Store the original data
        instance_args['_raw_data'] = data.copy() if data else {}
        
        # Create and return the instance
        return cls(**instance_args)
        
    def get_raw(self, key: str, default: Any = None) -> Any:
        """Access any field from the raw data"""
        return self._raw_data.get(key, default)