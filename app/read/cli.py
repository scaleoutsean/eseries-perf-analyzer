"""
Entry point for the E-Series Performance Analyzer CLI.
"""
import argparse
import logging
import os
from pathlib import Path

from app.read.factory import ReaderFactory
from app.read.json_reader import JsonReader


def add_from_json_args(parser):
    """Add command line arguments for reading from JSON files."""
    fromjson_group = parser.add_argument_group('JSON input options')
    fromjson_group.add_argument(
        '--fromJson', 
        action='store_true',
        help='Read data from JSON files instead of collecting from systems'
    )
    fromjson_group.add_argument(
        '--inputDir', 
        type=str,
        default='output',
        help='Directory containing JSON files to read (default: output)'
    )
    fromjson_group.add_argument(
        '--inputPattern', 
        type=str,
        default='*.json',
        help='File pattern for JSON files to read (default: *.json)'
    )
    fromjson_group.add_argument(
        '--sortBy',
        type=str,
        choices=['mtime', 'name', 'timestamp', 'none'],
        default='timestamp',
        help='How to sort input files: mtime (modification time), name (alphabetical), timestamp (from filename), or none (default: timestamp)'
    )
    fromjson_group.add_argument(
        '--sortReverse',
        action='store_true',
        help='Reverse the sort order (newest/Z first instead of oldest/A first)'
    )


def process_from_json(args):
    """Process data from JSON files."""
    logging.info(f"Reading data from JSON files in directory: {args.inputDir}")
    
    input_dir = Path(args.inputDir)
    if not input_dir.exists():
        logging.error(f"Input directory {args.inputDir} does not exist")
        return None
    
    # Find all JSON files matching the pattern
    json_files = list(input_dir.glob(args.inputPattern))
    logging.info(f"Found {len(json_files)} JSON files")
    
    if not json_files:
        logging.warning(f"No files matching pattern '{args.inputPattern}' found in {args.inputDir}")
        return None
        
    # Sort files according to user preference
    if args.sortBy == 'mtime':
        json_files.sort(key=lambda x: x.stat().st_mtime, reverse=args.sortReverse)
        sort_desc = "chronological" if not args.sortReverse else "reverse chronological"
        logging.info(f"Processing files in {sort_desc} order (by modification time)")
    elif args.sortBy == 'name':
        json_files.sort(key=lambda x: str(x), reverse=args.sortReverse)
        sort_desc = "alphabetical" if not args.sortReverse else "reverse alphabetical"
        logging.info(f"Processing files in {sort_desc} order (by filename)")
    elif args.sortBy == 'timestamp':
        # Use the timestamp from filename if available, otherwise use mtime
        def get_timestamp_key(file_path):
            timestamp = JsonReader.extract_timestamp_from_filename(file_path)
            if timestamp:
                return timestamp.timestamp()
            return file_path.stat().st_mtime
            
        json_files.sort(key=get_timestamp_key, reverse=args.sortReverse)
        sort_desc = "chronological" if not args.sortReverse else "reverse chronological"
        logging.info(f"Processing files in {sort_desc} order (by timestamp from filename)")
    else:
        # No sorting (system order)
        if args.sortReverse:
            json_files.reverse()
            logging.info("Processing files in reverse system order")
        else:
            logging.info("Processing files in system order (no sorting)")
    
    # Process each file based on its name/content
    results = {}
    for file_path in json_files:
        # Try to determine the data type from the filename
        file_stem = file_path.stem
        
        # Try to match file name to a known data type
        # This is a simplified example - you might want a more robust mapping
        if 'volume_perf' in file_stem:
            data_type = 'volume_perf'
        elif 'drive_stats' in file_stem:
            data_type = 'drive_stats'
        elif 'system_stats' in file_stem:
            data_type = 'system_stats'
        elif 'interface_stats' in file_stem:
            data_type = 'interface_stats'
        elif 'controller_stats' in file_stem:
            data_type = 'controller_stats'
        elif 'system_config' in file_stem:
            data_type = 'system_config'
        elif 'controller_config' in file_stem:
            data_type = 'controller_config'
        elif 'drive_config' in file_stem:
            data_type = 'drive_config'
        elif 'volume_config' in file_stem:
            data_type = 'volume_config'
        elif 'storage_pool_config' in file_stem:
            data_type = 'storage_pool_config'
        elif 'volume_mappings' in file_stem:
            data_type = 'volume_mappings_config'
        elif 'host_config' in file_stem:
            data_type = 'host_config'
        elif 'host_groups' in file_stem:
            data_type = 'host_groups_config'
        else:
            logging.warning(f"Could not determine data type for file: {file_path}")
            continue
            
        # Read the data using the appropriate reader
        data = ReaderFactory.read_data(data_type, file_path)
        if data is not None:
            logging.info(f"Successfully read data from {file_path}")
            results[data_type] = data
        else:
            logging.error(f"Failed to read data from {file_path}")
    
    return results


def main():
    """Main entry point for the CLI."""
    # This is just a sample implementation to demonstrate the --fromJson functionality
    parser = argparse.ArgumentParser(
        description='E-Series Performance Analyzer'
    )
    
    # Add fromJson arguments
    add_from_json_args(parser)
    
    # Parse arguments
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Process from JSON if specified
    if args.fromJson:
        results = process_from_json(args)
        # Process the results as needed
        if results:
            for data_type, data in results.items():
                logging.info(f"Data type: {data_type}, Number of items: {len(data) if hasattr(data, '__len__') else 1}")
    else:
        # Regular data collection path (to be implemented)
        pass


if __name__ == '__main__':
    main()