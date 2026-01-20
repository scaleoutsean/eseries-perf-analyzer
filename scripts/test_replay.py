#!/usr/bin/env python3
"""
Test script to replay captured SANtricity API responses and verify collector behavior.
Useful for testing field coercion and ensuring no fields are dropped.

Usage:
    python3 scripts/test_replay.py --captures ./captures/20250101T120000Z
"""

import sys
import os
import json
import glob
import argparse
import logging
import re
from unittest.mock import MagicMock, patch

# Add parent directory to path to import collector
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'epa', 'collector')))

# Prepare dummy arguments for collector import to avoid conflicts
original_argv = sys.argv
sys.argv = ['collector.py', '--username', 'dummy', '--password', 'dummy', '--api', '0.0.0.0', 
            '--sysname', 'dummy', '--sysid', 'dummy', '--doNotPost', '--dbAddress', 'dummy:8086']

import collector

# Restore arguments
sys.argv = original_argv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
LOG = logging.getLogger("test_replay")

class ReplaySession:
    def __init__(self, capture_dir):
        self.capture_dir = capture_dir
        self.captures = []
        self._load_captures()
        self.headers = {}

    def _load_captures(self):
        files = glob.glob(os.path.join(self.capture_dir, "*.json"))
        for f in sorted(files):
            try:
                with open(f, 'r') as fp:
                    data = json.load(fp)
                    self.captures.append(data)
            except Exception as e:
                LOG.error(f"Failed to load capture {f}: {e}")
        LOG.info(f"Loaded {len(self.captures)} capture files")

    def get(self, url, **kwargs):
        # Find matching capture
        # Heuristic: Match URL suffix
        # We consume the capture to allow simulating time progression (next call gets next capture)
        for i, capture in enumerate(self.captures):
            cap_url = capture.get('url', '')
            if url in cap_url or cap_url.endswith(url):
                # Found a match
                LOG.info(f"Replay match: {url} -> {cap_url} (Sequence {i})")
                
                # Use this capture and remove it from the list so we don't reuse it
                # effectively advancing the "timeline" for this request type
                self.captures.pop(i)
                
                resp = MagicMock()
                resp.status_code = capture['response']['status_code']
                
                body_content = capture['response']['body']
                # If body is a string, try to parse it as JSON to return via .json()
                if isinstance(body_content, str):
                    try:
                        json_body = json.loads(body_content)
                    except json.JSONDecodeError:
                        json_body = body_content
                else:
                    json_body = body_content
                    
                resp.json.return_value = json_body
                resp.text = body_content if isinstance(body_content, str) else json.dumps(body_content)
                return resp
        
        LOG.warning(f"No capture found for URL: {url}")
        resp = MagicMock()
        resp.status_code = 404
        resp.json.side_effect = ValueError("No capture found")
        return resp

def run_tests(capture_dir):
    # Setup collector globals
    collector.sys_id = "test_sys_id"
    collector.sys_name = "test_sys_name"
    collector.CMD = MagicMock()
    collector.CMD.api = ['1.2.3.4']  # Set API IP for get_controller
    collector.CMD.include = None # Include all
    collector.CMD.realtime = True # Enable realtime testing
    collector.CMD.showVolumeMetrics = True
    collector.CMD.output = 'influxdb'
    collector.INFLUX_WRITE_ENABLED = True
    collector.PROMETHEUS_AVAILABLE = False
    
    # Mock InfluxDB client and write_to_outputs
    collector.write_to_outputs = MagicMock()
    
    # Mock global cache
    collector._MAPPABLE_OBJECTS_CACHE = {}
    collector._HOSTS_CACHE = {}
    
    # Define systems to test
    systems_to_test = [
        {'id': 'test_sys_id_1', 'name': 'array1'},
        {'id': 'test_sys_id_2', 'name': 'array2'}
    ]
    
    # Initialize Replay Session
    replay_session = ReplaySession(capture_dir)
    
    # Patch get_session to return our replay session
    with patch('collector.get_session', return_value=replay_session):
        
        for sys_info in systems_to_test:
            LOG.info(f"=== Testing System: {sys_info['name']} ({sys_info['id']}) ===")
            collector.sys_id = sys_info['id']
            collector.sys_name = sys_info['name']
            
            # Reset collector caches for isolation between systems
            collector._VOLUME_STATS_CACHE = {} 
            
            LOG.info(f"--- Iteration 1: Initialize Cache for {sys_info['name']} ---")
            collector.collect_volume_stats_realtime({'wwn': collector.sys_id, 'name': collector.sys_name})
            
            LOG.info(f"--- Iteration 2: Calculate Deltas for {sys_info['name']} ---")
            collector.collect_volume_stats_realtime({'wwn': collector.sys_id, 'name': collector.sys_name})
            
            # Verify output
            if collector.write_to_outputs.called:
                # Get the last call arguments
                args, _ = collector.write_to_outputs.call_args
                measurements = args[0]
                LOG.info(f"Generated {len(measurements)} measurements for {sys_info['name']}")
                
                if len(measurements) > 0:
                    sample = measurements[0]
                    LOG.info(f"Sample measurement for {sys_info['name']}: {json.dumps(sample, indent=2)}")
                    
                    # Basic Validation
                    fields = sample.get('fields', {})
                    if 'readIOps' not in fields:
                        LOG.error(f"FAILURE: 'readIOps' missing in fields for {sys_info['name']}")
                        sys.exit(1)
                    
                    # Check for float type (field coercion / standard type check)
                    if not isinstance(fields['readIOps'], float):
                        LOG.error(f"FAILURE: 'readIOps' is not float (got {type(fields['readIOps'])}) for {sys_info['name']}")
                        sys.exit(1)

                    LOG.info(f"SUCCESS: Validation passed for {sys_info['name']}")
            else:
                 LOG.warning(f"No measurements generated in Iteration 2 for {sys_info['name']} (Expected if delta calc worked)")
                 # Wait, if it worked, we SHOULD have measurements.
                 # Iteration 1 initializes cache (no output). Iteration 2 has delta (output).
                 # So if not called, that's a failure.
                 LOG.error(f"FAILURE: write_to_outputs not called for {sys_info['name']}")
                 sys.exit(1)
            
            # Reset mock for next iteration
            collector.write_to_outputs.reset_mock()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay SANtricity captures")
    parser.add_argument('--captures', required=True, help="Directory containing capture .json files")
    args = parser.parse_args()
    
    if not os.path.isdir(args.captures):
        LOG.error(f"Capture directory not found: {args.captures}")
        sys.exit(1)
        
    run_tests(args.captures)
