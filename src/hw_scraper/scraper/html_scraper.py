"""Enhanced HTML scraper with XPath support."""

from typing import Dict, List, Any, Optional, Set
from urllib.parse import urljoin, urlparse
import re
import logging

from lxml import html
from curl_cffi import requests

from hw_scraper.config import Config
from hw_scraper.models import CourseFile, FileType
from hw_scraper.scraper.xpath_extractor import XPathExtractor


class HTMLScraper:
    """Enhanced HTML content scraper."""

    def __init__(self, config: Config, session: Optional[requests.Session] = None):
        """Initialize HTML scraper."""
        self.config = config
        self.session = session or self._create_session()
        self.xpath_extractor = XPathExtractor()
        self.logger = logging.getLogger(self.__class__.__name__)

    def _create_session(self) -> requests.Session:
        """Create HTTP session."""
        return requests.Session(
            impersonate='chrome120',
            timeout=self.config.scraper_config.timeout,
            verify=self.config.scraper_config.verify_ssl
        )

    def scrape_page(
        self,
        url: str,
        extraction_rules: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Scrape page with custom extraction rules.

        Args:
            url: Page URL
            extraction_rules: Dictionary of field names to XPath expressions

        Returns:
            Extracted data dictionary
        """
        try:
            response = self.session.get(url)
            response.raise_for_status()

            html_content = response.text
            extracted_data = {'url': url}

            # Extract metadata
            extracted_data['metadata'] = self.xpath_extractor.extract_metadata(html_content)

            # Apply custom extraction rules
            if extraction_rules:
                for field_name, xpath in extraction_rules.items():
                    extracted_data[field_name] = self.xpath_extractor.extract(
                        html_content, xpath, 'text'
                    )

            # Extract structured data
            structured = self.xpath_extractor.extract_structured_data(html_content)
            if structured:
                extracted_data['structured_data'] = structured

            # Extract forms
            forms = self.xpath_extractor.extract_forms(html_content)
            if forms:
                extracted_data['forms'] = forms

            # Extract links
            links = self.xpath_extractor.extract_links(html_content, base_url=url)
            extracted_data['links'] = links

            return extracted_data

        except Exception as e:
            self.logger.error(f"Failed to scrape {url}: {e}")
            return {'url': url, 'error': str(e)}

    def extract_course_materials(
        self,
        url: str,
        custom_rules: Optional[Dict[str, str]] = None
    ) -> List[CourseFile]:
        """
        Extract course materials from a page.

        Args:
            url: Course page URL
            custom_rules: Custom XPath rules for extraction

        Returns:
            List of CourseFile objects
        """
        files = []

        try:
            response = self.session.get(url)
            response.raise_for_status()

            html_content = response.text

            # Default extraction rules for course materials
            default_rules = {
                'pdf_links': '//a[contains(@href, ".pdf")]',
                'doc_links': '//a[contains(@href, ".doc") or contains(@href, ".docx")]',
                'ppt_links': '//a[contains(@href, ".ppt") or contains(@href, ".pptx")]',
                'video_links': '//a[contains(@href, ".mp4") or contains(@href, ".avi")]',
                'download_links': '//a[@download or contains(@class, "download")]'
            }

            # Merge with custom rules
            rules = {**default_rules, **(custom_rules or {})}

            # Extract links based on rules
            tree = html.fromstring(html_content)

            for rule_name, xpath in rules.items():
                elements = tree.xpath(xpath)

                for element in elements:
                    href = element.get('href')
                    if href:
                        file_url = urljoin(url, href)
                        file_name = element.text_content().strip() or self._extract_filename_from_url(file_url)
                        file_type = self._detect_file_type(file_url, file_name)

                        files.append(CourseFile(
                            name=file_name,
                            url=file_url,
                            type=file_type,
                            description=element.get('title', '')
                        ))

            # Remove duplicates
            seen_urls = set()
            unique_files = []
            for file in files:
                if file.url not in seen_urls:
                    seen_urls.add(file.url)
                    unique_files.append(file)

            return unique_files

        except Exception as e:
            self.logger.error(f"Failed to extract course materials from {url}: {e}")
            return []

    def _extract_filename_from_url(self, url: str) -> str:
        """Extract filename from URL."""
        path = urlparse(url).path
        if '/' in path:
            filename = path.split('/')[-1]
        else:
            filename = path

        return filename or f"file_{hash(url) % 10000}"

    def _detect_file_type(self, url: str, filename: str) -> FileType:
        """Detect file type from URL and filename."""
        combined = (url + filename).lower()

        if any(ext in combined for ext in ['.mp4', '.avi', '.mov', '.webm']):
            return FileType.LECTURE_VIDEO
        elif any(ext in combined for ext in ['.ppt', '.pptx']):
            return FileType.LECTURE_SLIDE
        elif any(ext in combined for ext in ['.pdf']) and 'slide' in combined:
            return FileType.LECTURE_SLIDE
        elif any(ext in combined for ext in ['.doc', '.docx']) and any(
            word in combined for word in ['assignment', 'homework', 'hw']
        ):
            return FileType.ASSIGNMENT
        elif 'syllabus' in combined:
            return FileType.SYLLABUS
        elif any(ext in combined for ext in ['.zip', '.tar', '.gz', '.rar']):
            return FileType.RESOURCE
        elif any(ext in combined for ext in ['.pdf', '.epub']):
            return FileType.READING

        return FileType.OTHER

    def extract_with_patterns(
        self,
        url: str,
        patterns: Dict[str, str]
    ) -> Dict[str, List[str]]:
        """
        Extract content using regex patterns.

        Args:
            url: Page URL
            patterns: Dictionary of field names to regex patterns

        Returns:
            Dictionary of extracted content
        """
        results = {}

        try:
            response = self.session.get(url)
            response.raise_for_status()

            html_content = response.text

            # Remove HTML tags for pattern matching
            text_content = re.sub(r'<[^>]+>', ' ', html_content)

            for field_name, pattern in patterns.items():
                matches = re.findall(pattern, text_content, re.IGNORECASE)
                results[field_name] = matches

        except Exception as e:
            self.logger.error(f"Failed to extract with patterns from {url}: {e}")

        return results

    def extract_tables(
        self,
        url: str,
        table_selector: str = '//table'
    ) -> List[List[Dict[str, str]]]:
        """
        Extract all tables from page.

        Args:
            url: Page URL
            table_selector: XPath selector for tables

        Returns:
            List of tables (each table is a list of row dictionaries)
        """
        tables = []

        try:
            response = self.session.get(url)
            response.raise_for_status()

            table_data = self.xpath_extractor.extract_table(
                response.text,
                table_xpath=table_selector
            )

            if table_data:
                tables.append(table_data)

        except Exception as e:
            self.logger.error(f"Failed to extract tables from {url}: {e}")

        return tables

    def extract_academic_content(self, url: str) -> Dict[str, Any]:
        """
        Extract academic content with specialized rules.

        Args:
            url: Academic page URL

        Returns:
            Extracted academic content
        """
        academic_rules = {
            'course_title': '//h1[@class="course-title"] | //h1 | //title',
            'instructor': '//*[contains(@class, "instructor")] | //*[contains(text(), "Professor")]',
            'schedule': '//*[contains(@class, "schedule")] | //*[contains(text(), "Schedule")]',
            'prerequisites': '//*[contains(text(), "Prerequisites")] | //*[contains(@class, "prereq")]',
            'textbooks': '//*[contains(text(), "Textbook")] | //*[contains(@class, "textbook")]',
            'grading': '//*[contains(text(), "Grading")] | //*[contains(@class, "grading")]',
            'office_hours': '//*[contains(text(), "Office Hours")] | //*[contains(@class, "office")]',
            'assignments': '//a[contains(@href, "assignment") or contains(@href, "homework")]'
        }

        return self.scrape_page(url, academic_rules)