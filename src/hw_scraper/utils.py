"""Utility functions for hw-scraper."""

import re
import json
import hashlib
from typing import Dict, List, Any, Optional
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import logging


def setup_logging(level: str = 'INFO', log_file: Optional[str] = None):
    """
    Set up logging configuration.
    
    Args:
        level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        log_file: Optional log file path
    """
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=handlers
    )


def parse_course_url(url: str) -> Dict[str, str]:
    """
    Parse course URL to extract components.
    
    Args:
        url: Course URL
    
    Returns:
        Dictionary with URL components
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    
    # Try to extract course ID from various patterns
    course_id = None
    path_parts = parsed.path.strip('/').split('/')
    
    for part in path_parts:
        # Common patterns: CS101, cs-101, course-123
        if re.match(r'^[A-Z]{2,4}[-_]?\d{3,4}$', part, re.IGNORECASE):
            course_id = part
            break
        elif re.match(r'^course[-_]\d+$', part, re.IGNORECASE):
            course_id = part
            break
    
    # Check query parameters
    if not course_id:
        for key in ['course', 'id', 'cid', 'course_id']:
            if key in query_params:
                course_id = query_params[key][0]
                break
    
    return {
        'domain': parsed.netloc,
        'path': parsed.path,
        'course_id': course_id,
        'query': dict(query_params),
        'full_url': url
    }


def generate_session_id() -> str:
    """Generate a unique session ID for tracking."""
    timestamp = datetime.now().isoformat()
    return hashlib.md5(timestamp.encode()).hexdigest()[:16]


def format_bytes(size: int) -> str:
    """
    Format bytes to human readable string.
    
    Args:
        size: Size in bytes
    
    Returns:
        Formatted string (e.g., '1.5 MB')
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_duration(seconds: float) -> str:
    """
    Format duration to human readable string.
    
    Args:
        seconds: Duration in seconds
    
    Returns:
        Formatted string (e.g., '1h 30m 45s')
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")
    
    return ' '.join(parts)


def validate_url(url: str) -> bool:
    """
    Validate if string is a valid URL.
    
    Args:
        url: URL string to validate
    
    Returns:
        True if valid URL, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge multiple configuration dictionaries.
    
    Args:
        *configs: Configuration dictionaries to merge
    
    Returns:
        Merged configuration (later configs override earlier ones)
    """
    result = {}
    
    for config in configs:
        if not config:
            continue
        
        for key, value in config.items():
            if isinstance(value, dict) and key in result and isinstance(result[key], dict):
                # Recursively merge dictionaries
                result[key] = merge_configs(result[key], value)
            else:
                result[key] = value
    
    return result


def load_urls_from_file(filepath: str) -> List[str]:
    """
    Load URLs from various file formats.
    
    Args:
        filepath: Path to file containing URLs
    
    Returns:
        List of URLs
    """
    path = Path(filepath)
    
    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")
    
    urls = []
    
    if path.suffix.lower() == '.json':
        with open(path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                urls = [item if isinstance(item, str) else item.get('url', '') for item in data]
            elif isinstance(data, dict):
                urls = data.get('urls', [])
    elif path.suffix.lower() in ['.txt', '.list']:
        with open(path, 'r') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    else:
        # Try to read as plain text
        with open(path, 'r') as f:
            content = f.read()
            # Extract URLs using regex
            url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
            urls = re.findall(url_pattern, content)
    
    # Validate URLs
    return [url for url in urls if validate_url(url)]


def save_results_to_json(results: List[Dict[str, Any]], filepath: str):
    """
    Save scraping results to JSON file.
    
    Args:
        results: List of result dictionaries
        filepath: Output file path
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert Path objects to strings
    def convert_paths(obj):
        if isinstance(obj, dict):
            return {k: convert_paths(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_paths(item) for item in obj]
        elif isinstance(obj, Path):
            return str(obj)
        elif hasattr(obj, 'dict'):  # Pydantic models
            return convert_paths(obj.dict())
        else:
            return obj
    
    data = convert_paths(results)
    
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def create_download_report(results: List[Any]) -> str:
    """
    Create a markdown report of download results.
    
    Args:
        results: List of DownloadResult objects
    
    Returns:
        Markdown formatted report
    """
    report = ["# Download Report\n\n"]
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    # Summary statistics
    total = len(results)
    successful = sum(1 for r in results if r.success)
    failed = total - successful
    total_bytes = sum(r.bytes_downloaded or 0 for r in results if r.success)
    
    report.append("## Summary\n\n")
    report.append(f"- Total files: {total}\n")
    report.append(f"- Successful: {successful}\n")
    report.append(f"- Failed: {failed}\n")
    report.append(f"- Total downloaded: {format_bytes(total_bytes)}\n\n")
    
    # Successful downloads
    if successful > 0:
        report.append("## Successful Downloads\n\n")
        for r in results:
            if r.success:
                report.append(f"- ✓ {r.file.name}")
                if r.bytes_downloaded:
                    report.append(f" ({format_bytes(r.bytes_downloaded)})")
                if r.download_time:
                    report.append(f" - {r.download_time:.1f}s")
                report.append("\n")
        report.append("\n")
    
    # Failed downloads
    if failed > 0:
        report.append("## Failed Downloads\n\n")
        for r in results:
            if not r.success:
                report.append(f"- ✗ {r.file.name}")
                if r.error:
                    report.append(f": {r.error}")
                report.append("\n")
        report.append("\n")
    
    return ''.join(report)


def sanitize_path(path: str, max_length: int = 255) -> str:
    """
    Sanitize path for filesystem compatibility.
    
    Args:
        path: Path string to sanitize
        max_length: Maximum length for path components
    
    Returns:
        Sanitized path string
    """
    # Split into components
    parts = Path(path).parts
    
    sanitized_parts = []
    for part in parts:
        # Skip drive letters on Windows
        if len(part) == 2 and part[1] == ':':
            sanitized_parts.append(part)
            continue
        
        # Remove invalid characters
        invalid_chars = '<>:"|?*\0'
        for char in invalid_chars:
            part = part.replace(char, '_')
        
        # Remove control characters
        part = ''.join(char for char in part if ord(char) >= 32)
        
        # Limit length
        if len(part) > max_length:
            # Preserve extension if present
            if '.' in part:
                name, ext = part.rsplit('.', 1)
                max_name_length = max_length - len(ext) - 1
                part = f"{name[:max_name_length]}.{ext}"
            else:
                part = part[:max_length]
        
        # Ensure not empty
        if not part:
            part = 'unnamed'
        
        sanitized_parts.append(part)
    
    return str(Path(*sanitized_parts))


class RateLimiter:
    """Simple rate limiter for API calls."""
    
    def __init__(self, calls_per_second: float = 1.0):
        """
        Initialize rate limiter.
        
        Args:
            calls_per_second: Maximum calls per second
        """
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0
    
    def wait_if_needed(self):
        """Wait if necessary to maintain rate limit."""
        import time
        current = time.time()
        elapsed = current - self.last_call
        
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        
        self.last_call = time.time()