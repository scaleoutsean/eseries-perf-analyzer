"""
Multi-writer for E-Series Performance Analyzer.
Supports writing to multiple destinations simultaneously (e.g., InfluxDB + Prometheus).
"""

import logging
from typing import Dict, Any, List, Optional

from app.writer.base import Writer

# Initialize logger
LOG = logging.getLogger(__name__)

class MultiWriter(Writer):
    """
    Composite writer that can write to multiple destinations simultaneously.
    Useful for outputting data to both InfluxDB and Prometheus at the same time.
    """
    
    def __init__(self, writers: List[Writer]):
        """
        Initialize the multi-writer with a list of writers.
        
        Args:
            writers: List of Writer instances to write to
        """
        self.writers = writers
        LOG.info(f"MultiWriter initialized with {len(writers)} writers: {[type(w).__name__ for w in writers]}")
    
    def write(self, data: Dict[str, Any], loop_iteration: int = 1) -> bool:
        """
        Write data to all configured writers.
        
        Args:
            data: Dictionary containing data to write
            loop_iteration: Current iteration number for debug file naming
            
        Returns:
            True if all writes were successful, False if any failed
        """
        success = True
        results = []
        
        for i, writer in enumerate(self.writers):
            try:
                writer_name = type(writer).__name__
                LOG.debug(f"Writing to {writer_name} ({i+1}/{len(self.writers)})")
                
                result = writer.write(data, loop_iteration)
                results.append(result)
                
                if result:
                    LOG.debug(f"✅ {writer_name} write successful")
                else:
                    LOG.error(f"❌ {writer_name} write failed")
                    success = False
                    
            except Exception as e:
                writer_name = type(writer).__name__
                LOG.error(f"❌ Exception in {writer_name}: {e}", exc_info=True)
                results.append(False)
                success = False
        
        # Log summary
        successful_writers = sum(1 for r in results if r)
        LOG.info(f"MultiWriter completed: {successful_writers}/{len(self.writers)} writers successful")
        
        return success
    
    def close(self, timeout_seconds=90, force_exit_on_timeout=False):
        """
        Close all writers that support the close method.
        
        Args:
            timeout_seconds: Timeout for closing operations
            force_exit_on_timeout: Whether to force exit on timeout
        """
        LOG.info("Closing MultiWriter and all sub-writers...")
        
        for writer in self.writers:
            try:
                writer_name = type(writer).__name__
                
                # Check if writer has close method
                if hasattr(writer, 'close') and callable(getattr(writer, 'close')):
                    LOG.info(f"Closing {writer_name}...")
                    writer.close(timeout_seconds=timeout_seconds, force_exit_on_timeout=force_exit_on_timeout)
                    LOG.info(f"✅ {writer_name} closed successfully")
                else:
                    LOG.debug(f"ℹ️  {writer_name} does not have close method, skipping")
                    
            except Exception as e:
                writer_name = type(writer).__name__
                LOG.error(f"❌ Error closing {writer_name}: {e}", exc_info=True)
        
        LOG.info("MultiWriter close operation completed")
    
    def __str__(self) -> str:
        """String representation of the multi-writer."""
        writer_names = [type(w).__name__ for w in self.writers]
        return f"MultiWriter({', '.join(writer_names)})"
    
    def __repr__(self) -> str:
        """Detailed representation of the multi-writer."""
        return self.__str__()