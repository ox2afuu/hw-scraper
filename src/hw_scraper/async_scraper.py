"""Fully async implementation of the scraper using httpx and aiohttp."""

import asyncio
import time
import logging
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
from pathlib import Path
from datetime import datetime
import aiofiles
import httpx
import aiohttp

from hw_scraper.config import Config
from hw_scraper.auth import AuthManager
from hw_scraper.models import (
    Course, CourseFile, ScrapeResult, FileType,
    DownloadResult, BatchTask, BatchResult
)
from hw_scraper.parser import ContentParser
from hw_scraper.organizer import FileOrganizer
from hw_scraper.session_manager import AsyncSessionManager, ConnectionPool, SessionMetrics
from hw_scraper.concurrency import (
    AsyncRateLimiter, AsyncSemaphorePool, AsyncCircuitBreaker,
    ExponentialBackoff, AsyncTaskQueue, safe_async_execute
)

logger = logging.getLogger(__name__)


class AsyncScraper:
    """Fully async scraper implementation."""
    
    def __init__(self, config: Config, auth_manager: AuthManager):
        self.config = config
        self.auth_manager = auth_manager
        self.session_manager = AsyncSessionManager(config, auth_manager)
        self.connection_pool = ConnectionPool(config)
        self.parser = ContentParser()
        self.organizer = FileOrganizer(config)
        
        # Concurrency controls
        self.rate_limiter = AsyncRateLimiter(config.scraper_config.rate_limit)
        self.semaphore_pool = AsyncSemaphorePool(default_limit=5)
        self.circuit_breaker = AsyncCircuitBreaker()
        self.backoff = ExponentialBackoff()
        
        # Metrics
        self.metrics = SessionMetrics()
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connection_pool.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def _make_request(self, url: str, method: str = 'GET', **kwargs) -> httpx.Response:
        """Make async HTTP request with retry logic."""
        domain = urlparse(url).netloc
        
        # Check circuit breaker
        if await self.circuit_breaker.is_open(domain):
            raise Exception(f"Circuit breaker open for {domain}")
        
        last_error = None
        
        for attempt in range(self.config.scraper_config.max_retries):
            try:
                if attempt > 0:
                    await self.backoff.wait(attempt)
                
                # Use session manager for request
                async with self.session_manager.httpx_context(url) as client:
                    start_time = time.time()
                    response = await client.request(method, url, **kwargs)
                    response.raise_for_status()
                    
                    # Record metrics
                    latency = time.time() - start_time
                    self.metrics.record_request(domain, len(response.content), latency)
                    
                    # Record success for circuit breaker
                    await self.circuit_breaker.record_success(domain)
                    
                    return response
                    
            except Exception as e:
                last_error = e
                self.metrics.record_error(domain)
                await self.circuit_breaker.record_failure(domain)
                
                if attempt < self.config.scraper_config.max_retries - 1:
                    logger.warning(f"Request failed for {url}, attempt {attempt + 1}: {e}")
                else:
                    logger.error(f"All retries failed for {url}: {e}")
        
        raise last_error or Exception(f"Failed to fetch {url}")
    
    async def scrape_course(self, url: str, output_dir: str = './downloads',
                          organize: bool = True) -> ScrapeResult:
        """Scrape course asynchronously."""
        start_time = time.time()
        
        result = ScrapeResult(
            course_name="Unknown Course",
            course_url=url,
            files_found=0,
            files_downloaded=0,
            files_failed=0,
            duration=0
        )
        
        try:
            # Fetch course page
            response = await self._make_request(url)
            content = response.text
            
            # Parse course information
            course_info = self.parser.parse_course_page(content, url)
            result.course_name = course_info.get('name', 'Unknown Course')
            
            # Extract files
            files = self.parser.extract_course_files(content, url)
            result.files_found = len(files)
            
            # Set up output directory
            output_path = Path(output_dir)
            if organize:
                output_path = self.organizer.setup_course_directory(
                    output_path,
                    result.course_name
                )
            
            # Download files concurrently
            download_tasks = []
            domain = urlparse(url).netloc
            
            async with self.semaphore_pool.acquire(domain, limit=3):
                for file in files:
                    task = self._download_file(file, output_path, organize)
                    download_tasks.append(task)
                
                # Process downloads with concurrency limit
                download_results = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            # Process results
            for i, download_result in enumerate(download_results):
                if isinstance(download_result, Exception):
                    result.files_failed += 1
                    result.errors.append(str(download_result))
                elif download_result and download_result.success:
                    result.files_downloaded += 1
                    files[i].local_path = download_result.local_path
                else:
                    result.files_failed += 1
                    if download_result and download_result.error:
                        result.errors.append(download_result.error)
            
            result.files = files
            
        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"Error scraping course {url}: {e}")
        
        result.duration = time.time() - start_time
        return result
    
    async def _download_file(self, file: CourseFile, output_path: Path,
                           organize: bool) -> DownloadResult:
        """Download a single file asynchronously."""
        result = DownloadResult(
            file=file,
            success=False
        )
        
        try:
            # Determine output file path
            filename = file.name or self._extract_filename(str(file.url))
            file_path = output_path / filename
            
            # Download file
            response = await self._make_request(str(file.url))
            content = response.content
            
            # Write file asynchronously
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            
            # Organize if needed
            if organize:
                file_path = self.organizer.organize_file(
                    file_path,
                    file.type,
                    file.course_name or "Unknown"
                )
            
            result.success = True
            result.local_path = file_path
            result.bytes_downloaded = len(content)
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"Error downloading {file.url}: {e}")
        
        return result
    
    async def scrape_batch(self, urls: List[str], output_dir: str = './downloads',
                         organize: bool = True, max_concurrent: int = 3) -> BatchResult:
        """Scrape multiple courses concurrently."""
        batch_id = f"batch_{datetime.now().isoformat()}"
        start_time = datetime.now()
        
        result = BatchResult(
            batch_id=batch_id,
            total_tasks=len(urls),
            completed_tasks=0,
            failed_tasks=0,
            in_progress_tasks=0,
            total_files_downloaded=0,
            total_bytes_downloaded=0,
            start_time=start_time
        )
        
        # Create tasks
        tasks = []
        for i, url in enumerate(urls):
            task = BatchTask(
                task_id=f"task_{i}",
                url=url,
                created_at=datetime.now()
            )
            result.tasks.append(task)
            tasks.append(self._process_batch_task(task, output_dir, organize))
        
        # Process with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_with_semaphore(task_coro, batch_task):
            async with semaphore:
                batch_task.status = "processing"
                batch_task.started_at = datetime.now()
                result.in_progress_tasks += 1
                
                try:
                    scrape_result = await task_coro
                    batch_task.status = "completed"
                    batch_task.completed_at = datetime.now()
                    result.completed_tasks += 1
                    result.total_files_downloaded += scrape_result.files_downloaded
                    return scrape_result
                except Exception as e:
                    batch_task.status = "failed"
                    batch_task.error = str(e)
                    batch_task.completed_at = datetime.now()
                    result.failed_tasks += 1
                    result.errors.append(str(e))
                    return None
                finally:
                    result.in_progress_tasks -= 1
        
        # Execute all tasks
        scrape_tasks = [
            process_with_semaphore(task_coro, batch_task)
            for task_coro, batch_task in zip(tasks, result.tasks)
        ]
        
        await asyncio.gather(*scrape_tasks, return_exceptions=True)
        
        # Finalize result
        result.end_time = datetime.now()
        result.duration = (result.end_time - start_time).total_seconds()
        
        return result
    
    async def _process_batch_task(self, task: BatchTask, output_dir: str,
                                 organize: bool) -> ScrapeResult:
        """Process a single batch task."""
        return await self.scrape_course(str(task.url), output_dir, organize)
    
    async def list_courses(self, catalog_url: str) -> List[Course]:
        """List courses from catalog asynchronously."""
        try:
            response = await self._make_request(catalog_url)
            courses = self.parser.parse_course_catalog(response.text, catalog_url)
            return courses
        except Exception as e:
            logger.error(f"Failed to list courses from {catalog_url}: {e}")
            return []
    
    async def download_with_progress(self, url: str, output_path: Path,
                                   progress_callback=None) -> DownloadResult:
        """Download file with progress reporting."""
        result = DownloadResult(
            file=CourseFile(
                name=output_path.name,
                url=url,
                type=FileType.OTHER
            ),
            success=False
        )
        
        try:
            async with self.session_manager.httpx_context(url) as client:
                async with client.stream('GET', url) as response:
                    response.raise_for_status()
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    async with aiofiles.open(output_path, 'wb') as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            await f.write(chunk)
                            downloaded += len(chunk)
                            
                            if progress_callback:
                                await progress_callback(downloaded, total_size)
            
            result.success = True
            result.local_path = output_path
            result.bytes_downloaded = downloaded
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"Error downloading {url}: {e}")
        
        return result
    
    def _extract_filename(self, url: str) -> str:
        """Extract filename from URL."""
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        if '/' in path:
            filename = path.split('/')[-1]
        else:
            filename = path
        
        if not filename or '.' not in filename:
            filename = f"file_{hash(url) % 10000}.bin"
        
        return filename
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get scraper metrics."""
        return self.metrics.get_stats()
    
    async def close(self):
        """Close all resources."""
        await self.session_manager.close_all()
        await self.connection_pool.close()