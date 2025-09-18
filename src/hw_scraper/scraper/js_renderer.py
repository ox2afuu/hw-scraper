"""JavaScript rendering detection and handling."""

from typing import Optional, Dict, Any, List, Set
import re
import logging
import json

from lxml import html
from curl_cffi import requests


class JSDetector:
    """Detector for JavaScript-rendered content."""

    # Common JavaScript frameworks and libraries
    JS_FRAMEWORKS = {
        'react': ['react', 'ReactDOM', '__REACT_'],
        'angular': ['angular', 'ng-', 'ng-app'],
        'vue': ['Vue', 'v-', '__VUE__'],
        'ember': ['Ember', 'ember-'],
        'backbone': ['Backbone'],
        'jquery': ['jQuery', '$'],
        'nextjs': ['__NEXT_', '_next'],
        'nuxtjs': ['__NUXT__'],
        'gatsby': ['___gatsby'],
        'svelte': ['__svelte']
    }

    # Indicators of JS-heavy content
    JS_INDICATORS = [
        '<noscript>',
        'data-react',
        'data-ng-',
        'v-bind',
        'ng-controller',
        'id="root"',
        'id="app"',
        '__INITIAL_STATE__',
        '__PRELOADED_STATE__',
        'window.__',
        'require.js',
        'webpack',
        'bundle.js'
    ]

    def __init__(self):
        """Initialize JS detector."""
        self.logger = logging.getLogger(self.__class__.__name__)

    def detect_javascript(self, html_content: str) -> Dict[str, Any]:
        """
        Detect JavaScript usage in HTML content.

        Args:
            html_content: HTML content to analyze

        Returns:
            Dictionary with JS detection results
        """
        results = {
            'uses_javascript': False,
            'requires_js_rendering': False,
            'frameworks': [],
            'indicators': [],
            'dynamic_content_score': 0
        }

        # Check for JS frameworks
        for framework, patterns in self.JS_FRAMEWORKS.items():
            for pattern in patterns:
                if pattern in html_content:
                    results['frameworks'].append(framework)
                    results['uses_javascript'] = True
                    break

        # Check for JS indicators
        for indicator in self.JS_INDICATORS:
            if indicator in html_content:
                results['indicators'].append(indicator)
                results['uses_javascript'] = True

        # Calculate dynamic content score
        score = self._calculate_js_score(html_content)
        results['dynamic_content_score'] = score

        # Determine if JS rendering is required
        if score > 50:
            results['requires_js_rendering'] = True
        elif results['frameworks'] and len(results['frameworks']) > 0:
            results['requires_js_rendering'] = True
        elif '<noscript>' in html_content and self._check_noscript_content(html_content):
            results['requires_js_rendering'] = True

        return results

    def _calculate_js_score(self, html_content: str) -> int:
        """
        Calculate JavaScript dependency score.

        Args:
            html_content: HTML content

        Returns:
            Score from 0-100 indicating JS dependency
        """
        score = 0

        # Check for script tags
        script_count = html_content.count('<script')
        score += min(script_count * 5, 30)

        # Check for inline JavaScript
        if 'onclick=' in html_content or 'onload=' in html_content:
            score += 10

        # Check for AJAX indicators
        if 'XMLHttpRequest' in html_content or 'fetch(' in html_content:
            score += 20

        # Check for JSON data
        if '__INITIAL_DATA__' in html_content or 'window.__' in html_content:
            score += 15

        # Check for SPA indicators
        if any(spa in html_content for spa in ['#root', '#app', 'id="root"', 'id="app"']):
            score += 20

        # Check for minimal HTML content
        tree = html.fromstring(html_content)
        body_text = tree.text_content() if tree.body is not None else ''
        if len(body_text.strip()) < 100:
            score += 15

        return min(score, 100)

    def _check_noscript_content(self, html_content: str) -> bool:
        """
        Check if noscript tag contains significant content.

        Args:
            html_content: HTML content

        Returns:
            True if noscript contains important content
        """
        noscript_pattern = r'<noscript>(.*?)</noscript>'
        matches = re.findall(noscript_pattern, html_content, re.DOTALL | re.IGNORECASE)

        for match in matches:
            if 'JavaScript' in match or 'enable' in match:
                return True

        return False

    def extract_js_data(self, html_content: str) -> Dict[str, Any]:
        """
        Extract embedded JavaScript data.

        Args:
            html_content: HTML content

        Returns:
            Dictionary of extracted JS data
        """
        extracted_data = {}

        # Extract JSON-LD
        json_ld_pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
        json_ld_matches = re.findall(json_ld_pattern, html_content, re.DOTALL | re.IGNORECASE)

        for match in json_ld_matches:
            try:
                data = json.loads(match.strip())
                extracted_data['json_ld'] = extracted_data.get('json_ld', [])
                extracted_data['json_ld'].append(data)
            except json.JSONDecodeError:
                pass

        # Extract window variables
        window_var_pattern = r'window\.(\w+)\s*=\s*({.*?});'
        window_matches = re.findall(window_var_pattern, html_content, re.DOTALL)

        for var_name, var_content in window_matches:
            try:
                data = json.loads(var_content)
                extracted_data[f'window.{var_name}'] = data
            except json.JSONDecodeError:
                # Try to clean and parse
                cleaned = self._clean_js_object(var_content)
                try:
                    data = json.loads(cleaned)
                    extracted_data[f'window.{var_name}'] = data
                except:
                    pass

        return extracted_data

    def _clean_js_object(self, js_str: str) -> str:
        """
        Clean JavaScript object string for JSON parsing.

        Args:
            js_str: JavaScript object string

        Returns:
            Cleaned string
        """
        # Remove trailing commas
        js_str = re.sub(r',\s*}', '}', js_str)
        js_str = re.sub(r',\s*]', ']', js_str)

        # Convert single quotes to double quotes
        js_str = js_str.replace("'", '"')

        # Handle unquoted keys
        js_str = re.sub(r'(\w+):', r'"\1":', js_str)

        return js_str


class JSRenderer:
    """JavaScript renderer for dynamic content (placeholder for full implementation)."""

    def __init__(self, method: str = 'curl_cffi'):
        """
        Initialize JS renderer.

        Args:
            method: Rendering method ('curl_cffi', 'selenium', 'playwright')
        """
        self.method = method
        self.logger = logging.getLogger(self.__class__.__name__)
        self.detector = JSDetector()

    def render(
        self,
        url: str,
        wait_for: Optional[str] = None,
        timeout: int = 30
    ) -> str:
        """
        Render JavaScript-heavy page.

        Args:
            url: Page URL
            wait_for: Element selector to wait for
            timeout: Timeout in seconds

        Returns:
            Rendered HTML content
        """
        if self.method == 'curl_cffi':
            return self._render_with_curl_cffi(url, timeout)
        else:
            # Placeholder for other methods
            self.logger.warning(f"Rendering method {self.method} not implemented, using curl_cffi")
            return self._render_with_curl_cffi(url, timeout)

    def _render_with_curl_cffi(self, url: str, timeout: int) -> str:
        """
        Render with curl_cffi (limited JS support).

        Args:
            url: Page URL
            timeout: Timeout in seconds

        Returns:
            HTML content
        """
        try:
            # curl_cffi has some JS support through browser impersonation
            session = requests.Session(
                impersonate='chrome120',
                timeout=timeout
            )

            # Add headers that might trigger JS content
            session.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })

            response = session.get(url)
            response.raise_for_status()

            return response.text

        except Exception as e:
            self.logger.error(f"Failed to render {url}: {e}")
            return ""

    def check_rendering_required(self, html_content: str) -> bool:
        """
        Check if JS rendering is required.

        Args:
            html_content: HTML content

        Returns:
            True if JS rendering is needed
        """
        detection = self.detector.detect_javascript(html_content)
        return detection['requires_js_rendering']

    def extract_ajax_endpoints(self, html_content: str) -> List[str]:
        """
        Extract AJAX/API endpoints from JavaScript code.

        Args:
            html_content: HTML content

        Returns:
            List of discovered endpoints
        """
        endpoints = set()

        # Common API patterns
        api_patterns = [
            r'["\'](/api/[^"\']+)["\']',
            r'["\'](/v\d+/[^"\']+)["\']',
            r'fetch\(["\']([^"\']+)["\']',
            r'axios\.[get|post|put|delete]\(["\']([^"\']+)["\']',
            r'XMLHttpRequest.*open\(["\'][^"\']*["\'],\s*["\']([^"\']+)["\']'
        ]

        for pattern in api_patterns:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            endpoints.update(matches)

        # Filter out obvious non-API URLs
        filtered = []
        for endpoint in endpoints:
            if not any(skip in endpoint.lower() for skip in ['.css', '.js', '.jpg', '.png', '.gif']):
                filtered.append(endpoint)

        return filtered

    def detect_spa_routing(self, html_content: str) -> Dict[str, Any]:
        """
        Detect SPA routing configuration.

        Args:
            html_content: HTML content

        Returns:
            Dictionary with routing information
        """
        routing_info = {
            'type': 'unknown',
            'routes': []
        }

        # Check for React Router
        if 'react-router' in html_content or 'BrowserRouter' in html_content:
            routing_info['type'] = 'react-router'

        # Check for Vue Router
        elif 'vue-router' in html_content or 'VueRouter' in html_content:
            routing_info['type'] = 'vue-router'

        # Check for Angular Router
        elif 'RouterModule' in html_content or '@angular/router' in html_content:
            routing_info['type'] = 'angular-router'

        # Try to extract route patterns
        route_patterns = [
            r'path:\s*["\']([^"\']+)["\']',
            r'route:\s*["\']([^"\']+)["\']',
            r'["\']path["\']:\s*["\']([^"\']+)["\']'
        ]

        for pattern in route_patterns:
            matches = re.findall(pattern, html_content)
            routing_info['routes'].extend(matches)

        return routing_info