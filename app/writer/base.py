"""
Base writer interface for E-Series Performance Analyzer.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

# Initialize logger
LOG = logging.getLogger(__name__)

class Writer(ABC):
    """
    Base class for all writers.
    """
    
    @abstractmethod
    def write(self, data: Dict[str, Any], loop_iteration: int = 1) -> bool:
        """
        Write data to the destination.
        
        Args:
            data: Dictionary containing data to write
            loop_iteration: Current iteration number for debug file naming
            
        Returns:
            True if write was successful, False otherwise
        """
        pass
    
    def close(self, timeout_seconds: int = 90, force_exit_on_timeout: bool = False) -> None:
        """
        Optional method to close the writer and clean up resources.
        Default implementation does nothing - override in subclasses that need cleanup.
        
        Args:
            timeout_seconds: Timeout for cleanup operations
            force_exit_on_timeout: Whether to force exit on timeout
        """
        pass