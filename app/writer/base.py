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
    def write(self, data: Dict[str, Any]) -> bool:
        """
        Write data to the destination.
        
        Args:
            data: Dictionary containing data to write
            
        Returns:
            True if write was successful, False otherwise
        """
        pass