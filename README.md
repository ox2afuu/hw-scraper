# hw-scraper

A powerful web scraper for downloading course materials with anti-detection capabilities using TLS fingerprinting.

## Features

- **Advanced Concurrency**:
  - Fully async implementation with httpx/aiohttp.
  - Thread-safe session management with connection pooling.
  - Process/thread/async worker pools for scalability.
  - Non-blocking I/O for all operations.
- **Multiple Authentication Methods**:
  - Environment variables.
  - System keyring (secure credential storage).
  - Cookie-based authentication.
  - Interactive prompt.
- **Smart File Organization**:
  - Automatic sorting by course name and file type.
  - Configurable directory structure.
  - Duplicate detection and handling.
- **Batch Processing**:
  - Process multiple courses concurrently.
  - Checkpointing for resume capability.
  - Progress tracking across workers.
  - Automatic load balancing.
- **Resilience Features**:
  - Circuit breaker pattern for failing services.
  - Exponential backoff with jitter.
  - Rate limiting per domain.
  - Health monitoring for workers.
- **Multiple Input Formats**: JSON, XML, CSV, plain text, or stdin.
- **CLI & API**: Both command-line interface and scriptable Python API.
- **Configurable**: Python or JSON configuration files with environment variable overrides.

## Installation

```bash
# Clone the repository
git clone [https://github.com/yourusername/hw-scraper.git](https://github.com/yourusername/hw-scraper.git)
cd hw-scraper

# Install with Poetry
poetry install

# Or install with pip
pip install -e .
```

## Quick Start

### CLI Usage

```bash
# Initialize configuration
poetry run python -m hw_scraper config init

# Set credentials via environment variables
export HW_SCRAPER_USERNAME="your_username"
export HW_SCRAPER_PASSWORD="your_password"

# Scrape a course
poetry run python -m hw_scraper scrape --url "[https://course.edu/cs101](https://course.edu/cs101)"

# Download from a list of URLs
poetry run python -m hw_scraper download --input urls.json --output ./downloads

# List available courses
poetry run python -m hw_scraper list --url "[https://course.edu/catalog](https://course.edu/catalog)"

# Use different browser impersonation
poetry run python -m hw_scraper scrape --url "..." --impersonate firefox
```

### Python API Usage

```python
from hw_scraper import create_scraper, quick_scrape

# Quick scrape
result = quick_scrape(
    url='[https://course.edu/cs101](https://course.edu/cs101)',
    output_dir='./downloads',
    auth_method='env',
    organize=True
)
print(f"Downloaded {result.files_downloaded} files")

# Advanced usage
scraper = create_scraper(auth_method='env', impersonate='chrome')
courses = scraper.list_courses('[https://course.edu/catalog](https://course.edu/catalog)')

for course in courses:
    result = scraper.scrape_course(
        url=course.url,
        output_dir=f'./downloads/{course.id}',
        organize=True
    )
    print(f"Scraped {course.name}: {result.files_downloaded} files")

scraper.close()
```

## Configuration

### Environment Variables

```bash
# Authentication
export HW_SCRAPER_USERNAME="username"
export HW_SCRAPER_PASSWORD="password"
export HW_SCRAPER_TOKEN="session_token"

# Optional JSON string for cookies
export HW_SCRAPER_COOKIES='{"session": "..."}'

# Scraper settings
export HW_SCRAPER_DOWNLOAD_PATH="./downloads"
export HW_SCRAPER_BASE_URL="[https://course.edu](https://course.edu)"
export HW_SCRAPER_RATE_LIMIT="0.5" # Seconds between requests
export HW_SCRAPER_BROWSER="chrome" # chrome, firefox, safari, edge
export HW_SCRAPER_PARALLEL="3" # Parallel downloads
export HW_SCRAPER_VERIFY_SSL="true"
```

### Configuration File (config.py)

```python
SCRAPER_CONFIG = {
    'base_url': '[https://course.edu](https://course.edu)',
    'download_path': './downloads',
    'max_retries': 3,
    'rate_limit': 0.5,
    'browser_profile': 'chrome120',
    'parallel_downloads': 3,
}

ORGANIZATION = {
    'by_course': True,
    'by_type': True,
    'sanitize_names': True,
}
```

## File Organization

Downloaded files are automatically organized into a clean structure:

```
downloads/
├── Course_Name_1/
│   ├── lectures/
│   │   ├── videos/
│   │   └── slides/
│   ├── assignments/
│   ├── resources/
│   └── readings/
└── Course_Name_2/
    └── ...
```

## Input Formats

### JSON Format

```json
{
  "urls": [
    "[https://course.edu/lecture1.pdf](https://course.edu/lecture1.pdf)",
    "[https://course.edu/homework1.docx](https://course.edu/homework1.docx)"
  ]
}
```

### XML Format

```xml
<urls>
  <url>[https://course.edu/lecture1.pdf](https://course.edu/lecture1.pdf)</url>
  <url>[https://course.edu/homework1.docx](https://course.edu/homework1.docx)</url>
</urls>
```

### Plain Text

```text
[https://course.edu/lecture1.pdf](https://course.edu/lecture1.pdf)
[https://course.edu/homework1.docx](https://course.edu/homework1.docx)
```

### Via stdin

```bash
cat urls.txt | poetry run python -m hw_scraper scrape --stdin
```

## Authentication Methods

### 1. Environment Variables (Recommended)

```bash
export HW_SCRAPER_USERNAME="your_username"
export HW_SCRAPER_PASSWORD="your_password"
```

### 2. System Keyring (Most Secure)

```bash
# First time: save credentials
poetry run python -m hw_scraper scrape --auth prompt
# Enter credentials when prompted and choose to save

# Future runs: use saved credentials
poetry run python -m hw_scraper scrape --auth keyring
```

### 3. Cookie File

```bash
# Export cookies from browser and save to cookies.json
poetry run python -m hw_scraper scrape --auth cookies --cookies cookies.json
```

### 4. Interactive Prompt

```bash
poetry run python -m hw_scraper scrape --auth prompt
```

## Browser Impersonation

The scraper can impersonate different browsers to avoid detection:

- `chrome` - Chrome 120 (default)
- `firefox` - Firefox 120
- `safari` - Safari 17.0
- `edge` - Edge 120

```bash
# Use Firefox impersonation
poetry run python -m hw_scraper scrape --url "..." --impersonate firefox
```

## Batch Processing (New!)

Process multiple courses concurrently with advanced features:

```bash
#
