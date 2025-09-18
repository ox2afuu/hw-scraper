"""Batch processor for handling multiple course downloads efficiently."""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from datetime import datetime
from rich.progress import Progress, TaskID
from rich.console import Console
from rich.table import Table

from hw_scraper.config import Config
from hw_scraper.auth import AuthManager
from hw_scraper.async_scraper import AsyncScraper
from hw_scraper.worker_pool import WorkerPool
from hw_scraper.models import (
    BatchTask, BatchResult, WorkerConfig, WorkerType,
    ScrapeResult, CourseFile
)
from hw_scraper.concurrency import (
    AsyncTaskQueue, chunk_list, generate_worker_id
)
from hw_scraper.utils import format_bytes, format_duration, save_results_to_json

logger = logging.getLogger(__name__)
console = Console()


class BatchProcessor:
    """High-level batch processor for course downloads."""
    
    def __init__(self, config: Config, auth_manager: AuthManager,
                 worker_config: Optional[WorkerConfig] = None):
        self.config = config
        self.auth_manager = auth_manager
        self.worker_config = worker_config or WorkerConfig()
        
        # Components
        self.worker_pool: Optional[WorkerPool] = None
        self.async_scraper: Optional[AsyncScraper] = None
        
        # State
        self._checkpoint_file: Optional[Path] = None
        self._checkpoint_data: Dict[str, Any] = {}
        self._progress: Optional[Progress] = None
        self._progress_tasks: Dict[str, TaskID] = {}
    
    async def __aenter__(self):
        """Async context manager entry."""
        if self.worker_config.worker_type == WorkerType.ASYNC:
            self.async_scraper = AsyncScraper(self.config, self.auth_manager)
            await self.async_scraper.connection_pool.initialize()
        else:
            self.worker_pool = WorkerPool(
                self.config,
                self.auth_manager,
                self.worker_config
            )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def process_courses(self, urls: List[str], output_dir: str = './downloads',
                            organize: bool = True, checkpoint: bool = True,
                            progress: bool = True) -> BatchResult:
        """Process multiple course URLs with advanced features."""
        batch_id = generate_worker_id("batch")
        start_time = datetime.now()
        
        # Initialize result
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
        
        # Set up checkpointing
        if checkpoint:
            self._setup_checkpoint(batch_id, output_dir)
            urls = self._filter_completed_urls(urls)
        
        # Set up progress display
        if progress:
            self._setup_progress(len(urls))
        
        # Process based on worker type
        if self.worker_config.worker_type == WorkerType.ASYNC:
            await self._process_async(urls, output_dir, organize, result)
        else:
            await self._process_with_pool(urls, output_dir, organize, result)
        
        # Finalize
        result.end_time = datetime.now()
        result.duration = (result.end_time - start_time).total_seconds()
        
        # Save final results
        if checkpoint:
            self._save_final_results(result, output_dir)
        
        # Clean up progress
        if self._progress:
            self._progress.stop()
        
        return result
    
    async def _process_async(self, urls: List[str], output_dir: str,
                           organize: bool, result: BatchResult):
        """Process using async scraper directly."""
        # Create tasks
        tasks = []
        for i, url in enumerate(urls):
            batch_task = BatchTask(
                task_id=f"task_{i}",
                url=url,
                created_at=datetime.now()
            )
            result.tasks.append(batch_task)
            
            # Create coroutine
            task_coro = self._process_single_course(
                batch_task, output_dir, organize
            )
            tasks.append(task_coro)
        
        # Process with concurrency limit
        semaphore = asyncio.Semaphore(self.worker_config.max_workers)
        
        async def process_with_limit(task_coro, batch_task):
            async with semaphore:
                return await self._process_and_update(
                    task_coro, batch_task, result
                )
        
        # Execute all tasks
        process_tasks = [
            process_with_limit(task_coro, batch_task)
            for task_coro, batch_task in zip(tasks, result.tasks)
        ]
        
        await asyncio.gather(*process_tasks, return_exceptions=True)
    
    async def _process_with_pool(self, urls: List[str], output_dir: str,
                                organize: bool, result: BatchResult):
        """Process using worker pool."""
        # Start worker pool
        if self.worker_config.worker_type == WorkerType.THREAD:
            self.worker_pool.start_sync()
            
            # Submit tasks
            for i, url in enumerate(urls):
                task = BatchTask(
                    task_id=f"task_{i}",
                    url=url,
                    created_at=datetime.now()
                )
                result.tasks.append(task)
                self.worker_pool.submit_task_sync(task)
            
            # Collect results
            await self._collect_pool_results(result, len(urls))
        else:
            # Async pool processing
            pool_result = await self.worker_pool.process_urls_async(urls)
            
            # Copy results
            result.completed_tasks = pool_result.completed_tasks
            result.failed_tasks = pool_result.failed_tasks
            result.total_files_downloaded = pool_result.total_files_downloaded
            result.tasks = pool_result.tasks
    
    async def _process_single_course(self, task: BatchTask, output_dir: str,
                                    organize: bool) -> ScrapeResult:
        """Process a single course URL."""
        task.status = "processing"
        task.started_at = datetime.now()
        
        try:
            # Scrape course
            course_output = Path(output_dir) / task.task_id
            
            result = await self.async_scraper.scrape_course(
                str(task.url),
                str(course_output),
                organize
            )
            
            task.status = "completed"
            task.completed_at = datetime.now()
            
            # Save checkpoint
            if self._checkpoint_file:
                self._save_checkpoint(task)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to process {task.url}: {e}")
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now()
            raise
    
    async def _process_and_update(self, task_coro, batch_task: BatchTask,
                                 result: BatchResult) -> Optional[ScrapeResult]:
        """Process task and update result."""
        try:
            # Update progress
            if self._progress and batch_task.task_id in self._progress_tasks:
                self._progress.update(
                    self._progress_tasks[batch_task.task_id],
                    description=f"Processing {batch_task.url[:50]}..."
                )
            
            result.in_progress_tasks += 1
            
            # Process task
            scrape_result = await task_coro
            
            # Update results
            result.completed_tasks += 1
            result.total_files_downloaded += scrape_result.files_downloaded
            
            # Update progress
            if self._progress and batch_task.task_id in self._progress_tasks:
                self._progress.update(
                    self._progress_tasks[batch_task.task_id],
                    completed=True
                )
            
            return scrape_result
            
        except Exception as e:
            result.failed_tasks += 1
            result.errors.append(str(e))
            
            # Update progress
            if self._progress and batch_task.task_id in self._progress_tasks:
                self._progress.update(
                    self._progress_tasks[batch_task.task_id],
                    description=f"[red]Failed: {batch_task.url[:40]}..."
                )
            
            return None
        finally:
            result.in_progress_tasks -= 1
    
    async def _collect_pool_results(self, result: BatchResult, total: int):
        """Collect results from worker pool."""
        completed = 0
        
        while completed < total:
            try:
                # Get result from queue
                task, scrape_result = self.worker_pool.result_queue.get(timeout=5.0)
                
                if scrape_result:
                    result.completed_tasks += 1
                    result.total_files_downloaded += scrape_result.files_downloaded
                else:
                    result.failed_tasks += 1
                
                completed += 1
                
                # Update progress
                if self._progress:
                    self._update_main_progress(completed, total)
                
            except TimeoutError:
                logger.warning("Timeout waiting for worker results")
                continue
    
    def _setup_checkpoint(self, batch_id: str, output_dir: str):
        """Set up checkpointing."""
        checkpoint_dir = Path(output_dir) / ".checkpoints"
        checkpoint_dir.mkdir(exist_ok=True)
        
        self._checkpoint_file = checkpoint_dir / f"{batch_id}.json"
        
        # Load existing checkpoint if exists
        if self._checkpoint_file.exists():
            with open(self._checkpoint_file, 'r') as f:
                self._checkpoint_data = json.load(f)
        else:
            self._checkpoint_data = {
                'batch_id': batch_id,
                'started_at': datetime.now().isoformat(),
                'completed_tasks': []
            }
    
    def _filter_completed_urls(self, urls: List[str]) -> List[str]:
        """Filter out already completed URLs."""
        completed = set(self._checkpoint_data.get('completed_tasks', []))
        return [url for url in urls if url not in completed]
    
    def _save_checkpoint(self, task: BatchTask):
        """Save checkpoint after task completion."""
        if task.status == "completed":
            self._checkpoint_data['completed_tasks'].append(str(task.url))
            
            with open(self._checkpoint_file, 'w') as f:
                json.dump(self._checkpoint_data, f, indent=2)
    
    def _save_final_results(self, result: BatchResult, output_dir: str):
        """Save final results to file."""
        results_file = Path(output_dir) / f"{result.batch_id}_results.json"
        save_results_to_json([result.dict()], str(results_file))
        
        # Generate summary report
        self._generate_summary_report(result, output_dir)
    
    def _generate_summary_report(self, result: BatchResult, output_dir: str):
        """Generate markdown summary report."""
        report_file = Path(output_dir) / f"{result.batch_id}_report.md"
        
        report = [
            f"# Batch Processing Report\n\n",
            f"**Batch ID:** {result.batch_id}\n",
            f"**Start Time:** {result.start_time}\n",
            f"**End Time:** {result.end_time}\n",
            f"**Duration:** {format_duration(result.duration)}\n\n",
            f"## Summary\n\n",
            f"- Total Tasks: {result.total_tasks}\n",
            f"- Completed: {result.completed_tasks}\n",
            f"- Failed: {result.failed_tasks}\n",
            f"- Success Rate: {result.success_rate:.1%}\n",
            f"- Files Downloaded: {result.total_files_downloaded}\n",
            f"- Data Downloaded: {format_bytes(result.total_bytes_downloaded)}\n\n"
        ]
        
        # Add failed tasks if any
        if result.failed_tasks > 0:
            report.append("## Failed Tasks\n\n")
            for task in result.tasks:
                if task.status == "failed":
                    report.append(f"- {task.url}: {task.error}\n")
            report.append("\n")
        
        # Write report
        with open(report_file, 'w') as f:
            f.writelines(report)
    
    def _setup_progress(self, total: int):
        """Set up progress display."""
        from rich.progress import (
            Progress, SpinnerColumn, BarColumn,
            TextColumn, TimeRemainingColumn
        )
        
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        )
        
        self._progress.start()
        
        # Create main progress task
        self._main_task = self._progress.add_task(
            f"[green]Processing {total} courses...",
            total=total
        )
    
    def _update_main_progress(self, completed: int, total: int):
        """Update main progress bar."""
        if self._progress and hasattr(self, '_main_task'):
            self._progress.update(
                self._main_task,
                completed=completed,
                description=f"[green]Processed {completed}/{total} courses"
            )
    
    async def close(self):
        """Clean up resources."""
        if self.async_scraper:
            await self.async_scraper.close()
        
        if self.worker_pool:
            self.worker_pool.shutdown()
        
        if self._progress:
            self._progress.stop()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current statistics."""
        stats = {}
        
        if self.worker_pool:
            pool_status = self.worker_pool.get_status()
            stats['pool'] = {
                'active_workers': pool_status.active_workers,
                'idle_workers': pool_status.idle_workers,
                'tasks_in_queue': pool_status.tasks_in_queue,
                'utilization': pool_status.utilization
            }
        
        if self.async_scraper:
            metrics = asyncio.run(self.async_scraper.get_metrics())
            stats['scraper'] = metrics
        
        return stats


async def batch_scrape_courses(urls: List[str], config: Config,
                              auth_manager: AuthManager,
                              output_dir: str = './downloads') -> BatchResult:
    """Convenience function for batch scraping."""
    worker_config = WorkerConfig(
        max_workers=config.scraper_config.parallel_downloads,
        worker_type=WorkerType.ASYNC
    )
    
    async with BatchProcessor(config, auth_manager, worker_config) as processor:
        result = await processor.process_courses(urls, output_dir)
        return result