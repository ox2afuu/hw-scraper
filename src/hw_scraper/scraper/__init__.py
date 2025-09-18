"""Enhanced scraper module with HTML and JavaScript support."""

from .html_scraper import HTMLScraper
from .js_renderer import JSRenderer, JSDetector
from .xpath_extractor import XPathExtractor

__all__ = [
    'HTMLScraper',
    'JSRenderer',
    'JSDetector',
    'XPathExtractor'
]