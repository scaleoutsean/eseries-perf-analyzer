"""
Example showing how to use the CaseConversionMixin with models.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

from app.utils.model_mixins import CaseConversionMixin


@dataclass
class ExampleModel(CaseConversionMixin):
    """Example model with camelCase attributes demonstrating case conversion."""
    camelCaseAttribute: Optional[str] = None
    anotherCamelCase: Optional[int] = None
    snake_case_attr: Optional[bool] = None
    _raw_data: Dict[str, Any] = field(default_factory=dict)
    
    # After initialization, build the case mapping
    def __post_init__(self):
        self._build_case_mapping()


def demo_case_conversion():
    """Demonstrate using the CaseConversionMixin."""
    # Create an instance with camelCase attributes
    model = ExampleModel(
        camelCaseAttribute="test value",
        anotherCamelCase=42,
        snake_case_attr=True
    )
    
    # Access with original camelCase
    print(f"Original camelCase: {model.camelCaseAttribute}")
    
    # Access with converted snake_case
    print(f"Converted snake_case: {model.camel_case_attribute}")
    
    # Access original snake_case
    print(f"Original snake_case: {model.snake_case_attr}")
    
    # Access with converted camelCase
    print(f"Converted camelCase: {model.snakeCaseAttr}")
    
    # Convert to dict with snake_case keys
    snake_dict = model.to_dict(snake_case=True)
    print(f"Dict with snake_case keys: {snake_dict}")
    
    
if __name__ == "__main__":
    demo_case_conversion()