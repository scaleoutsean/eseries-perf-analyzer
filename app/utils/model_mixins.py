"""
Mixin classes that can be used with models to provide additional functionality.
"""
from typing import Dict, Any, Optional

from app.utils import camel_to_snake_case, snake_to_camel_case


class CaseConversionMixin:
    """
    A mixin that provides case conversion functionality for model attributes.
    It allows accessing camelCase attributes as snake_case and vice versa.
    """
    _case_mapping: Dict[str, str] = None
    
    def __getattr__(self, name):
        """
        Override attribute access to allow getting attributes in different case.
        If an attribute doesn't exist, try the converted case version.
        """
        # Initialize case mapping if not already done
        if self._case_mapping is None:
            self._build_case_mapping()
        
        # If the attribute name is in the mapping, try the mapped version
        if name in self._case_mapping:
            mapped_name = self._case_mapping[name]
            # Use object.__getattribute__ to avoid recursive __getattr__ calls
            try:
                return object.__getattribute__(self, mapped_name)
            except AttributeError:
                pass
                
        # Default behavior
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    def _build_case_mapping(self):
        """
        Build the case mapping dictionary for this instance.
        Maps camelCase to snake_case and vice versa for all attributes.
        """
        self._case_mapping = {}
        # Get all attributes from the instance dictionary
        for attr in self.__dict__:
            # Skip private attributes and the mapping itself
            if attr.startswith('_'):
                continue
                
            # Map camelCase to snake_case
            if '_' not in attr and any(c.isupper() for c in attr):
                snake = camel_to_snake_case(attr)
                self._case_mapping[snake] = attr
                self._case_mapping[attr] = attr  # Identity mapping
            # Map snake_case to camelCase
            elif '_' in attr:
                camel = snake_to_camel_case(attr)
                self._case_mapping[camel] = attr
                self._case_mapping[attr] = attr  # Identity mapping
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Dict-like get method that respects case conversion.
        
        Args:
            key: The attribute name to get
            default: The default value if the attribute doesn't exist
            
        Returns:
            The attribute value or default
        """
        try:
            return self.__getattr__(key)
        except AttributeError:
            return default
            
    def to_dict(self, snake_case: bool = False) -> Dict[str, Any]:
        """
        Convert the model to a dictionary.
        
        Args:
            snake_case: If True, convert all keys to snake_case
            
        Returns:
            Dict representation of the model
        """
        result = {}
        for key, value in self.__dict__.items():
            # Skip private attributes and the case mapping
            if key.startswith('_'):
                continue
                
            # Convert key to snake_case if requested
            if snake_case and '_' not in key and any(c.isupper() for c in key):
                key = camel_to_snake_case(key)
                
            result[key] = value
            
        return result