# Crawler/Scraper Architecture Guide

## Overview

The hw-scraper has been refactored to separate **crawling** (URL discovery) from **scraping** (content extraction). This modular architecture provides better control, compliance with web standards, and improved performance.

## Architecture

```
hw-scraper/
├── crawler/           # URL discovery and site traversal
│   ├── base_crawler   # Abstract base class
│   ├── bfs_crawler    # Breadth-first search
│   ├── dfs_crawler    # Depth-first search
│   ├── robots_parser  # Robots.txt compliance
│   └── sitemap_parser # Sitemap processing
└── scraper/          # Content extraction
    ├── html_scraper   # HTML content extraction
    ├── xpath_extractor # XPath-based extraction
    └── js_renderer    # JavaScript detection/rendering
```

## Quick Start

### 1. Crawling - Discover URLs

```python
from hw_scraper.crawler import BFSCrawler
from hw_scraper.config import Config

config = Config()
crawler = BFSCrawler(
    config=config,
    max_depth=3,
    max_urls=100,
    respect_robots=True
)

result = crawler.crawl("https://example.com")
print(f"Discovered {len(result.discovered_urls)} URLs")
```

### 2. Scraping - Extract Content

```python
from hw_scraper.scraper import HTMLScraper, XPathExtractor

scraper = HTMLScraper(config)
extractor = XPathExtractor()

# Custom extraction rules
rules = {
    'title': '//h1/text()',
    'links': '//a[@href]',
    'images': '//img[@src]'
}

data = scraper.scrape_page("https://example.com", rules)
```

## CLI Commands

### Crawl Command
Discover URLs using BFS or DFS algorithms.

```bash
# Basic crawl with BFS
python -m hw_scraper crawl -u https://example.com --algorithm bfs

# Deep crawl with DFS
python -m hw_scraper crawl -u https://example.com --algorithm dfs --max-depth 5

# Crawl with domain restrictions
python -m hw_scraper crawl -u https://example.com --domains example.com sub.example.com

# Save discovered URLs
python -m hw_scraper crawl -u https://example.com --output urls.json
```

**Options:**
- `--algorithm`: Choose between `bfs` or `dfs` (default: bfs)
- `--max-depth`: Maximum crawl depth (default: 3, -1 for unlimited)
- `--max-urls`: Maximum URLs to crawl (default: 100)
- `--domains`: Allowed domains to crawl
- `--no-robots`: Ignore robots.txt
- `--use-sitemap`: Use sitemap for URL discovery
- `--filter`: Regex pattern to filter URLs
- `--output`: Save results to file

### Analyze Command
Analyze pages for JavaScript requirements and structure.

```bash
# Check JavaScript requirements
python -m hw_scraper analyze -u https://example.com --check-js

# Extract specific content with XPath
python -m hw_scraper analyze -u https://example.com \
    --extract-xpath "//h1/text()" "//meta[@name='description']/@content"

# Extract all tables and forms
python -m hw_scraper analyze -u https://example.com \
    --extract-tables --extract-forms --output analysis.json
```

**Options:**
- `--check-js`: Analyze JavaScript usage
- `--extract-xpath`: XPath expressions to extract
- `--extract-tables`: Extract all tables
- `--extract-forms`: Extract form information
- `--extract-links`: Extract all links
- `--output`: Save analysis results

### Robots Command
Check robots.txt compliance.

```bash
# Check robots.txt rules
python -m hw_scraper robots -u https://example.com

# Check if specific URL is allowed
python -m hw_scraper robots -u https://example.com \
    --check-url https://example.com/admin

# Show sitemaps and crawl delay
python -m hw_scraper robots -u https://example.com \
    --show-sitemaps --show-delay

# Check for specific user agent
python -m hw_scraper robots -u https://example.com \
    --user-agent "Googlebot"
```

### Sitemap Command
Parse and extract URLs from sitemaps.

```bash
# Parse specific sitemap
python -m hw_scraper sitemap -u https://example.com/sitemap.xml

# Auto-discover and parse sitemaps
python -m hw_scraper sitemap --website https://example.com

# Save URLs in different formats
python -m hw_scraper sitemap --website https://example.com \
    --output urls.csv --format csv
```

## Python API

### Crawler Module

#### BFSCrawler
Breadth-first search crawler for level-by-level exploration.

```python
from hw_scraper.crawler import BFSCrawler

crawler = BFSCrawler(
    config=config,
    respect_robots=True,    # Respect robots.txt
    max_depth=3,            # Maximum depth to crawl
    max_urls=100,           # Maximum URLs to visit
    allowed_domains=['example.com']  # Domain restrictions
)

result = crawler.crawl(
    start_url="https://example.com",
    use_sitemap=True  # Use sitemap for URL discovery
)

# Access results
print(f"Visited: {len(result.visited_urls)}")
print(f"Failed: {len(result.failed_urls)}")
print(f"Duration: {result.duration}s")
```

#### DFSCrawler
Depth-first search crawler for deep exploration.

```python
from hw_scraper.crawler import DFSCrawler

crawler = DFSCrawler(config=config, max_depth=5)

# Iterative DFS
result = crawler.crawl("https://example.com")

# Recursive DFS (alternative implementation)
result = crawler.crawl_recursive("https://example.com")
```

#### RobotsParser
Parse and enforce robots.txt rules.

```python
from hw_scraper.crawler import RobotsParser

parser = RobotsParser()

# Check if URL is allowed
allowed = parser.can_fetch("https://example.com/page", user_agent="*")

# Get crawl delay
delay = parser.get_crawl_delay("https://example.com")

# Get sitemap URLs
sitemaps = parser.get_sitemaps("https://example.com")

# Apply crawl delay automatically
parser.apply_crawl_delay("https://example.com")
```

#### SitemapParser
Parse XML and HTML sitemaps.

```python
from hw_scraper.crawler import SitemapParser

parser = SitemapParser()

# Parse sitemap
urls = parser.parse_sitemap("https://example.com/sitemap.xml")

# Auto-discover sitemaps
sitemaps = parser.find_sitemaps("https://example.com")

# Parse with metadata
entries = parser.parse_sitemap_with_metadata("https://example.com/sitemap.xml")
for entry in entries:
    print(f"URL: {entry['url']}, LastMod: {entry.get('lastmod')}")
```

### Scraper Module

#### XPathExtractor
Advanced content extraction using XPath.

```python
from hw_scraper.scraper import XPathExtractor

extractor = XPathExtractor()

# Extract text content
titles = extractor.extract(
    html_content,
    xpath="//h1/text()",
    extract_type="text"
)

# Extract HTML fragments
articles = extractor.extract(
    html_content,
    xpath="//article",
    extract_type="html"
)

# Extract single element
main_title = extractor.extract(
    html_content,
    xpath="//h1[1]/text()",
    single=True,
    default="No title"
)

# Extract tables
tables = extractor.extract_table(html_content)

# Extract metadata
metadata = extractor.extract_metadata(html_content)

# Extract forms
forms = extractor.extract_forms(html_content)
```

#### JSDetector
Detect JavaScript requirements.

```python
from hw_scraper.scraper import JSDetector

detector = JSDetector()

# Analyze JavaScript usage
analysis = detector.detect_javascript(html_content)

if analysis['requires_js_rendering']:
    print(f"JS Frameworks: {analysis['frameworks']}")
    print(f"Dynamic Score: {analysis['dynamic_content_score']}/100")

# Extract embedded JS data
js_data = detector.extract_js_data(html_content)
```

#### HTMLScraper
Enhanced HTML content scraping.

```python
from hw_scraper.scraper import HTMLScraper

scraper = HTMLScraper(config)

# Scrape with custom rules
rules = {
    'course_title': '//h1[@class="course-title"]/text()',
    'instructor': '//*[@class="instructor"]/text()',
    'materials': '//a[contains(@href, ".pdf")]'
}

data = scraper.scrape_page("https://example.com/course", rules)

# Extract course materials
materials = scraper.extract_course_materials("https://example.com/course")

# Extract academic content
academic_data = scraper.extract_academic_content("https://example.com/course")
```

## Advanced Usage

### Custom URL Filtering

```python
def custom_filter(url: str) -> bool:
    """Only crawl URLs containing 'courses'"""
    return 'courses' in url.lower()

crawler = BFSCrawler(
    config=config,
    url_filter=custom_filter
)
```

### Combining Crawling and Scraping

```python
# First, discover URLs
crawler = BFSCrawler(config=config, max_depth=2)
crawl_result = crawler.crawl("https://example.com")

# Then, scrape discovered pages
scraper = HTMLScraper(config)
for url in crawl_result.visited_urls:
    data = scraper.scrape_page(url)
    # Process extracted data
```

### Respecting Rate Limits

```python
# Get crawl delay from robots.txt
parser = RobotsParser()
delay = parser.get_crawl_delay("https://example.com")

# Configure crawler with delay
config.scraper_config.rate_limit = max(delay, 1.0)
crawler = BFSCrawler(config=config)
```

### JavaScript Detection Workflow

```python
detector = JSDetector()
scraper = HTMLScraper(config)

# Check if JS rendering is needed
response = scraper.session.get(url)
js_analysis = detector.detect_javascript(response.text)

if js_analysis['requires_js_rendering']:
    # Use JS renderer (future implementation)
    print("Page requires JavaScript rendering")
    print(f"Frameworks: {js_analysis['frameworks']}")
else:
    # Regular HTML extraction
    data = scraper.scrape_page(url)
```

## Best Practices

### 1. Respect robots.txt
Always check robots.txt before crawling:

```python
crawler = BFSCrawler(config=config, respect_robots=True)
```

### 2. Use appropriate crawl delays
Implement delays to avoid overwhelming servers:

```python
config.scraper_config.rate_limit = 1.0  # 1 second between requests
```

### 3. Set reasonable limits
Prevent infinite crawling:

```python
crawler = BFSCrawler(
    config=config,
    max_depth=3,     # Limit depth
    max_urls=100     # Limit total URLs
)
```

### 4. Handle failures gracefully
Check failed URLs and implement retry logic:

```python
result = crawler.crawl(start_url)
if result.failed_urls:
    print(f"Failed URLs: {result.failed_urls}")
    # Implement retry logic
```

### 5. Use domain restrictions
Stay within intended scope:

```python
crawler = BFSCrawler(
    config=config,
    allowed_domains=['example.com', 'subdomain.example.com']
)
```

## Performance Tips

1. **Use BFS for broad discovery**: Better for finding all pages at shallow depths
2. **Use DFS for deep content**: More memory-efficient for deep hierarchies
3. **Leverage sitemaps**: Faster than crawling for full site discovery
4. **Cache robots.txt**: Avoid repeated fetches
5. **Batch processing**: Process multiple URLs concurrently when possible

## Troubleshooting

### Issue: Crawler not finding URLs
- Check robots.txt restrictions
- Verify JavaScript rendering requirements
- Ensure correct domain settings

### Issue: Slow crawling
- Check crawl delay in robots.txt
- Reduce max_depth
- Use sitemap for faster discovery

### Issue: Memory usage
- Use DFS instead of BFS for deep sites
- Reduce max_urls limit
- Clear crawler cache periodically

## Future Enhancements

- Full JavaScript rendering with Selenium/Playwright
- Distributed crawling support
- Advanced duplicate detection
- Content change monitoring
- API endpoint discovery
- GraphQL schema extraction