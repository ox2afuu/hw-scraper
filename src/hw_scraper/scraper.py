"""Core scraping engine using curl-cffi."""

import time
import random
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin, urlparse
from pathlib import Path
from datetime import datetime
from curl_cffi import requests
from curl_cffi.requests import Session

from hw_scraper.config import Config
from hw_scraper.auth import AuthManager
from hw_scraper.models import (
    Course, CourseFile, ScrapeResult, BrowserProfile,
    FileType
)
from hw_scraper.parser import ContentParser
from hw_scraper.organizer import FileOrganizer
from hw_scraper.downloader import DownloadManager


class Scraper:
    """Main scraper class using curl-cffi for TLS fingerprinting bypass."""
    
    # Browser impersonation mappings
    BROWSER_IMPERSONATIONS = {
        'chrome': 'chrome120',
        'firefox': 'firefox120',
        'safari': 'safari17_0',
        'edge': 'edge120'
    }
    
    def __init__(self, config: Config, auth_manager: AuthManager, impersonate: str = 'chrome'):
        """Initialize the scraper."""
        self.config = config
        self.auth_manager = auth_manager
        self.impersonate = self.BROWSER_IMPERSONATIONS.get(impersonate, 'chrome120')
        self.session: Optional[Session] = None
        self.parser = ContentParser()
        self.organizer = FileOrganizer(config)
        self.downloader = DownloadManager(config)
        
        self._initialize_session()
    
    def _initialize_session(self):
        """Initialize curl-cffi session with browser impersonation."""
        self.session = requests.Session(
            impersonate=self.impersonate,
            timeout=self.config.scraper_config.timeout,
            verify=self.config.scraper_config.verify_ssl,
            max_redirects=10 if self.config.scraper_config.follow_redirects else 0
        )
        
        # Set cookies if available
        if self.auth_manager.get_cookies():
            for name, value in self.auth_manager.get_cookies().items():
                self.session.cookies.set(name, value)
        
        # Set random user agent
        if self.config.scraper_config.user_agents:
            ua = random.choice(self.config.scraper_config.user_agents)
            self.session.headers['User-Agent'] = ua
    
    def _make_request(self, url: str, method: str = 'GET', **kwargs) -> requests.Response:
        """Make HTTP request with retry logic and rate limiting."""
        if not self.session:
            self._initialize_session()
        
        # Apply rate limiting
        time.sleep(self.config.scraper_config.rate_limit)
        
        # Retry logic
        last_error = None
        for attempt in range(self.config.scraper_config.max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff
                    time.sleep(self.config.scraper_config.retry_delay * (2 ** attempt))
                
                response = self.session.request(method, url, **kwargs)
                response.raise_for_status()
                
                # Update cookies from response
                if response.cookies:
                    cookies = {k: v for k, v in response.cookies.items()}
                    self.auth_manager.update_cookies(cookies)
                
                return response
                
            except Exception as e:
                last_error = e
                if attempt < self.config.scraper_config.max_retries - 1:
                    # Try different browser profile on retry
                    profiles = list(self.BROWSER_IMPERSONATIONS.values())
                    self.impersonate = random.choice(profiles)
                    self._initialize_session()
        
        raise last_error or Exception(f"Failed to fetch {url}")
    
    def login(self, login_url: str, form_data: Optional[Dict[str, str]] = None) -> bool:
        """Perform login using credentials."""
        if not self.auth_manager.is_authenticated():
            return False
        
        # Prepare login data
        if not form_data:
            form_data = {
                'username': self.auth_manager.credentials.username,
                'password': self.auth_manager.credentials.password
            }
        else:
            # Update with credentials
            if self.auth_manager.credentials.username:
                form_data['username'] = self.auth_manager.credentials.username
            if self.auth_manager.credentials.password:
                form_data['password'] = self.auth_manager.credentials.password
        
        try:
            response = self._make_request(login_url, method='POST', data=form_data)
            
            # Check if login was successful (customize based on site)
            # Usually check for redirect, specific cookies, or content
            if response.status_code == 200 or response.status_code == 302:
                # Save session cookies
                if response.cookies:
                    cookies = {k: v for k, v in response.cookies.items()}
                    self.auth_manager.update_cookies(cookies)
                return True
        except Exception as e:
            print(f"Login failed: {e}")
        
        return False
    
    def scrape_course(self, url: str, output_dir: str = './downloads', organize: bool = True) -> ScrapeResult:
        """Scrape all materials from a course page."""
        start_time = time.time()
        
        result = ScrapeResult(
            course_name="Unknown Course",
            course_url=url,
            files_found=0,
            files_downloaded=0,
            files_failed=0,
            duration=0
        )
        
        try:
            # Fetch course page
            response = self._make_request(url)
            
            # Parse course information and files
            course_info = self.parser.parse_course_page(response.text, url)
            result.course_name = course_info.get('name', 'Unknown Course')
            
            # Extract all downloadable links
            files = self.parser.extract_course_files(response.text, url)
            result.files_found = len(files)
            
            # Set up output directory
            output_path = Path(output_dir)
            if organize:
                output_path = self.organizer.setup_course_directory(
                    output_path,
                    result.course_name
                )
            
            # Download files
            download_results = self.downloader.download_batch(
                [f.url for f in files],
                str(output_path)
            )
            
            # Process results
            for i, download_result in enumerate(download_results):
                if download_result.success:
                    result.files_downloaded += 1
                    
                    # Organize file if needed
                    if organize and download_result.local_path:
                        organized_path = self.organizer.organize_file(
                            download_result.local_path,
                            files[i].type,
                            result.course_name
                        )
                        files[i].local_path = organized_path
                else:
                    result.files_failed += 1
                    if download_result.error:
                        result.errors.append(download_result.error)
            
            result.files = files
            
        except Exception as e:
            result.errors.append(str(e))
        
        result.duration = time.time() - start_time
        return result
    
    def list_courses(self, catalog_url: str) -> List[Course]:
        """List all available courses from a catalog page."""
        try:
            response = self._make_request(catalog_url)
            courses = self.parser.parse_course_catalog(response.text, catalog_url)
            return courses
        except Exception as e:
            print(f"Failed to fetch courses: {e}")
            return []
    
    def discover_courses(self, base_url: Optional[str] = None) -> List[Course]:
        """Discover available courses from base URL."""
        url = base_url or self.config.scraper_config.base_url
        
        if not url:
            raise ValueError("No base URL provided")
        
        # Try common course catalog paths
        catalog_paths = [
            '',
            '/courses',
            '/catalog',
            '/academics/courses',
            '/course-list'
        ]
        
        for path in catalog_paths:
            try:
                catalog_url = urljoin(str(url), path)
                courses = self.list_courses(catalog_url)
                if courses:
                    return courses
            except Exception:
                continue
        
        return []
    
    def scrape_file(self, url: str, output_path: str, file_type: Optional[FileType] = None) -> bool:
        """Scrape a single file."""
        try:
            # Detect file type if not provided
            if not file_type:
                file_type = self.parser.detect_file_type(url)
            
            # Download file
            result = self.downloader.download_file(url, output_path)
            
            return result.success
        except Exception as e:
            print(f"Failed to scrape file {url}: {e}")
            return False
    
    def close(self):
        """Close the scraper session."""
        if self.session:
            self.session.close()
            self.session = None