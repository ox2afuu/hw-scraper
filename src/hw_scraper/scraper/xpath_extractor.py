"""XPath-based content extraction utilities."""

from typing import List, Dict, Any, Optional, Union
from lxml import html, etree
import re
import logging


class XPathExtractor:
    """Advanced XPath-based content extractor."""

    def __init__(self):
        """Initialize XPath extractor."""
        self.logger = logging.getLogger(self.__class__.__name__)

    def extract(
        self,
        html_content: str,
        xpath: str,
        extract_type: str = 'text',
        single: bool = False,
        default: Any = None
    ) -> Union[Any, List[Any]]:
        """
        Extract content using XPath.

        Args:
            html_content: HTML content to parse
            xpath: XPath expression
            extract_type: Type of extraction ('text', 'html', 'attribute', 'all')
            single: Return single element instead of list
            default: Default value if nothing found

        Returns:
            Extracted content or default value
        """
        try:
            tree = html.fromstring(html_content)
            elements = tree.xpath(xpath)

            if not elements:
                return default

            results = []
            for element in elements:
                if extract_type == 'text':
                    if isinstance(element, str):
                        results.append(element)
                    else:
                        text = element.text_content() if hasattr(element, 'text_content') else str(element)
                        results.append(text.strip() if text else '')

                elif extract_type == 'html':
                    if isinstance(element, str):
                        results.append(element)
                    else:
                        html_str = etree.tostring(element, encoding='unicode', method='html')
                        results.append(html_str)

                elif extract_type == 'attribute':
                    # For attribute extraction, the XPath should already select the attribute
                    if isinstance(element, str):
                        results.append(element)
                    else:
                        results.append(str(element))

                elif extract_type == 'all':
                    if isinstance(element, str):
                        results.append({'text': element, 'html': element, 'attributes': {}})
                    else:
                        result = {
                            'text': element.text_content() if hasattr(element, 'text_content') else '',
                            'html': etree.tostring(element, encoding='unicode', method='html'),
                            'attributes': dict(element.attrib) if hasattr(element, 'attrib') else {}
                        }
                        results.append(result)

            if single:
                return results[0] if results else default
            return results

        except Exception as e:
            self.logger.error(f"XPath extraction failed: {e}")
            return default if single else []

    def extract_with_css(
        self,
        html_content: str,
        css_selector: str,
        extract_type: str = 'text',
        single: bool = False,
        default: Any = None
    ) -> Union[Any, List[Any]]:
        """
        Extract content using CSS selector (converted to XPath).

        Args:
            html_content: HTML content to parse
            css_selector: CSS selector
            extract_type: Type of extraction
            single: Return single element
            default: Default value if nothing found

        Returns:
            Extracted content
        """
        xpath = self._css_to_xpath(css_selector)
        return self.extract(html_content, xpath, extract_type, single, default)

    def _css_to_xpath(self, css_selector: str) -> str:
        """
        Convert CSS selector to XPath (simplified).

        Args:
            css_selector: CSS selector string

        Returns:
            XPath expression
        """
        # This is a simplified converter
        # For production, consider using cssselect library

        xpath = css_selector

        # Convert ID selector
        xpath = re.sub(r'#(\w+)', r'[@id="\1"]', xpath)

        # Convert class selector
        xpath = re.sub(r'\.(\w+)', r'[contains(@class, "\1")]', xpath)

        # Convert descendant selector
        xpath = xpath.replace(' ', '//')

        # Convert direct child selector
        xpath = xpath.replace('>', '/')

        # Add // at the beginning if not present
        if not xpath.startswith('//'):
            xpath = '//' + xpath

        return xpath

    def extract_table(
        self,
        html_content: str,
        table_xpath: str = '//table',
        headers_xpath: str = './/thead//th | .//tr[1]//th | .//tr[1]//td',
        rows_xpath: str = './/tbody//tr | .//tr[position()>1]'
    ) -> List[Dict[str, str]]:
        """
        Extract table data as list of dictionaries.

        Args:
            html_content: HTML content
            table_xpath: XPath to table element
            headers_xpath: XPath to header cells (relative to table)
            rows_xpath: XPath to data rows (relative to table)

        Returns:
            List of row dictionaries with headers as keys
        """
        try:
            tree = html.fromstring(html_content)
            tables = tree.xpath(table_xpath)

            all_data = []

            for table in tables:
                # Extract headers
                header_elements = table.xpath(headers_xpath)
                headers = [h.text_content().strip() for h in header_elements]

                if not headers:
                    # Try to use first row as headers
                    first_row = table.xpath('.//tr[1]//td')
                    headers = [h.text_content().strip() for h in first_row]

                # Extract rows
                rows = table.xpath(rows_xpath)

                for row in rows:
                    cells = row.xpath('.//td | .//th')
                    if cells:
                        row_data = {}
                        for i, cell in enumerate(cells):
                            header = headers[i] if i < len(headers) else f'column_{i}'
                            row_data[header] = cell.text_content().strip()
                        all_data.append(row_data)

            return all_data

        except Exception as e:
            self.logger.error(f"Table extraction failed: {e}")
            return []

    def extract_links(
        self,
        html_content: str,
        link_xpath: str = '//a[@href]',
        absolute: bool = True,
        base_url: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Extract links with text and URL.

        Args:
            html_content: HTML content
            link_xpath: XPath to link elements
            absolute: Convert to absolute URLs
            base_url: Base URL for absolute conversion

        Returns:
            List of link dictionaries with 'text' and 'url' keys
        """
        try:
            tree = html.fromstring(html_content)

            if absolute and base_url:
                tree.make_links_absolute(base_url)

            links = []
            for link in tree.xpath(link_xpath):
                link_data = {
                    'text': link.text_content().strip(),
                    'url': link.get('href', ''),
                    'title': link.get('title', '')
                }
                links.append(link_data)

            return links

        except Exception as e:
            self.logger.error(f"Link extraction failed: {e}")
            return []

    def extract_metadata(
        self,
        html_content: str
    ) -> Dict[str, Any]:
        """
        Extract common metadata from HTML.

        Args:
            html_content: HTML content

        Returns:
            Dictionary of metadata
        """
        metadata = {}

        try:
            tree = html.fromstring(html_content)

            # Title
            title = self.extract(html_content, '//title', 'text', single=True)
            if title:
                metadata['title'] = title

            # Meta tags
            meta_tags = tree.xpath('//meta[@name or @property]')
            for meta in meta_tags:
                name = meta.get('name') or meta.get('property')
                content = meta.get('content')
                if name and content:
                    metadata[name] = content

            # Open Graph tags
            og_tags = tree.xpath('//meta[starts-with(@property, "og:")]')
            og_data = {}
            for tag in og_tags:
                prop = tag.get('property', '').replace('og:', '')
                content = tag.get('content')
                if prop and content:
                    og_data[prop] = content
            if og_data:
                metadata['open_graph'] = og_data

            # Twitter Card tags
            twitter_tags = tree.xpath('//meta[starts-with(@name, "twitter:")]')
            twitter_data = {}
            for tag in twitter_tags:
                name = tag.get('name', '').replace('twitter:', '')
                content = tag.get('content')
                if name and content:
                    twitter_data[name] = content
            if twitter_data:
                metadata['twitter_card'] = twitter_data

            # Canonical URL
            canonical = self.extract(
                html_content,
                '//link[@rel="canonical"]/@href',
                'attribute',
                single=True
            )
            if canonical:
                metadata['canonical_url'] = canonical

            # Language
            lang = self.extract(
                html_content,
                '/html/@lang',
                'attribute',
                single=True
            )
            if lang:
                metadata['language'] = lang

        except Exception as e:
            self.logger.error(f"Metadata extraction failed: {e}")

        return metadata

    def extract_structured_data(
        self,
        html_content: str
    ) -> List[Dict[str, Any]]:
        """
        Extract JSON-LD structured data.

        Args:
            html_content: HTML content

        Returns:
            List of structured data objects
        """
        import json

        structured_data = []

        try:
            scripts = self.extract(
                html_content,
                '//script[@type="application/ld+json"]',
                'text'
            )

            for script in scripts:
                if script:
                    try:
                        data = json.loads(script)
                        structured_data.append(data)
                    except json.JSONDecodeError:
                        self.logger.debug(f"Failed to parse JSON-LD: {script[:100]}")

        except Exception as e:
            self.logger.error(f"Structured data extraction failed: {e}")

        return structured_data

    def extract_forms(
        self,
        html_content: str
    ) -> List[Dict[str, Any]]:
        """
        Extract form information.

        Args:
            html_content: HTML content

        Returns:
            List of form data dictionaries
        """
        forms = []

        try:
            tree = html.fromstring(html_content)

            for form in tree.xpath('//form'):
                form_data = {
                    'action': form.get('action', ''),
                    'method': form.get('method', 'get').upper(),
                    'name': form.get('name', ''),
                    'id': form.get('id', ''),
                    'fields': []
                }

                # Extract form fields
                for field in form.xpath('.//input | .//select | .//textarea'):
                    field_info = {
                        'type': field.get('type', 'text'),
                        'name': field.get('name', ''),
                        'id': field.get('id', ''),
                        'value': field.get('value', ''),
                        'required': field.get('required') is not None
                    }

                    # For select elements, extract options
                    if field.tag == 'select':
                        options = []
                        for option in field.xpath('.//option'):
                            options.append({
                                'value': option.get('value', ''),
                                'text': option.text_content().strip()
                            })
                        field_info['options'] = options

                    form_data['fields'].append(field_info)

                forms.append(form_data)

        except Exception as e:
            self.logger.error(f"Form extraction failed: {e}")

        return forms