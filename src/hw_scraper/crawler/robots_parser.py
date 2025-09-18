"""Parser for robots.txt files to ensure crawler compliance."""

from typing import Optional, Dict, List, Set, Tuple
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import re
import time
import logging

from curl_cffi import requests


class RobotsParser:
    """Parser and enforcer of robots.txt rules."""

    def __init__(self, session: Optional[requests.Session] = None):
        """Initialize robots parser."""
        self.session = session or requests.Session(impersonate='chrome120')
        self.robots_cache: Dict[str, RobotFileParser] = {}
        self.sitemap_cache: Dict[str, List[str]] = {}
        self.crawl_delays: Dict[str, float] = {}
        self.logger = logging.getLogger(self.__class__.__name__)

    def _get_robots_url(self, url: str) -> str:
        """Get robots.txt URL for given URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def fetch_robots(self, url: str, user_agent: str = '*') -> Optional[RobotFileParser]:
        """
        Fetch and parse robots.txt for given URL.

        Args:
            url: Website URL
            user_agent: User agent string to check rules for

        Returns:
            RobotFileParser instance or None if not found
        """
        robots_url = self._get_robots_url(url)

        # Check cache
        if robots_url in self.robots_cache:
            return self.robots_cache[robots_url]

        try:
            response = self.session.get(robots_url, timeout=10)

            if response.status_code == 200:
                # Parse robots.txt
                rp = RobotFileParser()
                rp.set_url(robots_url)
                rp.parse(response.text.splitlines())

                # Cache the parser
                self.robots_cache[robots_url] = rp

                # Extract additional directives
                self._parse_extended_directives(response.text, robots_url, user_agent)

                return rp

            elif response.status_code == 404:
                # No robots.txt means everything is allowed
                self.logger.info(f"No robots.txt found for {robots_url}")
                return None

        except Exception as e:
            self.logger.warning(f"Failed to fetch robots.txt from {robots_url}: {e}")

        return None

    def _parse_extended_directives(self, robots_text: str, robots_url: str, user_agent: str):
        """Parse extended directives like Crawl-delay and Sitemap."""
        lines = robots_text.splitlines()
        current_user_agent = None
        domain = urlparse(robots_url).netloc

        for line in lines:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Parse user-agent
            if line.lower().startswith('user-agent:'):
                agent = line.split(':', 1)[1].strip()
                current_user_agent = agent
                continue

            # Only process directives for matching user-agent
            if current_user_agent and current_user_agent != '*' and current_user_agent != user_agent:
                continue

            # Parse Crawl-delay
            if line.lower().startswith('crawl-delay:'):
                try:
                    delay = float(line.split(':', 1)[1].strip())
                    self.crawl_delays[domain] = delay
                    self.logger.info(f"Crawl delay for {domain}: {delay}s")
                except ValueError:
                    pass

            # Parse Sitemap
            if line.lower().startswith('sitemap:'):
                sitemap_url = line.split(':', 1)[1].strip()
                if sitemap_url.startswith('http'):
                    if domain not in self.sitemap_cache:
                        self.sitemap_cache[domain] = []
                    self.sitemap_cache[domain].append(sitemap_url)
                    self.logger.info(f"Found sitemap: {sitemap_url}")

    def can_fetch(self, url: str, user_agent: str = '*') -> bool:
        """
        Check if URL can be fetched according to robots.txt.

        Args:
            url: URL to check
            user_agent: User agent string

        Returns:
            True if URL can be fetched, False otherwise
        """
        robots_url = self._get_robots_url(url)

        # Get or fetch robots.txt
        if robots_url in self.robots_cache:
            rp = self.robots_cache[robots_url]
        else:
            rp = self.fetch_robots(url, user_agent)

        # No robots.txt means everything is allowed
        if rp is None:
            return True

        # Check if URL is allowed
        return rp.can_fetch(user_agent, url)

    def get_crawl_delay(self, url: str) -> float:
        """
        Get crawl delay for given URL.

        Args:
            url: Website URL

        Returns:
            Crawl delay in seconds (0 if not specified)
        """
        domain = urlparse(url).netloc
        return self.crawl_delays.get(domain, 0.0)

    def get_sitemaps(self, url: str) -> List[str]:
        """
        Get sitemap URLs from robots.txt.

        Args:
            url: Website URL

        Returns:
            List of sitemap URLs
        """
        domain = urlparse(url).netloc

        # Fetch robots.txt if not in cache
        if domain not in self.sitemap_cache:
            self.fetch_robots(url)

        return self.sitemap_cache.get(domain, [])

    def get_allowed_paths(self, url: str, user_agent: str = '*') -> Set[str]:
        """
        Get explicitly allowed paths from robots.txt.

        Args:
            url: Website URL
            user_agent: User agent string

        Returns:
            Set of allowed path patterns
        """
        allowed = set()
        robots_url = self._get_robots_url(url)

        try:
            response = self.session.get(robots_url, timeout=10)
            if response.status_code == 200:
                lines = response.text.splitlines()
                current_user_agent = None

                for line in lines:
                    line = line.strip()

                    if line.lower().startswith('user-agent:'):
                        agent = line.split(':', 1)[1].strip()
                        current_user_agent = agent
                        continue

                    # Only process for matching user-agent
                    if current_user_agent and current_user_agent != '*' and current_user_agent != user_agent:
                        continue

                    # Look for Allow directives
                    if line.lower().startswith('allow:'):
                        path = line.split(':', 1)[1].strip()
                        if path:
                            allowed.add(path)

        except Exception as e:
            self.logger.debug(f"Failed to get allowed paths from {robots_url}: {e}")

        return allowed

    def get_disallowed_paths(self, url: str, user_agent: str = '*') -> Set[str]:
        """
        Get disallowed paths from robots.txt.

        Args:
            url: Website URL
            user_agent: User agent string

        Returns:
            Set of disallowed path patterns
        """
        disallowed = set()
        robots_url = self._get_robots_url(url)

        try:
            response = self.session.get(robots_url, timeout=10)
            if response.status_code == 200:
                lines = response.text.splitlines()
                current_user_agent = None

                for line in lines:
                    line = line.strip()

                    if line.lower().startswith('user-agent:'):
                        agent = line.split(':', 1)[1].strip()
                        current_user_agent = agent
                        continue

                    # Only process for matching user-agent
                    if current_user_agent and current_user_agent != '*' and current_user_agent != user_agent:
                        continue

                    # Look for Disallow directives
                    if line.lower().startswith('disallow:'):
                        path = line.split(':', 1)[1].strip()
                        if path:
                            disallowed.add(path)

        except Exception as e:
            self.logger.debug(f"Failed to get disallowed paths from {robots_url}: {e}")

        return disallowed

    def apply_crawl_delay(self, url: str):
        """Apply crawl delay if specified in robots.txt."""
        delay = self.get_crawl_delay(url)
        if delay > 0:
            time.sleep(delay)

    def clear_cache(self):
        """Clear all cached robots.txt data."""
        self.robots_cache.clear()
        self.sitemap_cache.clear()
        self.crawl_delays.clear()