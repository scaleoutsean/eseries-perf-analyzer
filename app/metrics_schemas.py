# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

"""
InfluxDB 3.x measurement schemas for E-Series Performance Analyzer
Defines field types for measurements to ensure desired data types in InfluxDB
"""

# Schema definitions for measurements that need specific field types
# Only include EPA Collector's "overrides" i.e. fields where type is bad or wrong (integers that shouldn't become floats)
MEASUREMENT_SCHEMAS = {
    'drives': {
        'tags': ['system_id', 'system_name', 'id', 'driveRef', 'serialNumber', 
                'driveMediaType', 'driveType', 'status'],
        'fields': {
            # Integer fields - these should NOT be stored as floats
            'physicalLocation_slot': 'int64',                    # Slot number (1, 2, 3, etc.)
            'physicalLocation_locationPosition': 'int64',        # Position number (matches slot)
            'blkSize': 'int64',                                  # Block size (typically 4096)
            'workingChannel': 'int64',                           # Channel ID (can be -1, 0, 1, 2, etc.)
            'volumeGroupIndex': 'int64',                         # Volume group index/ID (0, 1, 2, etc.)
            'hasDegradedChannel': 'bool',                        # Boolean (true/false) - channel health status
            'spindleSpeed': 'int64',                             # RPM (0 for SSDs, 7200/10000/15000 for HDDs)
            'ssdWearLife_averageEraseCountPercent': 'int64',     # Whole number percentage
            'ssdWearLife_isWearLifeMonitoringSupported': 'int64', # Boolean converted to integer (0/1)
            'currentCommandAgingTimeout': 'int64',               # Timeout value in whole numbers
            'defaultCommandAgingTimeout': 'int64',               # Default timeout value
            'blkSizePhysical': 'int64',                          # Physical block size
            
            # Leave all other fields as default types (InfluxDB will infer them on write)
        }
    },
    
    'storage': {
        'fields': {
            'channelErrorCounts': 'int64',                       # Error count - always whole number
        }
    },
    
    'interface': {
        'fields': {
            'channelErrorCounts': 'int64',                       # Error count - always whole number
        }
    },
    
    'power': {
        'fields': {
            'totalPower': 'int64',                               # Power in watts - whole number
            'numberOfTrays': 'int64',                            # Tray count - always whole number
        }
    },
    
    'temp': {
        'fields': {
            'sensor_index': 'int64',                             # Sensor index - always whole number
        }
    },
    
    'controllers': {
        # No integer field candidates found
        # All fields are either clear floats (IOps, response times) or borderline cases
        # that should remain as floats (percentages, utilization). Schema-on-write will handle this.
        'fields': {}
    }
}

def get_schema_for_measurement(measurement_name):
    """
    Get schema definition for a specific measurement
    
    Args:
        measurement_name (str): Name of the measurement
        
    Returns:
        dict: Schema definition or None if not defined
    """
    return MEASUREMENT_SCHEMAS.get(measurement_name)

def get_integer_fields_for_measurement(measurement_name):
    """
    Get list of fields that should be integers for a measurement
    
    Args:
        measurement_name (str): Name of the measurement
        
    Returns:
        list: Field names that should be integers, empty list if none
    """
    schema = get_schema_for_measurement(measurement_name)
    if not schema or 'fields' not in schema:
        return []
    
    return [field_name for field_name, field_type in schema['fields'].items() 
            if field_type.startswith('int')]

def get_boolean_fields_for_measurement(measurement_name):
    """
    Get list of fields that should be booleans for a measurement
    
    Args:
        measurement_name (str): Name of the measurement
        
    Returns:
        list: Field names that should be booleans, empty list if none
    """
    schema = get_schema_for_measurement(measurement_name)
    if not schema or 'fields' not in schema:
        return []
    
    return [field_name for field_name, field_type in schema['fields'].items() 
            if field_type == 'bool']
