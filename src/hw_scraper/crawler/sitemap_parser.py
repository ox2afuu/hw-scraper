"""Parser for sitemap.xml and sitemap.html files."""

from typing import List, Set, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
from datetime import datetime
import xml.etree.ElementTree as ET
import re
import logging
import gzip
from io import BytesIO

from curl_cffi import requests
from lxml import html


class SitemapParser:
    """Parser for XML and HTML sitemaps."""

    def __init__(self, session: Optional[requests.Session] = None):
        """Initialize sitemap parser."""
        self.session = session or requests.Session(impersonate='chrome120')
        self.logger = logging.getLogger(self.__class__.__name__)

    def parse_sitemap(self, sitemap_url: str) -> Set[str]:
        """
        Parse sitemap and extract all URLs.

        Args:
            sitemap_url: URL of the sitemap

        Returns:
            Set of discovered URLs
        """
        urls = set()

        try:
            # Detect sitemap type from URL or content
            if sitemap_url.endswith('.xml') or sitemap_url.endswith('.xml.gz'):
                urls = self._parse_xml_sitemap(sitemap_url)
            elif sitemap_url.endswith('.html') or sitemap_url.endswith('.htm'):
                urls = self._parse_html_sitemap(sitemap_url)
            else:
                # Try to detect from content
                urls = self._auto_detect_and_parse(sitemap_url)

            self.logger.info(f"Found {len(urls)} URLs in sitemap {sitemap_url}")

        except Exception as e:
            self.logger.error(f"Failed to parse sitemap {sitemap_url}: {e}")

        return urls

    def _parse_xml_sitemap(self, sitemap_url: str) -> Set[str]:
        """Parse XML sitemap."""
        urls = set()

        try:
            response = self.session.get(sitemap_url, timeout=30)
            response.raise_for_status()

            # Handle gzipped sitemaps
            content = response.content
            if sitemap_url.endswith('.gz'):
                content = gzip.decompress(content)

            # Parse XML
            root = ET.fromstring(content)

            # Handle sitemap index files
            if 'sitemapindex' in root.tag:
                # This is a sitemap index, parse referenced sitemaps
                for sitemap in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
                    loc = sitemap.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                    if loc is not None and loc.text:
                        # Recursively parse referenced sitemap
                        sub_urls = self.parse_sitemap(loc.text)
                        urls.update(sub_urls)
            else:
                # Regular sitemap with URLs
                for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
                    loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                    if loc is not None and loc.text:
                        urls.add(loc.text.strip())

                # Also try without namespace (some sitemaps don't use it)
                for url in root.findall('.//url'):
                    loc = url.find('loc')
                    if loc is not None and loc.text:
                        urls.add(loc.text.strip())

        except ET.ParseError as e:
            self.logger.error(f"XML parsing error for {sitemap_url}: {e}")
        except Exception as e:
            self.logger.error(f"Failed to parse XML sitemap {sitemap_url}: {e}")

        return urls

    def _parse_html_sitemap(self, sitemap_url: str) -> Set[str]:
        """Parse HTML sitemap."""
        urls = set()

        try:
            response = self.session.get(sitemap_url, timeout=30)
            response.raise_for_status()

            # Parse HTML
            tree = html.fromstring(response.text)

            # Extract all links
            for link in tree.xpath('//a[@href]'):
                href = link.get('href')
                if href:
                    # Make URL absolute
                    absolute_url = urljoin(sitemap_url, href)

                    # Filter out common non-content URLs
                    if not self._is_navigation_url(absolute_url):
                        urls.add(absolute_url)

        except Exception as e:
            self.logger.error(f"Failed to parse HTML sitemap {sitemap_url}: {e}")

        return urls

    def _auto_detect_and_parse(self, sitemap_url: str) -> Set[str]:
        """Auto-detect sitemap type and parse."""
        try:
            response = self.session.get(sitemap_url, timeout=30)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '').lower()

            # Check content type
            if 'xml' in content_type or response.text.strip().startswith('<?xml'):
                # Parse as XML
                return self._parse_xml_from_content(response.content, sitemap_url)
            elif 'html' in content_type or '<html' in response.text[:1000].lower():
                # Parse as HTML
                return self._parse_html_from_content(response.text, sitemap_url)
            else:
                # Try XML first, fall back to HTML
                try:
                    return self._parse_xml_from_content(response.content, sitemap_url)
                except:
                    return self._parse_html_from_content(response.text, sitemap_url)

        except Exception as e:
            self.logger.error(f"Failed to auto-detect sitemap type for {sitemap_url}: {e}")

        return set()

    def _parse_xml_from_content(self, content: bytes, base_url: str) -> Set[str]:
        """Parse XML sitemap from content."""
        urls = set()

        try:
            root = ET.fromstring(content)

            # Handle sitemap index
            if 'sitemapindex' in root.tag:
                for sitemap in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap'):
                    loc = sitemap.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                    if loc is not None and loc.text:
                        sub_urls = self.parse_sitemap(loc.text)
                        urls.update(sub_urls)
            else:
                # Regular sitemap
                for url in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}url'):
                    loc = url.find('{http://www.sitemaps.org/schemas/sitemap/0.9}loc')
                    if loc is not None and loc.text:
                        urls.add(loc.text.strip())

                # Try without namespace
                for url in root.findall('.//url'):
                    loc = url.find('loc')
                    if loc is not None and loc.text:
                        urls.add(loc.text.strip())

        except Exception as e:
            self.logger.debug(f"Failed to parse XML content: {e}")

        return urls

    def _parse_html_from_content(self, content: str, base_url: str) -> Set[str]:
        """Parse HTML sitemap from content."""
        urls = set()

        try:
            tree = html.fromstring(content)

            for link in tree.xpath('//a[@href]'):
                href = link.get('href')
                if href:
                    absolute_url = urljoin(base_url, href)
                    if not self._is_navigation_url(absolute_url):
                        urls.add(absolute_url)

        except Exception as e:
            self.logger.debug(f"Failed to parse HTML content: {e}")

        return urls

    def _is_navigation_url(self, url: str) -> bool:
        """Check if URL is likely a navigation/utility link."""
        parsed = urlparse(url)
        path = parsed.path.lower()

        # Common navigation patterns to exclude
        nav_patterns = [
            '/contact', '/about', '/privacy', '/terms',
            '/login', '/logout', '/register', '/signup',
            '/search', '/help', '/faq', '/sitemap'
        ]

        return any(pattern in path for pattern in nav_patterns)

    def find_sitemaps(self, base_url: str) -> List[str]:
        """
        Try to find sitemaps for a website.

        Args:
            base_url: Base URL of the website

        Returns:
            List of discovered sitemap URLs
        """
        sitemaps = []
        parsed = urlparse(base_url)
        base = f"{parsed.scheme}://{parsed.netloc}"

        # Common sitemap locations
        common_locations = [
            '/sitemap.xml',
            '/sitemap_index.xml',
            '/sitemap.xml.gz',
            '/sitemap.html',
            '/sitemap.htm',
            '/sitemap/',
            '/sitemaps.xml',
            '/sitemap/sitemap.xml',
            '/sitemap_index.xml.gz'
        ]

        for location in common_locations:
            sitemap_url = urljoin(base, location)
            try:
                response = self.session.head(sitemap_url, timeout=5)
                if response.status_code == 200:
                    sitemaps.append(sitemap_url)
                    self.logger.info(f"Found sitemap at {sitemap_url}")
            except:
                pass

        return sitemaps

    def parse_sitemap_with_metadata(self, sitemap_url: str) -> List[Dict[str, Any]]:
        """
        Parse sitemap with metadata like lastmod, changefreq, priority.

        Args:
            sitemap_url: URL of the sitemap

        Returns:
            List of URL entries with metadata
        """
        entries = []

        try:
            response = self.session.get(sitemap_url, timeout=30)
            response.raise_for_status()

            content = response.content
            if sitemap_url.endswith('.gz'):
                content = gzip.decompress(content)

            root = ET.fromstring(content)

            # Parse with namespace
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            for url in root.findall('.//sm:url', ns):
                entry = {}

                # Extract URL
                loc = url.find('sm:loc', ns)
                if loc is not None and loc.text:
                    entry['url'] = loc.text.strip()

                    # Extract optional metadata
                    lastmod = url.find('sm:lastmod', ns)
                    if lastmod is not None and lastmod.text:
                        entry['lastmod'] = lastmod.text.strip()

                    changefreq = url.find('sm:changefreq', ns)
                    if changefreq is not None and changefreq.text:
                        entry['changefreq'] = changefreq.text.strip()

                    priority = url.find('sm:priority', ns)
                    if priority is not None and priority.text:
                        try:
                            entry['priority'] = float(priority.text.strip())
                        except ValueError:
                            pass

                    entries.append(entry)

        except Exception as e:
            self.logger.error(f"Failed to parse sitemap with metadata {sitemap_url}: {e}")

        return entries