"""Authentication management for hw-scraper."""

import os
import json
import getpass
from typing import Optional, Dict, Any
from pathlib import Path
import keyring
from lxml import etree

from hw_scraper.models import Credentials, AuthMethod
from hw_scraper.config import Config


class AuthManager:
    """Manages authentication credentials and sessions."""
    
    SERVICE_NAME = "hw-scraper"
    
    def __init__(self, config: Config):
        """Initialize authentication manager."""
        self.config = config
        self.credentials = Credentials()
        self._session_cookies: Dict[str, str] = {}
    
    def load_from_method(self, method: str) -> bool:
        """Load credentials using specified method."""
        auth_method = AuthMethod(method)
        
        if auth_method == AuthMethod.ENV:
            return self.load_from_env()
        elif auth_method == AuthMethod.KEYRING:
            return self.load_from_keyring()
        elif auth_method == AuthMethod.COOKIES:
            # Cookies should be loaded separately with load_cookies()
            return bool(self._session_cookies)
        elif auth_method == AuthMethod.PROMPT:
            return self.prompt_credentials()
        
        return False
    
    def load_from_env(self) -> bool:
        """Load credentials from environment variables."""
        username = os.getenv('HW_SCRAPER_USERNAME') or os.getenv('PRIMARY_USER')
        password = os.getenv('HW_SCRAPER_PASSWORD') or os.getenv('PRIMARY_PASS')
        session_token = os.getenv('HW_SCRAPER_TOKEN')
        
        if username and password:
            self.credentials.username = username
            self.credentials.password = password
            if session_token:
                self.credentials.session_token = session_token
            return True
        
        # Check for cookies in environment
        cookies_env = os.getenv('HW_SCRAPER_COOKIES')
        if cookies_env:
            try:
                self._session_cookies = json.loads(cookies_env)
                self.credentials.cookies = self._session_cookies
                return True
            except json.JSONDecodeError:
                pass
        
        return False
    
    def load_from_keyring(self) -> bool:
        """Load credentials from system keyring."""
        try:
            username = keyring.get_password(self.SERVICE_NAME, "username")
            password = keyring.get_password(self.SERVICE_NAME, "password")
            
            if username and password:
                self.credentials.username = username
                self.credentials.password = password
                
                # Try to load session token if available
                token = keyring.get_password(self.SERVICE_NAME, "session_token")
                if token:
                    self.credentials.session_token = token
                
                # Try to load cookies if available
                cookies_str = keyring.get_password(self.SERVICE_NAME, "cookies")
                if cookies_str:
                    try:
                        self._session_cookies = json.loads(cookies_str)
                        self.credentials.cookies = self._session_cookies
                    except json.JSONDecodeError:
                        pass
                
                return True
        except Exception:
            pass
        
        return False
    
    def save_to_keyring(self) -> bool:
        """Save credentials to system keyring."""
        try:
            if self.credentials.username:
                keyring.set_password(self.SERVICE_NAME, "username", self.credentials.username)
            
            if self.credentials.password:
                keyring.set_password(self.SERVICE_NAME, "password", self.credentials.password)
            
            if self.credentials.session_token:
                keyring.set_password(self.SERVICE_NAME, "session_token", self.credentials.session_token)
            
            if self._session_cookies:
                keyring.set_password(self.SERVICE_NAME, "cookies", json.dumps(self._session_cookies))
            
            return True
        except Exception:
            return False
    
    def prompt_credentials(self) -> bool:
        """Prompt user for credentials interactively."""
        print("Please enter your credentials:")
        
        username = input("Username: ").strip()
        if not username:
            print("Username cannot be empty")
            return False
        
        password = getpass.getpass("Password: ")
        if not password:
            print("Password cannot be empty")
            return False
        
        self.credentials.username = username
        self.credentials.password = password
        
        # Ask if user wants to save credentials
        save = input("Save credentials to keyring? (y/n): ").lower()
        if save == 'y':
            self.save_to_keyring()
        
        return True
    
    def load_cookies(self, filepath: str) -> bool:
        """Load cookies from file (JSON or XML format)."""
        path = Path(filepath)
        
        if not path.exists():
            return False
        
        try:
            if path.suffix.lower() == '.json':
                return self._load_json_cookies(path)
            elif path.suffix.lower() == '.xml':
                return self._load_xml_cookies(path)
            else:
                # Try to detect format
                with open(path, 'r') as f:
                    content = f.read().strip()
                    if content.startswith('{') or content.startswith('['):
                        return self._load_json_cookies(path)
                    elif content.startswith('<'):
                        return self._load_xml_cookies(path)
        except Exception as e:
            print(f"Error loading cookies: {e}")
            return False
        
        return False
    
    def _load_json_cookies(self, path: Path) -> bool:
        """Load cookies from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)
        
        if isinstance(data, dict):
            # Direct cookie dictionary
            self._session_cookies = data
        elif isinstance(data, list):
            # Browser cookie format
            self._session_cookies = {}
            for cookie in data:
                if 'name' in cookie and 'value' in cookie:
                    self._session_cookies[cookie['name']] = cookie['value']
        else:
            return False
        
        self.credentials.cookies = self._session_cookies
        return True
    
    def _load_xml_cookies(self, path: Path) -> bool:
        """Load cookies from XML file."""
        tree = etree.parse(str(path))
        root = tree.getroot()
        
        self._session_cookies = {}
        
        # Support multiple XML formats
        # Format 1: <cookies><cookie name="..." value="..." /></cookies>
        for cookie in root.xpath('//cookie'):
            name = cookie.get('name')
            value = cookie.get('value')
            if name and value:
                self._session_cookies[name] = value
        
        # Format 2: <cookies><name>value</name></cookies>
        if not self._session_cookies:
            for child in root:
                self._session_cookies[child.tag] = child.text or ''
        
        self.credentials.cookies = self._session_cookies
        return bool(self._session_cookies)
    
    def save_cookies(self, filepath: str, format: str = 'json') -> bool:
        """Save current cookies to file."""
        path = Path(filepath)
        
        try:
            if format == 'json' or path.suffix.lower() == '.json':
                with open(path, 'w') as f:
                    json.dump(self._session_cookies, f, indent=2)
            elif format == 'xml' or path.suffix.lower() == '.xml':
                root = etree.Element('cookies')
                for name, value in self._session_cookies.items():
                    cookie = etree.SubElement(root, 'cookie')
                    cookie.set('name', name)
                    cookie.set('value', value)
                
                tree = etree.ElementTree(root)
                tree.write(str(path), pretty_print=True, xml_declaration=True, encoding='UTF-8')
            else:
                return False
            
            return True
        except Exception as e:
            print(f"Error saving cookies: {e}")
            return False
    
    def update_cookies(self, cookies: Dict[str, str]):
        """Update session cookies."""
        self._session_cookies.update(cookies)
        self.credentials.cookies = self._session_cookies
    
    def get_cookies(self) -> Dict[str, str]:
        """Get current session cookies."""
        return self._session_cookies.copy()
    
    def clear_credentials(self):
        """Clear all stored credentials."""
        self.credentials = Credentials()
        self._session_cookies = {}
        
        # Try to clear from keyring
        try:
            keyring.delete_password(self.SERVICE_NAME, "username")
            keyring.delete_password(self.SERVICE_NAME, "password")
            keyring.delete_password(self.SERVICE_NAME, "session_token")
            keyring.delete_password(self.SERVICE_NAME, "cookies")
        except Exception:
            pass
    
    def is_authenticated(self) -> bool:
        """Check if we have valid authentication."""
        return bool(
            (self.credentials.username and self.credentials.password) or
            self.credentials.session_token or
            self._session_cookies
        )