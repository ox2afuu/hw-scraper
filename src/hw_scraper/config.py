"""Configuration management for hw-scraper."""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from pydantic import ValidationError
from dotenv import load_dotenv

from hw_scraper.models import ScraperConfig, OrganizationScheme, BrowserProfile, WorkerConfig, WorkerType


class Config:
    """Configuration manager for the scraper."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration from file or defaults."""
        self.config_path = config_path or self._find_config_file()
        self.scraper_config = ScraperConfig()
        self.organization = OrganizationScheme()
        self.worker_config = WorkerConfig()
        self._custom_settings: Dict[str, Any] = {}
        
        # Load environment variables
        load_dotenv()
        
        # Load configuration if file exists
        if self.config_path and Path(self.config_path).exists():
            self._load_from_file()
        
        # Override with environment variables
        self._load_from_env()
    
    def _find_config_file(self) -> Optional[str]:
        """Find configuration file in common locations."""
        search_paths = [
            Path.cwd() / "config.py",
            Path.cwd() / "config.json",
            Path.home() / ".hw-scraper" / "config.py",
            Path.home() / ".config" / "hw-scraper" / "config.json",
        ]
        
        for path in search_paths:
            if path.exists():
                return str(path)
        
        return None
    
    def _load_from_file(self):
        """Load configuration from file."""
        path = Path(self.config_path)
        
        if path.suffix == '.py':
            self._load_python_config(path)
        elif path.suffix == '.json':
            self._load_json_config(path)
    
    def _load_python_config(self, path: Path):
        """Load configuration from Python file."""
        import importlib.util
        
        spec = importlib.util.spec_from_file_location("config", path)
        if spec and spec.loader:
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            
            # Extract configuration attributes
            if hasattr(config_module, 'SCRAPER_CONFIG'):
                self.scraper_config = ScraperConfig(**config_module.SCRAPER_CONFIG)
            
            if hasattr(config_module, 'ORGANIZATION'):
                self.organization = OrganizationScheme(**config_module.ORGANIZATION)
            
            if hasattr(config_module, 'WORKER_CONFIG'):
                self.worker_config = WorkerConfig(**config_module.WORKER_CONFIG)
            
            if hasattr(config_module, 'CUSTOM'):
                self._custom_settings = config_module.CUSTOM
    
    def _load_json_config(self, path: Path):
        """Load configuration from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        
        if 'scraper' in data:
            self.scraper_config = ScraperConfig(**data['scraper'])
        
        if 'organization' in data:
            self.organization = OrganizationScheme(**data['organization'])
        
        if 'worker' in data:
            self.worker_config = WorkerConfig(**data['worker'])
        
        if 'custom' in data:
            self._custom_settings = data['custom']
    
    def _load_from_env(self):
        """Override configuration with environment variables."""
        # Download path
        if download_path := os.getenv('HW_SCRAPER_DOWNLOAD_PATH'):
            self.scraper_config.download_path = Path(download_path)
        
        # Base URL
        if base_url := os.getenv('HW_SCRAPER_BASE_URL'):
            self.scraper_config.base_url = base_url
        
        # Rate limit
        if rate_limit := os.getenv('HW_SCRAPER_RATE_LIMIT'):
            self.scraper_config.rate_limit = float(rate_limit)
        
        # Browser profile
        if browser := os.getenv('HW_SCRAPER_BROWSER'):
            try:
                self.scraper_config.browser_profile = BrowserProfile[browser.upper()]
            except KeyError:
                pass
        
        # Parallel downloads
        if parallel := os.getenv('HW_SCRAPER_PARALLEL'):
            self.scraper_config.parallel_downloads = int(parallel)
        
        # SSL verification
        if verify_ssl := os.getenv('HW_SCRAPER_VERIFY_SSL'):
            self.scraper_config.verify_ssl = verify_ssl.lower() in ('true', '1', 'yes')
        
        # Worker configuration
        if max_workers := os.getenv('HW_SCRAPER_MAX_WORKERS'):
            self.worker_config.max_workers = int(max_workers)
        
        if worker_type := os.getenv('HW_SCRAPER_WORKER_TYPE'):
            try:
                self.worker_config.worker_type = WorkerType[worker_type.upper()]
            except KeyError:
                pass
        
        if conn_pool := os.getenv('HW_SCRAPER_CONNECTION_POOL_SIZE'):
            self.worker_config.connection_pool_size = int(conn_pool)
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        # Check custom settings first
        if key in self._custom_settings:
            return self._custom_settings[key]
        
        # Check scraper config
        if hasattr(self.scraper_config, key):
            return getattr(self.scraper_config, key)
        
        # Check organization config
        if hasattr(self.organization, key):
            return getattr(self.organization, key)
        
        # Check worker config
        if hasattr(self.worker_config, key):
            return getattr(self.worker_config, key)
        
        return default
    
    def set(self, key: str, value: Any):
        """Set configuration value."""
        # Try to set on scraper config
        if hasattr(self.scraper_config, key):
            setattr(self.scraper_config, key, value)
        # Try to set on organization config
        elif hasattr(self.organization, key):
            setattr(self.organization, key, value)
        # Try to set on worker config
        elif hasattr(self.worker_config, key):
            setattr(self.worker_config, key, value)
        else:
            # Store in custom settings
            self._custom_settings[key] = value
    
    def update(self, data: Dict[str, Any]):
        """Update configuration from dictionary."""
        if 'scraper' in data:
            for key, value in data['scraper'].items():
                if hasattr(self.scraper_config, key):
                    setattr(self.scraper_config, key, value)
        
        if 'organization' in data:
            for key, value in data['organization'].items():
                if hasattr(self.organization, key):
                    setattr(self.organization, key, value)
        
        if 'worker' in data:
            for key, value in data['worker'].items():
                if hasattr(self.worker_config, key):
                    setattr(self.worker_config, key, value)
        
        if 'custom' in data:
            self._custom_settings.update(data['custom'])
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            'scraper': self.scraper_config.dict(),
            'organization': self.organization.dict(),
            'worker': self.worker_config.dict(),
            'custom': self._custom_settings
        }
    
    def save(self, path: Optional[str] = None):
        """Save configuration to file."""
        save_path = Path(path or self.config_path or './config.json')
        
        if save_path.suffix == '.py':
            self._save_python_config(save_path)
        else:
            self._save_json_config(save_path)
    
    def _save_python_config(self, path: Path):
        """Save configuration as Python file."""
        config_str = '''"""Configuration file for hw-scraper."""

# Scraper configuration
SCRAPER_CONFIG = {
'''
        for key, value in self.scraper_config.dict().items():
            if isinstance(value, Path):
                config_str += f"    '{key}': '{value}',\n"
            elif isinstance(value, str):
                config_str += f"    '{key}': '{value}',\n"
            else:
                config_str += f"    '{key}': {value},\n"
        
        config_str += '''}

# File organization settings
ORGANIZATION = {
'''
        for key, value in self.organization.dict().items():
            if isinstance(value, str):
                config_str += f"    '{key}': '{value}',\n"
            else:
                config_str += f"    '{key}': {value},\n"
        
        config_str += '''}

# Worker pool configuration
WORKER_CONFIG = {
'''
        for key, value in self.worker_config.dict().items():
            if isinstance(value, str):
                config_str += f"    '{key}': '{value}',\n"
            else:
                config_str += f"    '{key}': {value},\n"
        
        config_str += '''}

# Custom settings
CUSTOM = {
'''
        for key, value in self._custom_settings.items():
            if isinstance(value, str):
                config_str += f"    '{key}': '{value}',\n"
            else:
                config_str += f"    '{key}': {value},\n"
        
        config_str += '}\n'
        
        with open(path, 'w') as f:
            f.write(config_str)
    
    def _save_json_config(self, path: Path):
        """Save configuration as JSON file."""
        data = self.to_dict()
        
        # Convert Path objects to strings
        def convert_paths(obj):
            if isinstance(obj, dict):
                return {k: convert_paths(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_paths(item) for item in obj]
            elif isinstance(obj, Path):
                return str(obj)
            else:
                return obj
        
        data = convert_paths(data)
        
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)


def load_config(config_path: Optional[str] = None) -> Config:
    """Load configuration from file or create default."""
    return Config(config_path)


def create_default_config(path: str = './config.py'):
    """Create a default configuration file."""
    config = Config()
    
    # Set some sensible defaults
    config.scraper_config.download_path = Path('./downloads')
    config.scraper_config.max_retries = 3
    config.scraper_config.rate_limit = 0.5
    config.scraper_config.parallel_downloads = 3
    config.scraper_config.browser_profile = 'chrome120'
    
    config.organization.by_course = True
    config.organization.by_type = True
    config.organization.sanitize_names = True
    
    config.worker_config.max_workers = 3
    config.worker_config.worker_type = 'thread'
    config.worker_config.connection_pool_size = 10
    config.worker_config.enable_checkpointing = True
    
    # Save the configuration
    config.save(path)