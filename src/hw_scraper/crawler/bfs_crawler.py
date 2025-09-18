"""Breadth-first search crawler implementation."""

from typing import Set, Optional, Deque
from collections import deque
from datetime import datetime
import logging

from hw_scraper.config import Config
from hw_scraper.crawler.base_crawler import BaseCrawler, CrawlResult
from hw_scraper.crawler.robots_parser import RobotsParser
from hw_scraper.crawler.sitemap_parser import SitemapParser


class BFSCrawler(BaseCrawler):
    """Crawler using breadth-first search algorithm."""

    def __init__(self, config: Config, **kwargs):
        """Initialize BFS crawler."""
        super().__init__(config, **kwargs)
        self.robots_parser = RobotsParser(self.session) if self.respect_robots else None
        self.sitemap_parser = SitemapParser(self.session)

    def crawl(self, start_url: str, use_sitemap: bool = True) -> CrawlResult:
        """
        Crawl website using BFS algorithm.

        Args:
            start_url: URL to start crawling from
            use_sitemap: Whether to use sitemap for URL discovery

        Returns:
            CrawlResult containing discovered URLs and statistics
        """
        self.reset()

        # Normalize start URL
        start_url = self._normalize_url(start_url)

        # Initialize result
        result = CrawlResult(
            start_url=start_url,
            start_time=datetime.now()
        )

        # Initialize BFS queue with (url, depth) tuples
        queue: Deque[tuple[str, int]] = deque([(start_url, 0)])
        self.discovered_urls.add(start_url)

        # Check robots.txt
        if self.respect_robots and self.robots_parser:
            if not self.robots_parser.can_fetch(start_url, '*'):
                self.logger.warning(f"Robots.txt disallows crawling {start_url}")
                result.failed_urls[start_url] = "Disallowed by robots.txt"
                result.end_time = datetime.now()
                return result

            # Get sitemaps from robots.txt
            if use_sitemap:
                sitemaps = self.robots_parser.get_sitemaps(start_url)
                for sitemap_url in sitemaps:
                    sitemap_urls = self.sitemap_parser.parse_sitemap(sitemap_url)
                    for url in sitemap_urls:
                        if self._is_valid_url(url) and url not in self.discovered_urls:
                            queue.append((url, 1))
                            self.discovered_urls.add(url)

        # Try to find sitemaps if not in robots.txt
        if use_sitemap and not self.discovered_urls:
            found_sitemaps = self.sitemap_parser.find_sitemaps(start_url)
            for sitemap_url in found_sitemaps:
                sitemap_urls = self.sitemap_parser.parse_sitemap(sitemap_url)
                for url in sitemap_urls:
                    if self._is_valid_url(url) and url not in self.discovered_urls:
                        queue.append((url, 1))
                        self.discovered_urls.add(url)

        # BFS crawling
        while queue:
            # Check max URLs limit
            if self.max_urls > 0 and len(self.visited_urls) >= self.max_urls:
                self.logger.info(f"Reached max URLs limit ({self.max_urls})")
                break

            # Get next URL from queue
            current_url, depth = queue.popleft()

            # Check max depth
            if self.max_depth >= 0 and depth > self.max_depth:
                continue

            # Update max depth reached
            result.max_depth_reached = max(result.max_depth_reached, depth)

            # Skip if already visited
            if current_url in self.visited_urls:
                continue

            # Check robots.txt for this specific URL
            if self.respect_robots and self.robots_parser:
                if not self.robots_parser.can_fetch(current_url, '*'):
                    self.logger.debug(f"Skipping {current_url} (disallowed by robots.txt)")
                    self.failed_urls[current_url] = "Disallowed by robots.txt"
                    continue

                # Apply crawl delay
                self.robots_parser.apply_crawl_delay(current_url)

            # Fetch and parse page
            self.logger.info(f"Crawling {current_url} (depth: {depth})")
            html_content = self._fetch_page(current_url)

            if html_content:
                # Mark as visited
                self.visited_urls.add(current_url)

                # Extract links
                links = self._extract_links(html_content, current_url)

                # Add new links to queue
                for link in links:
                    if link not in self.discovered_urls and self._should_crawl_url(link):
                        queue.append((link, depth + 1))
                        self.discovered_urls.add(link)

                self.logger.debug(f"Found {len(links)} links on {current_url}")
            else:
                # Failed to fetch
                if current_url not in self.failed_urls:
                    self.failed_urls[current_url] = "Failed to fetch"

        # Finalize result
        result.discovered_urls = self.discovered_urls.copy()
        result.visited_urls = self.visited_urls.copy()
        result.failed_urls = self.failed_urls.copy()
        result.end_time = datetime.now()

        self.logger.info(
            f"BFS crawl completed: {len(result.visited_urls)} visited, "
            f"{len(result.discovered_urls)} discovered, "
            f"{len(result.failed_urls)} failed, "
            f"max depth: {result.max_depth_reached}, "
            f"duration: {result.duration:.2f}s"
        )

        return result

    def crawl_parallel(self, start_url: str, max_workers: int = 5) -> CrawlResult:
        """
        Crawl website using parallel BFS (multiple workers).

        Args:
            start_url: URL to start crawling from
            max_workers: Number of parallel workers

        Returns:
            CrawlResult containing discovered URLs and statistics
        """
        # TODO: Implement parallel BFS using threading/asyncio
        # For now, fall back to sequential
        return self.crawl(start_url)