"""
ChromaDB Telemetry Error Suppression
=====================================

This module provides a fix for ChromaDB v0.5.23 telemetry errors by:
1. Patching the problematic capture() method calls
2. Suppressing telemetry-related error logging
"""

import logging
import warnings
from functools import wraps

# Suppress specific ChromaDB telemetry warnings
warnings.filterwarnings('ignore', message='.*telemetry.*', category=UserWarning)
warnings.filterwarnings('ignore', message='.*capture.*takes.*positional.*', category=UserWarning)

def suppress_telemetry_errors(func):
    """Decorator to suppress ChromaDB telemetry errors"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if 'capture()' in str(e) and 'positional argument' in str(e):
                # This is a telemetry error - suppress it
                pass
            elif 'telemetry' in str(e).lower():
                # General telemetry error - suppress it
                pass
            else:
                # Re-raise non-telemetry errors
                raise
        return None
    return wrapper

def patch_chromadb_logging():
    """Patch ChromaDB logging to suppress telemetry errors"""
    
    # Get ChromaDB loggers
    chromadb_logger = logging.getLogger('chromadb')
    
    # Custom filter to suppress telemetry errors
    class TelemetryErrorFilter(logging.Filter):
        def filter(self, record):
            message = record.getMessage()
            # Suppress specific telemetry errors
            if 'telemetry event' in message and 'capture()' in message:
                return False
            if 'ClientStartEvent' in message:
                return False
            if 'ClientCreateCollectionEvent' in message:
                return False
            return True
    
    # Add filter to ChromaDB logger
    telemetry_filter = TelemetryErrorFilter()
    chromadb_logger.addFilter(telemetry_filter)
    
    # Also patch the root logger for safety
    root_logger = logging.getLogger()
    root_logger.addFilter(telemetry_filter)

# Apply the patch when this module is imported
patch_chromadb_logging()