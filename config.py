"""Configuration file for hw-scraper."""

# Scraper configuration
SCRAPER_CONFIG = {
    'base_url': None,
    'download_path': 'downloads',
    'max_retries': 3,
    'retry_delay': 1.0,
    'timeout': 30,
    'rate_limit': 0.5,
    'user_agents': ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'],
    'browser_profile': 'chrome120',
    'parallel_downloads': 3,
    'chunk_size': 8192,
    'verify_ssl': True,
    'follow_redirects': True,
}

# File organization settings
ORGANIZATION = {
    'by_course': True,
    'by_type': True,
    'flatten': False,
    'lectures_dir': 'lectures',
    'assignments_dir': 'assignments',
    'resources_dir': 'resources',
    'videos_dir': 'videos',
    'slides_dir': 'slides',
    'sanitize_names': True,
    'preserve_dates': True,
    'add_course_prefix': False,
}

# Worker pool configuration
WORKER_CONFIG = {
    'max_workers': 3,
    'worker_type': 'thread',
    'connection_pool_size': 10,
    'queue_size': 100,
    'enable_checkpointing': True,
    'checkpoint_interval': 60,
    'health_check_interval': 30,
    'max_retries_per_worker': 3,
    'worker_timeout': 300,
}

# Custom settings
CUSTOM = {
}
