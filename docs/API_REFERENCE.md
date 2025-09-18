# API Reference

## Crawler Module

### `crawler.BaseCrawler`

Abstract base class for web crawlers.

#### Constructor

```python
BaseCrawler(
    config: Config,
    session: Optional[requests.Session] = None,
    respect_robots: bool = True,
    max_depth: int = -1,
    max_urls: int = -1,
    allowed_domains: Optional[List[str]] = None,
    url_filter: Optional[Callable[[str], bool]] = None
)
```

**Parameters:**
- `config`: Application configuration object
- `session`: HTTP session to use (creates new if None)
- `respect_robots`: Whether to respect robots.txt (default: True)
- `max_depth`: Maximum crawl depth, -1 for unlimited (default: -1)
- `max_urls`: Maximum URLs to crawl, -1 for unlimited (default: -1)
- `allowed_domains`: List of allowed domains to crawl
- `url_filter`: Custom URL filter function

#### Methods

##### `crawl(start_url: str) -> CrawlResult`
Abstract method to be implemented by subclasses.

##### `reset()`
Reset crawler state for new crawl.

---

### `crawler.BFSCrawler`

Breadth-first search crawler implementation.

#### Methods

##### `crawl(start_url: str, use_sitemap: bool = True) -> CrawlResult`

Crawl website using BFS algorithm.

**Parameters:**
- `start_url`: URL to start crawling from
- `use_sitemap`: Whether to use sitemap for URL discovery (default: True)

**Returns:** CrawlResult object containing discovered URLs and statistics

##### `crawl_parallel(start_url: str, max_workers: int = 5) -> CrawlResult`

Crawl website using parallel BFS (future implementation).

---

### `crawler.DFSCrawler`

Depth-first search crawler implementation.

#### Methods

##### `crawl(start_url: str, use_sitemap: bool = True) -> CrawlResult`

Crawl website using DFS algorithm (iterative).

##### `crawl_recursive(start_url: str, use_sitemap: bool = True) -> CrawlResult`

Crawl website using recursive DFS implementation.

---

### `crawler.CrawlResult`

Data class for crawl results.

#### Attributes

- `start_url: str` - Starting URL
- `discovered_urls: Set[str]` - All discovered URLs
- `visited_urls: Set[str]` - Successfully visited URLs
- `failed_urls: Dict[str, str]` - Failed URLs with error messages
- `start_time: datetime` - Crawl start time
- `end_time: Optional[datetime]` - Crawl end time
- `max_depth_reached: int` - Maximum depth reached

#### Properties

- `duration: float` - Crawl duration in seconds
- `success_rate: float` - Success rate (0.0 to 1.0)

---

### `crawler.RobotsParser`

Parser for robots.txt files.

#### Constructor

```python
RobotsParser(session: Optional[requests.Session] = None)
```

#### Methods

##### `fetch_robots(url: str, user_agent: str = '*') -> Optional[RobotFileParser]`

Fetch and parse robots.txt for given URL.

**Parameters:**
- `url`: Website URL
- `user_agent`: User agent string to check rules for (default: '*')

**Returns:** RobotFileParser instance or None if not found

##### `can_fetch(url: str, user_agent: str = '*') -> bool`

Check if URL can be fetched according to robots.txt.

##### `get_crawl_delay(url: str) -> float`

Get crawl delay for given URL in seconds.

##### `get_sitemaps(url: str) -> List[str]`

Get sitemap URLs from robots.txt.

##### `get_allowed_paths(url: str, user_agent: str = '*') -> Set[str]`

Get explicitly allowed paths from robots.txt.

##### `get_disallowed_paths(url: str, user_agent: str = '*') -> Set[str]`

Get disallowed paths from robots.txt.

##### `apply_crawl_delay(url: str)`

Apply crawl delay if specified in robots.txt.

##### `clear_cache()`

Clear all cached robots.txt data.

---

### `crawler.SitemapParser`

Parser for XML and HTML sitemaps.

#### Constructor

```python
SitemapParser(session: Optional[requests.Session] = None)
```

#### Methods

##### `parse_sitemap(sitemap_url: str) -> Set[str]`

Parse sitemap and extract all URLs.

**Parameters:**
- `sitemap_url`: URL of the sitemap

**Returns:** Set of discovered URLs

##### `find_sitemaps(base_url: str) -> List[str]`

Try to find sitemaps for a website.

**Parameters:**
- `base_url`: Base URL of the website

**Returns:** List of discovered sitemap URLs

##### `parse_sitemap_with_metadata(sitemap_url: str) -> List[Dict[str, Any]]`

Parse sitemap with metadata like lastmod, changefreq, priority.

**Returns:** List of URL entries with metadata

---

## Scraper Module

### `scraper.HTMLScraper`

Enhanced HTML content scraper.

#### Constructor

```python
HTMLScraper(
    config: Config,
    session: Optional[requests.Session] = None
)
```

#### Methods

##### `scrape_page(url: str, extraction_rules: Optional[Dict[str, str]] = None) -> Dict[str, Any]`

Scrape page with custom extraction rules.

**Parameters:**
- `url`: Page URL
- `extraction_rules`: Dictionary of field names to XPath expressions

**Returns:** Extracted data dictionary

##### `extract_course_materials(url: str, custom_rules: Optional[Dict[str, str]] = None) -> List[CourseFile]`

Extract course materials from a page.

##### `extract_with_patterns(url: str, patterns: Dict[str, str]) -> Dict[str, List[str]]`

Extract content using regex patterns.

##### `extract_tables(url: str, table_selector: str = '//table') -> List[List[Dict[str, str]]]`

Extract all tables from page.

##### `extract_academic_content(url: str) -> Dict[str, Any]`

Extract academic content with specialized rules.

---

### `scraper.XPathExtractor`

Advanced XPath-based content extractor.

#### Constructor

```python
XPathExtractor()
```

#### Methods

##### `extract(html_content: str, xpath: str, extract_type: str = 'text', single: bool = False, default: Any = None) -> Union[Any, List[Any]]`

Extract content using XPath.

**Parameters:**
- `html_content`: HTML content to parse
- `xpath`: XPath expression
- `extract_type`: Type of extraction ('text', 'html', 'attribute', 'all')
- `single`: Return single element instead of list
- `default`: Default value if nothing found

**Returns:** Extracted content or default value

##### `extract_with_css(html_content: str, css_selector: str, extract_type: str = 'text', single: bool = False, default: Any = None) -> Union[Any, List[Any]]`

Extract content using CSS selector (converted to XPath).

##### `extract_table(html_content: str, table_xpath: str = '//table', headers_xpath: str = './/thead//th', rows_xpath: str = './/tbody//tr') -> List[Dict[str, str]]`

Extract table data as list of dictionaries.

##### `extract_links(html_content: str, link_xpath: str = '//a[@href]', absolute: bool = True, base_url: Optional[str] = None) -> List[Dict[str, str]]`

Extract links with text and URL.

##### `extract_metadata(html_content: str) -> Dict[str, Any]`

Extract common metadata from HTML.

##### `extract_structured_data(html_content: str) -> List[Dict[str, Any]]`

Extract JSON-LD structured data.

##### `extract_forms(html_content: str) -> List[Dict[str, Any]]`

Extract form information.

---

### `scraper.JSDetector`

Detector for JavaScript-rendered content.

#### Constructor

```python
JSDetector()
```

#### Methods

##### `detect_javascript(html_content: str) -> Dict[str, Any]`

Detect JavaScript usage in HTML content.

**Returns:** Dictionary with:
- `uses_javascript: bool` - Whether page uses JavaScript
- `requires_js_rendering: bool` - Whether JS rendering is required
- `frameworks: List[str]` - Detected JS frameworks
- `indicators: List[str]` - JS indicators found
- `dynamic_content_score: int` - Score from 0-100

##### `extract_js_data(html_content: str) -> Dict[str, Any]`

Extract embedded JavaScript data.

---

### `scraper.JSRenderer`

JavaScript renderer for dynamic content.

#### Constructor

```python
JSRenderer(method: str = 'curl_cffi')
```

**Parameters:**
- `method`: Rendering method ('curl_cffi', 'selenium', 'playwright')

#### Methods

##### `render(url: str, wait_for: Optional[str] = None, timeout: int = 30) -> str`

Render JavaScript-heavy page.

**Parameters:**
- `url`: Page URL
- `wait_for`: Element selector to wait for
- `timeout`: Timeout in seconds

**Returns:** Rendered HTML content

##### `check_rendering_required(html_content: str) -> bool`

Check if JS rendering is required.

##### `extract_ajax_endpoints(html_content: str) -> List[str]`

Extract AJAX/API endpoints from JavaScript code.

##### `detect_spa_routing(html_content: str) -> Dict[str, Any]`

Detect SPA routing configuration.

---

## Data Models

### `CourseFile`

```python
@dataclass
class CourseFile:
    name: str
    url: str
    type: FileType
    description: Optional[str] = None
    date: Optional[datetime] = None
    size: Optional[int] = None
    local_path: Optional[str] = None
```

### `FileType` (Enum)

```python
class FileType(str, Enum):
    LECTURE_VIDEO = "lecture_video"
    LECTURE_SLIDE = "lecture_slide"
    ASSIGNMENT = "assignment"
    SYLLABUS = "syllabus"
    READING = "reading"
    RESOURCE = "resource"
    OTHER = "other"
```

---

## Configuration

### `Config`

Main configuration class.

```python
config = Config()
config.scraper_config.rate_limit = 1.0  # 1 second between requests
config.scraper_config.max_retries = 3
config.scraper_config.timeout = 30
```

### Key Configuration Options

- `scraper_config.rate_limit`: Delay between requests (seconds)
- `scraper_config.max_retries`: Maximum retry attempts
- `scraper_config.timeout`: Request timeout (seconds)
- `scraper_config.verify_ssl`: SSL verification
- `scraper_config.follow_redirects`: Follow HTTP redirects
- `scraper_config.user_agents`: List of user agents for rotation