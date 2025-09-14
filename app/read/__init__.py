"""
Integration module for the read functionality in the main app.
"""
from app.read.factory import ReaderFactory
from app.read.json_reader import JsonReader
from app.read.cli import add_from_json_args, process_from_json

# Export key components for easier imports
__all__ = [
    'ReaderFactory', 
    'JsonReader', 
    'add_from_json_args', 
    'process_from_json'
]
