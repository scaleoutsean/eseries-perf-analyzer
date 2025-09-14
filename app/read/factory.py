"""
Factory for creating appropriate readers.
"""
from pathlib import Path
from typing import Union, List, Optional

from app.read.json_reader import (
    read_volume_statistics,
    read_drive_statistics,
    read_system_statistics,
    read_interface_statistics,
    read_controller_statistics,
    read_system_config,
    read_controller_config,
    read_drive_config,
    read_volume_config,
    read_storage_pool_config,
    read_volume_mappings_config,
    read_host_config,
    read_host_groups_config,
)

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


class ReaderFactory:
    """Factory for creating appropriate readers based on data type."""

    @staticmethod
    def get_reader_for_type(data_type: str):
        """
        Get the appropriate reader function for the given data type.
        
        Args:
            data_type: The type of data to read ('volume_perf', 'drive_stats', etc.)
            
        Returns:
            Reader function for the specified data type
        """
        readers = {
            'volume_perf': read_volume_statistics,
            'drive_stats': read_drive_statistics,
            'system_stats': read_system_statistics,
            'interface_stats': read_interface_statistics,
            'controller_stats': read_controller_statistics,
            'system_config': read_system_config,
            'controller_config': read_controller_config,
            'drive_config': read_drive_config,
            'volume_config': read_volume_config,
            'storage_pool_config': read_storage_pool_config,
            'volume_mappings_config': read_volume_mappings_config,
            'host_config': read_host_config,
            'host_groups_config': read_host_groups_config,
        }
        
        return readers.get(data_type, None)

    @staticmethod
    def read_data(data_type: str, filepath: Union[str, Path]):
        """
        Read data from file using the appropriate reader.
        
        Args:
            data_type: The type of data to read
            filepath: Path to the data file
            
        Returns:
            The data read from the file, or None if the data_type is invalid
        """
        reader = ReaderFactory.get_reader_for_type(data_type)
        if reader:
            return reader(filepath)
        return None