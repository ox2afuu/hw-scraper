"""Base crawler interface and common functionality."""

from abc import ABC, abstractmethod
from typing import Set, List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from urllib.parse import urlparse, urljoin
from datetime import datetime
import time
import logging

from curl_cffi import requests
from lxml import html

from hw_scraper.config import Config


@dataclass
class CrawlResult:
    """Result of a crawling operation."""
    start_url: str
    discovered_urls: Set[str] = field(default_factory=set)
    visited_urls: Set[str] = field(default_factory=set)
    failed_urls: Dict[str, str] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    max_depth_reached: int = 0

    @property
    def duration(self) -> float:
        """Get crawl duration in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate of crawled URLs."""
        total = len(self.visited_urls) + len(self.failed_urls)
        if total == 0:
            return 0.0
        return len(self.visited_urls) / total


class BaseCrawler(ABC):
    """Abstract base class for web crawlers."""

    def __init__(
        self,
        config: Config,
        session: Optional[requests.Session] = None,
        respect_robots: bool = True,
        max_depth: int = -1,
        max_urls: int = -1,
        allowed_domains: Optional[List[str]] = None,
        url_filter: Optional[Callable[[str], bool]] = None
    ):
        """
        Initialize base crawler.

        Args:
            config: Application configuration
            session: HTTP session to use (creates new if None)
            respect_robots: Whether to respect robots.txt
            max_depth: Maximum crawl depth (-1 for unlimited)
            max_urls: Maximum URLs to crawl (-1 for unlimited)
            allowed_domains: List of allowed domains to crawl
            url_filter: Custom URL filter function
        """
        self.config = config
        self.session = session or self._create_session()
        self.respect_robots = respect_robots
        self.max_depth = max_depth
        self.max_urls = max_urls
        self.allowed_domains = allowed_domains
        self.url_filter = url_filter

        self.visited_urls: Set[str] = set()
        self.discovered_urls: Set[str] = set()
        self.failed_urls: Dict[str, str] = {}

        self.logger = logging.getLogger(self.__class__.__name__)

    def _create_session(self) -> requests.Session:
        """Create a new HTTP session with proper configuration."""
        return requests.Session(
            impersonate='chrome120',
            timeout=self.config.scraper_config.timeout,
            verify=self.config.scraper_config.verify_ssl
        )

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for consistent comparison."""
        parsed = urlparse(url.lower())

        # Remove fragment
        url_without_fragment = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            url_without_fragment += f"?{parsed.query}"

        # Remove trailing slash from path
        if url_without_fragment.endswith('/') and len(parsed.path) > 1:
            url_without_fragment = url_without_fragment[:-1]

        return url_without_fragment

    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid for crawling."""
        try:
            parsed = urlparse(url)

            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                return False

            # Only HTTP(S) URLs
            if parsed.scheme not in ('http', 'https'):
                return False

            # Check domain restrictions
            if self.allowed_domains:
                domain = parsed.netloc.lower()
                if not any(domain.endswith(allowed) for allowed in self.allowed_domains):
                    return False

            # Apply custom filter
            if self.url_filter and not self.url_filter(url):
                return False

            # Skip common non-HTML resources
            path = parsed.path.lower()
            skip_extensions = (
                '.jpg', '.jpeg', '.png', '.gif', '.pdf', '.zip',
                '.exe', '.dmg', '.mp3', '.mp4', '.avi', '.mov'
            )
            if any(path.endswith(ext) for ext in skip_extensions):
                return False

            return True

        except Exception:
            return False

    def _fetch_page(self, url: str) -> Optional[str]:
        """Fetch page content."""
        try:
            # Apply rate limiting
            time.sleep(self.config.scraper_config.rate_limit)

            response = self.session.get(url)
            response.raise_for_status()

            # Only process HTML content
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type:
                return None

            return response.text

        except Exception as e:
            self.logger.debug(f"Failed to fetch {url}: {e}")
            self.failed_urls[url] = str(e)
            return None

    def _extract_links(self, html_content: str, base_url: str) -> Set[str]:
        """Extract all links from HTML content."""
        links = set()

        try:
            tree = html.fromstring(html_content)

            # Extract href attributes
            for element in tree.xpath('//a[@href]'):
                href = element.get('href')
                if href:
                    # Make URL absolute
                    absolute_url = urljoin(base_url, href)
                    normalized_url = self._normalize_url(absolute_url)

                    if self._is_valid_url(normalized_url):
                        links.add(normalized_url)

            # Also extract from other sources
            for element in tree.xpath('//link[@href]'):
                href = element.get('href')
                rel = element.get('rel', '')

                # Only follow certain link types
                if href and rel in ('alternate', 'canonical'):
                    absolute_url = urljoin(base_url, href)
                    normalized_url = self._normalize_url(absolute_url)

                    if self._is_valid_url(normalized_url):
                        links.add(normalized_url)

        except Exception as e:
            self.logger.debug(f"Failed to extract links from {base_url}: {e}")

        return links

    def _should_crawl_url(self, url: str) -> bool:
        """Check if URL should be crawled."""
        normalized_url = self._normalize_url(url)

        # Already visited
        if normalized_url in self.visited_urls:
            return False

        # Already failed
        if normalized_url in self.failed_urls:
            return False

        # Check max URLs limit
        if self.max_urls > 0 and len(self.visited_urls) >= self.max_urls:
            return False

        return self._is_valid_url(normalized_url)

    @abstractmethod
    def crawl(self, start_url: str) -> CrawlResult:
        """
        Crawl website starting from given URL.

        Args:
            start_url: URL to start crawling from

        Returns:
            CrawlResult containing discovered URLs and statistics
        """
        pass

    def reset(self):
        """Reset crawler state for new crawl."""
        self.visited_urls.clear()
        self.discovered_urls.clear()
        self.failed_urls.clear()