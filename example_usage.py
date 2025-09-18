#!/usr/bin/env python3
"""
Example usage of hw-scraper scriptable API.
"""

from hw_scraper import create_scraper, quick_scrape
from hw_scraper.config import Config
from hw_scraper.auth import AuthManager


def example_basic_usage():
    """Basic usage example."""
    print("Basic Usage Example")
    print("-" * 40)
    
    # Create a scraper with environment variables for auth
    scraper = create_scraper(auth_method='env', impersonate='chrome')
    
    # List courses from a catalog (example URL)
    # courses = scraper.list_courses('https://example.edu/courses')
    # for course in courses:
    #     print(f"Found course: {course.name} - {course.url}")
    
    # Scrape a specific course
    # result = scraper.scrape_course(
    #     url='https://example.edu/courses/cs101',
    #     output_dir='./downloads/cs101',
    #     organize=True
    # )
    # print(f"Downloaded {result.files_downloaded} files from {result.course_name}")
    
    # Always close the scraper when done
    scraper.close()


def example_quick_scrape():
    """Quick scrape example for simple use cases."""
    print("Quick Scrape Example")
    print("-" * 40)
    
    # Quick scrape with minimal configuration
    # result = quick_scrape(
    #     url='https://example.edu/courses/cs101',
    #     output_dir='./downloads',
    #     auth_method='env',
    #     organize=True
    # )
    # 
    # print(f"Course: {result.course_name}")
    # print(f"Files found: {result.files_found}")
    # print(f"Files downloaded: {result.files_downloaded}")
    # print(f"Files failed: {result.files_failed}")
    # print(f"Duration: {result.duration:.2f} seconds")


def example_custom_config():
    """Example with custom configuration."""
    print("Custom Configuration Example")
    print("-" * 40)
    
    # Create custom configuration
    config = Config()
    config.scraper_config.rate_limit = 1.0  # 1 second between requests
    config.scraper_config.parallel_downloads = 5
    config.organization.by_course = True
    config.organization.by_type = True
    
    # Set up authentication
    auth_manager = AuthManager(config)
    
    # Try different auth methods in order of preference
    if not auth_manager.load_from_env():
        if not auth_manager.load_from_keyring():
            print("No credentials found. Please set environment variables:")
            print("  export HW_SCRAPER_USERNAME='your_username'")
            print("  export HW_SCRAPER_PASSWORD='your_password'")
            return
    
    # Create scraper with custom config
    scraper = create_scraper()
    scraper.config = config
    scraper.auth_manager = auth_manager
    
    # Use the scraper...
    # courses = scraper.discover_courses('https://example.edu')
    
    scraper.close()


def example_batch_download():
    """Example of batch downloading from URLs."""
    print("Batch Download Example")
    print("-" * 40)
    
    # URLs to download
    urls = [
        # 'https://example.edu/lectures/lecture1.pdf',
        # 'https://example.edu/lectures/lecture2.pdf',
        # 'https://example.edu/assignments/hw1.pdf',
    ]
    
    if not urls:
        print("No URLs to download. Add URLs to the list to test.")
        return
    
    from hw_scraper.downloader import DownloadManager
    from hw_scraper.config import load_config
    
    config = load_config()
    downloader = DownloadManager(config, parallel=3, show_progress=True)
    
    results = downloader.download_batch(urls, './downloads')
    
    # Print statistics
    stats = downloader.get_download_stats(results)
    print(f"Total files: {stats['total']}")
    print(f"Successful: {stats['successful']}")
    print(f"Failed: {stats['failed']}")
    print(f"Total downloaded: {stats['total_bytes']} bytes")


def example_with_cookies():
    """Example using cookies for authentication."""
    print("Cookie Authentication Example")
    print("-" * 40)
    
    from hw_scraper.auth import AuthManager
    from hw_scraper.config import load_config
    
    config = load_config()
    auth_manager = AuthManager(config)
    
    # Load cookies from file
    # if auth_manager.load_cookies('cookies.json'):
    #     print("Cookies loaded successfully")
    #     
    #     # Create scraper with cookie auth
    #     scraper = create_scraper()
    #     scraper.auth_manager = auth_manager
    #     
    #     # Use the scraper...
    #     scraper.close()
    # else:
    #     print("Failed to load cookies")
    
    print("To use cookie authentication:")
    print("1. Export cookies from your browser")
    print("2. Save them to cookies.json")
    print("3. Uncomment the code above")


if __name__ == "__main__":
    print("=" * 50)
    print("hw-scraper API Examples")
    print("=" * 50)
    print()
    
    example_basic_usage()
    print()
    
    example_quick_scrape()
    print()
    
    example_custom_config()
    print()
    
    example_batch_download()
    print()
    
    example_with_cookies()
    
    print()
    print("=" * 50)
    print("Note: These examples use placeholder URLs.")
    print("Replace with actual course URLs to use.")
    print("=" * 50)