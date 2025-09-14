"""
Tests for the JSON reader module.
"""
import json
import logging
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.read.json_reader import JsonReader, read_system_config
from app.schema.models import SystemConfig


class TestJsonReader(unittest.TestCase):
    """Test cases for JsonReader class."""

    def setUp(self):
        """Set up test environment."""
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        
        # Sample system config data
        self.system_config_data = {
            "asupEnabled": True,
            "autoLoadBalancingEnabled": False,
            "chassisSerialNumber": "123456789",
            "driveCount": 24,
            "driveTypes": [
                {"driveMediaType": ["sas"]}
            ],
            "name": "test-system",
            "status": "optimal"
        }
        
        # Create test JSON file
        self.json_file = self.temp_path / "system_config.json"
        with open(self.json_file, 'w', encoding='utf-8') as f:
            json.dump(self.system_config_data, f)
            
    def tearDown(self):
        """Clean up after tests."""
        self.temp_dir.cleanup()
        
    def test_read_file(self):
        """Test reading a JSON file."""
        data = JsonReader.read_file(self.json_file)
        self.assertEqual(data["name"], "test-system")
        self.assertEqual(data["driveCount"], 24)
        
    def test_read_model_from_file(self):
        """Test reading and converting to a model."""
        system_config = JsonReader.read_model_from_file(self.json_file, SystemConfig)
        self.assertIsInstance(system_config, SystemConfig)
        self.assertEqual(system_config.name, "test-system")
        self.assertEqual(system_config.driveCount, 24)
        self.assertTrue(system_config.asupEnabled)
        
    def test_nonexistent_file(self):
        """Test reading a file that doesn't exist."""
        nonexistent_file = self.temp_path / "nonexistent.json"
        data = JsonReader.read_file(nonexistent_file)
        self.assertEqual(data, {})
        
    def test_invalid_json(self):
        """Test reading a file with invalid JSON."""
        invalid_json_file = self.temp_path / "invalid.json"
        with open(invalid_json_file, 'w', encoding='utf-8') as f:
            f.write("This is not valid JSON")
            
        data = JsonReader.read_file(invalid_json_file)
        self.assertEqual(data, {})
        
    def test_convenience_function(self):
        """Test convenience function for reading system config."""
        system_config = read_system_config(self.json_file)
        self.assertIsInstance(system_config, SystemConfig)
        self.assertEqual(system_config.name, "test-system")


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    unittest.main()