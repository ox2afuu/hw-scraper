"""
hw-scraper: A web scraper for course materials with anti-detection capabilities.

This module provides both a CLI interface and a scriptable API for downloading
course materials while bypassing bot detection using TLS fingerprinting.
"""

from hw_scraper.scraper import Scraper
from hw_scraper.async_scraper import AsyncScraper
from hw_scraper.config import Config, load_config
from hw_scraper.auth import AuthManager
from hw_scraper.models import (
    Course, CourseFile, DownloadResult, ScrapeResult,
    FileType, AuthMethod, BrowserProfile,
    WorkerType, WorkerConfig, BatchTask, BatchResult
)
from hw_scraper.downloader import DownloadManager
from hw_scraper.organizer import FileOrganizer
from hw_scraper.parser import ContentParser
from hw_scraper.batch_processor import BatchProcessor, batch_scrape_courses
from hw_scraper.worker_pool import WorkerPool

__version__ = "0.1.0"
__author__ = "ox2a-fuu"

__all__ = [
    # Main classes
    'Scraper',
    'AsyncScraper',
    'Config',
    'AuthManager',
    'DownloadManager',
    'FileOrganizer',
    'ContentParser',
    'BatchProcessor',
    'WorkerPool',
    
    # Models
    'Course',
    'CourseFile',
    'DownloadResult',
    'ScrapeResult',
    'FileType',
    'AuthMethod',
    'BrowserProfile',
    'WorkerType',
    'WorkerConfig',
    'BatchTask',
    'BatchResult',
    
    # Functions
    'load_config',
    'create_scraper',
    'quick_scrape',
    'batch_scrape_courses'
]


def create_scraper(config_path: str = None, auth_method: str = 'env',
                  impersonate: str = 'chrome') -> Scraper:
    """
    Create a configured scraper instance.
    
    Args:
        config_path: Path to configuration file
        auth_method: Authentication method ('env', 'keyring', 'cookies', 'prompt')
        impersonate: Browser to impersonate ('chrome', 'firefox', 'safari', 'edge')
    
    Returns:
        Configured Scraper instance
    
    Example:
        >>> scraper = create_scraper(auth_method='env')
        >>> result = scraper.scrape_course('https://course.edu/cs101')
    """
    config = load_config(config_path)
    auth_manager = AuthManager(config)
    auth_manager.load_from_method(auth_method)
    
    return Scraper(config, auth_manager, impersonate)


def quick_scrape(url: str, output_dir: str = './downloads',
                auth_method: str = 'env', organize: bool = True) -> ScrapeResult:
    """
    Quick scrape function for simple use cases.
    
    Args:
        url: Course URL to scrape
        output_dir: Directory for downloaded files
        auth_method: Authentication method
        organize: Whether to organize files by type
    
    Returns:
        ScrapeResult with download information
    
    Example:
        >>> result = quick_scrape('https://course.edu/cs101')
        >>> print(f"Downloaded {result.files_downloaded} files")
    """
    scraper = create_scraper(auth_method=auth_method)
    
    try:
        result = scraper.scrape_course(url, output_dir, organize)
        return result
    finally:
        scraper.close()