# -----------------------------------------------------------------------------
# Copyright (c) 2025 E-Series Perf Analyzer (scaleoutSean@Github and (pre v3.1.0) NetApp, Inc)
# Licensed under the MIT License. See LICENSE in project root for details.
# -----------------------------------------------------------------------------

from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field
import yaml
import os
import logging
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

logger = logging.getLogger(__name__)

# Ensure .env from parent directory is loaded for local CLI runs
if load_dotenv:
    load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# InfluxDB global options for all client instances shouldn't be set to sub-second precision because it's unnecessary
INFLUXDB_WRITE_PRECISION = 's'  # always use seconds, there's no point in finer granularity with SANtricity metrics

class FileConfig(BaseSettings):
    # InfluxDB settings
    inf_url: Optional[str] = None
    inf_database: Optional[str] = None
    inf_token: Optional[str] = None
    
    # TLS settings
    tls_ca: Optional[str] = None
    tls_ca_path: Optional[str] = None  # Added missing field
    
    # E-Series API settings
    api_endpoints: Optional[List[str]] = None
    username: Optional[str] = None
    password: Optional[str] = None
    
    # Collection settings
    interval_time: Optional[float] = 60.0
    drives_collection_interval: Optional[int] = 604800  # 1 week in seconds
    controller_collection_interval: Optional[int] = 3600  # 1 hour in seconds
    
    # Advanced settings
    threads: Optional[int] = 4
    tls_validation: Optional[str] = "strict"
    metrics: Optional[List[str]] = None
    
    # JSON mode settings (added missing fields)
    to_json: Optional[str] = None
    from_json: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True



class EnvConfig(BaseSettings):
    # Core InfluxDB settings
    INF_URL: str = Field(default="https://localhost:8181")
    INF_DATABASE: str = Field(default="eseries")
    INF_TOKEN: Optional[str] = Field(default=None)
    
    # NetApp E-Series settings (optional - not needed for --fromJson)
    API_ENDPOINTS: List[str] = Field(default_factory=list, env='API')
    USERNAME: Optional[str] = Field(default="admin", env='USERNAME')
    PASSWORD: Optional[str] = Field(default=None, env='PASSWORD')
    
    # Optional settings with smart defaults
    TLS_CA_PATH: Optional[str] = Field(default=None, env='TLS_CA')
    TLS_VALIDATION: str = Field(default="strict", env='TLS_VALIDATION')
    INTERVAL_TIME: float = Field(default=60.0, env='INTERVAL_TIME')
    
    # Advanced settings (rarely changed)
    THREADS: int = Field(default=4, env='THREADS')
    TO_JSON: Optional[str] = Field(default=None, env='TO_JSON')
    FROM_JSON: Optional[str] = Field(default=None, env='FROM_JSON')
    
    # Collection intervals for static or less important measurements
    DRIVES_COLLECTION_INTERVAL: int = Field(default=604800, env='DRIVES_COLLECTION_INTERVAL')  # 1 week in seconds
    CONTROLLER_COLLECTION_INTERVAL: int = Field(default=3600, env='CONTROLLER_COLLECTION_INTERVAL')  # 1 hour in seconds

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = 'ignore'  # Ignore extra fields in .env that aren't defined in the model



class Settings:
    def __init__(self, config_file: Optional[str] = None, from_env: bool = False):
        self.from_env = from_env
        
        if from_env:
            logger.debug("Loading configuration from environment variables")
            self._env_config = EnvConfig()
            
            # Core InfluxDB settings - using new field names
            self.influxdb_url = self._env_config.INF_URL
            self.influxdb_database = self._env_config.INF_DATABASE
            self.influxdb_token = self._env_config.INF_TOKEN
            
            # NetApp E-Series settings
            self.api_endpoints = self._env_config.API_ENDPOINTS
            self.username = self._env_config.USERNAME
            self.password = self._env_config.PASSWORD
            
            # Other settings
            self.tls_ca_path = self._env_config.TLS_CA_PATH
            self.tls_validation = self._env_config.TLS_VALIDATION
            self.interval_time = self._env_config.INTERVAL_TIME
            self.threads = self._env_config.THREADS
            self.to_json = self._env_config.TO_JSON
            self.from_json = self._env_config.FROM_JSON
            self.drives_collection_interval = self._env_config.DRIVES_COLLECTION_INTERVAL
            self.controller_collection_interval = self._env_config.CONTROLLER_COLLECTION_INTERVAL
            
        else:
            # Load from YAML file
            logger.debug(f"Loading configuration from file: {config_file}")
            self._file_config = FileConfig()
            if config_file and os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    data = yaml.safe_load(f)
                    for key, value in data.items():
                        if hasattr(self._file_config, key):
                            setattr(self._file_config, key, value)
            
            # Map from FileConfig - using updated field names
            self.influxdb_url = self._file_config.inf_url
            self.influxdb_database = self._file_config.inf_database
            self.influxdb_token = self._file_config.inf_token
            
            # NetApp E-Series settings
            self.api_endpoints = self._file_config.api_endpoints or []
            self.username = self._file_config.username
            self.password = self._file_config.password
            
            # Other settings
            self.tls_ca_path = self._file_config.tls_ca_path
            self.tls_validation = self._file_config.tls_validation
            self.interval_time = self._file_config.interval_time
            self.threads = self._file_config.threads
            self.to_json = self._file_config.to_json
            self.from_json = self._file_config.from_json
            self.drives_collection_interval = self._file_config.drives_collection_interval
            self.controller_collection_interval = self._file_config.controller_collection_interval
