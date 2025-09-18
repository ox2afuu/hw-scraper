"""Download manager with progress tracking and parallel downloads."""

import os
import time
import hashlib
import asyncio
import aiofiles
from pathlib import Path
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, unquote

from curl_cffi import requests
from tqdm import tqdm
from rich.console import Console
from rich.progress import (
    Progress, BarColumn, DownloadColumn,
    TransferSpeedColumn, TimeRemainingColumn,
    TextColumn, SpinnerColumn
)

from hw_scraper.config import Config
from hw_scraper.models import CourseFile, DownloadResult, FileType


console = Console()


class DownloadManager:
    """Manages file downloads with progress tracking and parallelization."""
    
    def __init__(self, config: Config, parallel: int = 3, show_progress: bool = True):
        """Initialize download manager."""
        self.config = config
        self.parallel = parallel or config.scraper_config.parallel_downloads
        self.show_progress = show_progress
        self.chunk_size = config.scraper_config.chunk_size
        self.session = None
        self._initialize_session()
    
    def _initialize_session(self):
        """Initialize curl-cffi session for downloads."""
        self.session = requests.Session(
            impersonate=self.config.scraper_config.browser_profile,
            timeout=self.config.scraper_config.timeout,
            verify=self.config.scraper_config.verify_ssl
        )
    
    def download_file(self, url: str, output_path: str,
                     resume: bool = True, verify_checksum: bool = False) -> DownloadResult:
        """Download a single file with progress tracking."""
        start_time = time.time()
        output_file = Path(output_path)
        
        # Create output directory if needed
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Prepare result
        result = DownloadResult(
            file=CourseFile(
                name=output_file.name,
                url=url,
                type=FileType.OTHER
            ),
            success=False
        )
        
        try:
            # Check if file exists and handle resume
            existing_size = 0
            if output_file.exists() and resume:
                existing_size = output_file.stat().st_size
            
            # Make request
            headers = {}
            if existing_size > 0:
                headers['Range'] = f'bytes={existing_size}-'
            
            response = self.session.get(url, headers=headers, stream=True)
            
            # Check if server supports resume
            if existing_size > 0 and response.status_code != 206:
                # Server doesn't support resume, start fresh
                existing_size = 0
                response = self.session.get(url, stream=True)
            
            response.raise_for_status()
            
            # Get file size
            total_size = int(response.headers.get('content-length', 0))
            if response.status_code == 206:
                # Partial content
                total_size += existing_size
            
            # Download with progress
            mode = 'ab' if existing_size > 0 else 'wb'
            bytes_downloaded = existing_size
            
            with open(output_file, mode) as f:
                if self.show_progress and total_size > 0:
                    with tqdm(
                        total=total_size,
                        initial=existing_size,
                        unit='B',
                        unit_scale=True,
                        desc=output_file.name[:30]
                    ) as pbar:
                        for chunk in response.iter_content(chunk_size=self.chunk_size):
                            if chunk:
                                f.write(chunk)
                                bytes_downloaded += len(chunk)
                                pbar.update(len(chunk))
                else:
                    for chunk in response.iter_content(chunk_size=self.chunk_size):
                        if chunk:
                            f.write(chunk)
                            bytes_downloaded += len(chunk)
            
            # Verify download if needed
            if verify_checksum and 'etag' in response.headers:
                if not self._verify_checksum(output_file, response.headers['etag']):
                    raise Exception("Checksum verification failed")
            
            result.success = True
            result.local_path = output_file
            result.bytes_downloaded = bytes_downloaded
            result.download_time = time.time() - start_time
            
        except Exception as e:
            result.error = str(e)
            # Clean up partial download if failed
            if output_file.exists() and output_file.stat().st_size == 0:
                output_file.unlink()
        
        return result
    
    def download_batch(self, urls: List[str], output_dir: str) -> List[DownloadResult]:
        """Download multiple files in parallel."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        results = []
        
        if self.show_progress:
            # Use rich progress for multiple downloads
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                console=console
            ) as progress:
                # Create main task
                main_task = progress.add_task(
                    f"[cyan]Downloading {len(urls)} files...",
                    total=len(urls)
                )
                
                # Download files in parallel
                with ThreadPoolExecutor(max_workers=self.parallel) as executor:
                    # Prepare download tasks
                    future_to_url = {}
                    for url in urls:
                        filename = self._extract_filename(url)
                        output_file = output_path / filename
                        
                        future = executor.submit(
                            self._download_with_retry,
                            url,
                            str(output_file)
                        )
                        future_to_url[future] = url
                    
                    # Process completed downloads
                    for future in as_completed(future_to_url):
                        url = future_to_url[future]
                        try:
                            result = future.result()
                            results.append(result)
                        except Exception as e:
                            result = DownloadResult(
                                file=CourseFile(
                                    name=self._extract_filename(url),
                                    url=url,
                                    type=FileType.OTHER
                                ),
                                success=False,
                                error=str(e)
                            )
                            results.append(result)
                        
                        progress.update(main_task, advance=1)
        else:
            # Download without progress bars
            with ThreadPoolExecutor(max_workers=self.parallel) as executor:
                future_to_url = {}
                for url in urls:
                    filename = self._extract_filename(url)
                    output_file = output_path / filename
                    
                    future = executor.submit(
                        self._download_with_retry,
                        url,
                        str(output_file)
                    )
                    future_to_url[future] = url
                
                for future in as_completed(future_to_url):
                    url = future_to_url[future]
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        result = DownloadResult(
                            file=CourseFile(
                                name=self._extract_filename(url),
                                url=url,
                                type=FileType.OTHER
                            ),
                            success=False,
                            error=str(e)
                        )
                        results.append(result)
        
        return results
    
    def _download_with_retry(self, url: str, output_path: str) -> DownloadResult:
        """Download with retry logic."""
        last_error = None
        
        for attempt in range(self.config.scraper_config.max_retries):
            try:
                if attempt > 0:
                    time.sleep(self.config.scraper_config.retry_delay * (2 ** attempt))
                
                return self.download_file(url, output_path, resume=True)
            except Exception as e:
                last_error = e
        
        # All retries failed
        return DownloadResult(
            file=CourseFile(
                name=Path(output_path).name,
                url=url,
                type=FileType.OTHER
            ),
            success=False,
            error=str(last_error)
        )
    
    async def download_async(self, url: str, output_path: str) -> DownloadResult:
        """Asynchronous download for better performance."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        result = DownloadResult(
            file=CourseFile(
                name=output_file.name,
                url=url,
                type=FileType.OTHER
            ),
            success=False
        )
        
        try:
            # Use aiohttp or async requests would be better here
            # For now, using sync in async context
            loop = asyncio.get_event_loop()
            sync_result = await loop.run_in_executor(
                None,
                self.download_file,
                url,
                output_path,
                True,
                False
            )
            return sync_result
        except Exception as e:
            result.error = str(e)
            return result
    
    async def download_batch_async(self, urls: List[str], output_dir: str) -> List[DownloadResult]:
        """Download multiple files asynchronously."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        tasks = []
        for url in urls:
            filename = self._extract_filename(url)
            output_file = output_path / filename
            task = self.download_async(url, str(output_file))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        return results
    
    def _extract_filename(self, url: str) -> str:
        """Extract filename from URL."""
        parsed = urlparse(url)
        path = unquote(parsed.path)
        
        if '/' in path:
            filename = path.split('/')[-1]
        else:
            filename = path
        
        # Ensure filename has an extension
        if '.' not in filename:
            # Try to guess extension from URL
            if 'pdf' in url.lower():
                filename += '.pdf'
            elif 'mp4' in url.lower() or 'video' in url.lower():
                filename += '.mp4'
            else:
                filename += '.bin'
        
        # Sanitize filename
        invalid_chars = '<>:"|?*\\/\0'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        return filename or f"download_{hash(url) % 10000}"
    
    def _verify_checksum(self, file_path: Path, expected_checksum: str) -> bool:
        """Verify file checksum."""
        # Simple MD5 check (could be extended for other algorithms)
        md5 = hashlib.md5()
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(self.chunk_size), b''):
                md5.update(chunk)
        
        calculated = md5.hexdigest()
        
        # Handle different checksum formats
        expected = expected_checksum.strip('"').lower()
        
        return calculated == expected
    
    def check_duplicate(self, url: str, output_dir: str) -> Optional[Path]:
        """Check if file already exists based on URL."""
        filename = self._extract_filename(url)
        output_path = Path(output_dir) / filename
        
        if output_path.exists():
            return output_path
        
        return None
    
    def get_download_stats(self, results: List[DownloadResult]) -> Dict[str, Any]:
        """Get statistics from download results."""
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_bytes = sum(r.bytes_downloaded or 0 for r in results)
        total_time = sum(r.download_time or 0 for r in results)
        
        return {
            'total': len(results),
            'successful': successful,
            'failed': failed,
            'total_bytes': total_bytes,
            'total_time': total_time,
            'average_speed': total_bytes / total_time if total_time > 0 else 0,
            'errors': [r.error for r in results if r.error]
        }