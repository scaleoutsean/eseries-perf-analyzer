"""
Example of applying the CaseConversionMixin to an existing model.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

from app.utils.model_mixins import CaseConversionMixin
from app.schema.models import SystemConfigDriveTypes, SystemConfig


# Create a new version of the model with the mixin
@dataclass
class SystemConfigWithMixin(SystemConfig, CaseConversionMixin):
    """SystemConfig with case conversion capabilities."""
    
    def __post_init__(self):
        """Initialize case mapping after dataclass initialization."""
        self._build_case_mapping()
        
    @staticmethod
    def from_api_response(data: Dict) -> 'SystemConfigWithMixin':
        """Create from API response with the same method as parent."""
        drive_types = None
        if data.get("driveTypes"):
            drive_types = [SystemConfigDriveTypes.from_api_response(m) for m in data.get("driveTypes") or []]
            
        # Use the parent constructor but return our enhanced type
        result = SystemConfigWithMixin(
            asupEnabled=data.get('asupEnabled'),
            autoLoadBalancingEnabled=data.get('autoLoadBalancingEnabled'),
            chassisSerialNumber=data.get('chassisSerialNumber'),
            driveCount=data.get('driveCount'),
            driveTypes=drive_types,
            freePoolSpace=data.get('freePoolSpace'),
            hostSpareCountInStandby=data.get('hostSpareCountInStandby'),
            hostSparesUsed=data.get('hostSparesUsed'),
            hotSpareCount=data.get('hotSpareCount'),
            mediaScanPeriod=data.get('mediaScanPeriod'),
            model=data.get('model'),
            name=data.get('name', 'unknown'),
            status=data.get('status'),
            unconfiguredSpace=data.get('unconfiguredSpace'),
            usedPoolSpace=data.get('usedPoolSpace'),
            wwn=data.get('wwn', 'unknown'),
            _raw_data=data.copy()
        )
        return result


def demonstrate_usage():
    """Show how to use the enhanced model with case conversion."""
    # Sample data
    sample_data = {
        "asupEnabled": True,
        "autoLoadBalancingEnabled": False,
        "chassisSerialNumber": "123456789",
        "driveCount": 24,
        "name": "test-system",
        "status": "optimal"
    }
    
    # Create instance
    config = SystemConfigWithMixin.from_api_response(sample_data)
    
    # Access with original camelCase
    print(f"Original camelCase: {config.asupEnabled}")
    
    # Access with converted snake_case
    print(f"Converted snake_case: {config.asup_enabled}")
    
    # Convert to dict with snake_case keys
    snake_dict = config.to_dict(snake_case=True)
    print(f"First few snake_case keys: {list(snake_dict.keys())[:5]}")
    
    return config


if __name__ == "__main__":
    demonstrate_usage()