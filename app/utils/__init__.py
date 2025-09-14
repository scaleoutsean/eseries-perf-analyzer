"""
Utility functions for string manipulations and case conversions.
"""
import re
from typing import Dict


def camel_to_snake_case(name: str) -> str:
    """
    Convert a camelCase or PascalCase string to snake_case.
    
    Args:
        name: The camelCase or PascalCase string to convert
        
    Returns:
        The string in snake_case
    """
    # Replace first capital with lowercase
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    # Handle all capitals
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def snake_to_camel_case(name: str) -> str:
    """
    Convert a snake_case string to camelCase.
    
    Args:
        name: The snake_case string to convert
        
    Returns:
        The string in camelCase
    """
    components = name.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


def create_case_mapping(attributes: list) -> Dict[str, str]:
    """
    Create a bidirectional mapping between camelCase and snake_case.
    
    Args:
        attributes: List of attribute names (can be in either case)
        
    Returns:
        Dictionary mapping both camelCase to snake_case and snake_case to camelCase
    """
    mapping = {}
    for attr in attributes:
        # Convert to snake_case if it's not already
        if '_' not in attr and any(c.isupper() for c in attr):
            snake = camel_to_snake_case(attr)
            mapping[attr] = snake
            mapping[snake] = attr
        # Convert to camelCase if it's snake_case
        elif '_' in attr:
            camel = snake_to_camel_case(attr)
            mapping[attr] = camel
            mapping[camel] = attr
    
    return mapping