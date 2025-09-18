#!/usr/bin/env python3
"""
Example usage of hw-scraper's concurrent and async features.
"""

import asyncio
from pathlib import Path
from hw_scraper import (
    Config, AuthManager, AsyncScraper, BatchProcessor,
    WorkerPool, WorkerConfig, WorkerType,
    batch_scrape_courses
)


async def example_async_scraper():
    """Example using the async scraper directly."""
    print("Async Scraper Example")
    print("-" * 40)
    
    # Create configuration
    config = Config()
    auth_manager = AuthManager(config)
    auth_manager.load_from_env()
    
    # Create async scraper
    async with AsyncScraper(config, auth_manager) as scraper:
        # Example URLs (replace with actual)
        urls = [
            # 'https://course.edu/cs101',
            # 'https://course.edu/cs102',
        ]
        
        if not urls:
            print("Add URLs to test async scraping")
            return
        
        # Scrape courses concurrently
        tasks = []
        for url in urls:
            task = scraper.scrape_course(url, f'./downloads/{Path(url).name}')
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Print results
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                print(f"Failed to scrape {url}: {result}")
            else:
                print(f"Scraped {url}: {result.files_downloaded} files")


async def example_batch_processor():
    """Example using the batch processor for multiple courses."""
    print("Batch Processor Example")
    print("-" * 40)
    
    config = Config()
    auth_manager = AuthManager(config)
    auth_manager.load_from_env()
    
    # Configure workers
    worker_config = WorkerConfig(
        max_workers=5,                    # 5 concurrent workers
        worker_type=WorkerType.ASYNC,     # Use async workers
        connection_pool_size=10,          # 10 connections per worker
        enable_checkpointing=True,        # Enable resume capability
        health_check_interval=30          # Health check every 30 seconds
    )
    
    # URLs to process
    urls = [
        # Add your course URLs here
        # 'https://course.edu/cs101',
        # 'https://course.edu/cs102',
        # 'https://course.edu/cs103',
    ]
    
    if not urls:
        print("Add URLs to test batch processing")
        return
    
    # Process courses with batch processor
    async with BatchProcessor(config, auth_manager, worker_config) as processor:
        result = await processor.process_courses(
            urls,
            output_dir='./batch_downloads',
            checkpoint=True,    # Enable checkpointing
            progress=True       # Show progress
        )
        
        print(f"\nBatch Results:")
        print(f"  Total: {result.total_tasks}")
        print(f"  Completed: {result.completed_tasks}")
        print(f"  Failed: {result.failed_tasks}")
        print(f"  Success Rate: {result.success_rate:.1%}")
        print(f"  Files Downloaded: {result.total_files_downloaded}")
        print(f"  Duration: {result.duration:.1f} seconds")


async def example_worker_pool():
    """Example using worker pool directly."""
    print("Worker Pool Example")
    print("-" * 40)
    
    config = Config()
    auth_manager = AuthManager(config)
    auth_manager.load_from_env()
    
    # Create worker pool with thread workers
    worker_config = WorkerConfig(
        max_workers=3,
        worker_type=WorkerType.THREAD,
        queue_size=100
    )
    
    pool = WorkerPool(config, auth_manager, worker_config)
    
    # URLs to process
    urls = [
        # 'https://course.edu/cs101',
        # 'https://course.edu/cs102',
    ]
    
    if not urls:
        print("Add URLs to test worker pool")
        return
    
    # Start pool and process
    pool.start_sync()
    
    try:
        # Submit tasks
        from hw_scraper.models import BatchTask
        from datetime import datetime
        
        for i, url in enumerate(urls):
            task = BatchTask(
                task_id=f"task_{i}",
                url=url,
                created_at=datetime.now()
            )
            pool.submit_task_sync(task)
        
        # Monitor pool status
        import time
        while pool.status.tasks_completed + pool.status.tasks_failed < len(urls):
            status = pool.get_status()
            print(f"Active: {status.active_workers}, "
                  f"Idle: {status.idle_workers}, "
                  f"Queue: {status.tasks_in_queue}, "
                  f"Completed: {status.tasks_completed}")
            time.sleep(2)
        
        print("All tasks completed!")
        
    finally:
        pool.shutdown()


async def example_concurrent_downloads():
    """Example of concurrent file downloads with progress."""
    print("Concurrent Downloads Example")
    print("-" * 40)
    
    config = Config()
    auth_manager = AuthManager(config)
    
    async with AsyncScraper(config, auth_manager) as scraper:
        # Example file URLs
        file_urls = [
            # 'https://example.edu/lecture1.pdf',
            # 'https://example.edu/lecture2.pdf',
            # 'https://example.edu/assignment1.docx',
        ]
        
        if not file_urls:
            print("Add file URLs to test concurrent downloads")
            return
        
        # Download with progress callback
        async def progress_callback(downloaded, total):
            if total > 0:
                percent = (downloaded / total) * 100
                print(f"Progress: {percent:.1f}% ({downloaded}/{total} bytes)")
        
        # Download files concurrently
        download_tasks = []
        for url in file_urls:
            output_path = Path('./downloads') / Path(url).name
            task = scraper.download_with_progress(
                url, output_path, progress_callback
            )
            download_tasks.append(task)
        
        results = await asyncio.gather(*download_tasks)
        
        # Print results
        for url, result in zip(file_urls, results):
            if result.success:
                print(f"✓ Downloaded {url}: {result.bytes_downloaded} bytes")
            else:
                print(f"✗ Failed {url}: {result.error}")


async def example_with_circuit_breaker():
    """Example showing circuit breaker pattern for resilient scraping."""
    print("Circuit Breaker Example")
    print("-" * 40)
    
    config = Config()
    auth_manager = AuthManager(config)
    
    # Use batch processor with circuit breaker
    urls = [
        # Mix of valid and potentially failing URLs
        # 'https://course.edu/valid-course',
        # 'https://failing-site.edu/course',
        # 'https://course.edu/another-course',
    ]
    
    if not urls:
        print("Add URLs to test circuit breaker")
        return
    
    # Use convenience function
    result = await batch_scrape_courses(
        urls, config, auth_manager,
        output_dir='./resilient_downloads'
    )
    
    print(f"Processed {result.total_tasks} courses")
    print(f"Circuit breaker prevented cascading failures")


async def main():
    """Run all examples."""
    print("=" * 50)
    print("hw-scraper Concurrent & Async Examples")
    print("=" * 50)
    print()
    
    # Run examples
    await example_async_scraper()
    print()
    
    await example_batch_processor()
    print()
    
    await example_worker_pool()
    print()
    
    await example_concurrent_downloads()
    print()
    
    await example_with_circuit_breaker()
    
    print()
    print("=" * 50)
    print("Note: Add actual course URLs to test the features")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())