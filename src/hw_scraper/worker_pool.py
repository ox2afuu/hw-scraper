"""Worker pool for managing multiple crawler instances."""

import asyncio
import threading
import multiprocessing
import os
import time
import psutil
import logging
from typing import List, Optional, Dict, Any, Callable, Union
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future
from datetime import datetime
from pathlib import Path
import json
import pickle

from hw_scraper.config import Config
from hw_scraper.auth import AuthManager
from hw_scraper.async_scraper import AsyncScraper
from hw_scraper.scraper import Scraper
from hw_scraper.models import (
    WorkerType, WorkerConfig, WorkerStatus, WorkerPoolStatus,
    BatchTask, BatchResult, ScrapeResult
)
from hw_scraper.concurrency import (
    generate_worker_id, AsyncTaskQueue, TaskQueue,
    chunk_list, safe_execute, safe_async_execute
)

logger = logging.getLogger(__name__)


class Worker:
    """Base worker class."""
    
    def __init__(self, worker_id: str, config: Config, auth_manager: AuthManager):
        self.worker_id = worker_id
        self.config = config
        self.auth_manager = auth_manager
        self.status = WorkerStatus(
            worker_id=worker_id,
            worker_type=WorkerType.THREAD,
            status="idle",
            tasks_completed=0,
            tasks_failed=0,
            bytes_downloaded=0,
            start_time=datetime.now(),
            last_heartbeat=datetime.now()
        )
        self._stop_event = threading.Event()
    
    def update_heartbeat(self):
        """Update worker heartbeat."""
        self.status.last_heartbeat = datetime.now()
    
    def stop(self):
        """Signal worker to stop."""
        self._stop_event.set()
    
    def is_stopped(self) -> bool:
        """Check if worker should stop."""
        return self._stop_event.is_set()
    
    def update_metrics(self):
        """Update worker metrics."""
        try:
            process = psutil.Process()
            self.status.memory_usage = process.memory_info().rss
            self.status.cpu_usage = process.cpu_percent(interval=0.1)
        except Exception:
            pass


class AsyncWorker(Worker):
    """Async worker for processing tasks."""
    
    def __init__(self, worker_id: str, config: Config, auth_manager: AuthManager,
                 task_queue: AsyncTaskQueue, result_queue: asyncio.Queue):
        super().__init__(worker_id, config, auth_manager)
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.status.worker_type = WorkerType.ASYNC
        self.scraper: Optional[AsyncScraper] = None
    
    async def run(self):
        """Run async worker."""
        try:
            # Initialize scraper
            self.scraper = AsyncScraper(self.config, self.auth_manager)
            await self.scraper.connection_pool.initialize()
            
            while not self.is_stopped():
                try:
                    # Get task with timeout
                    task = await asyncio.wait_for(
                        self.task_queue.get(),
                        timeout=1.0
                    )
                    
                    # Process task
                    await self._process_task(task)
                    
                except asyncio.TimeoutError:
                    # No tasks, continue
                    self.update_heartbeat()
                    continue
                except Exception as e:
                    logger.error(f"Worker {self.worker_id} error: {e}")
                    self.status.error_count += 1
        
        finally:
            # Cleanup
            if self.scraper:
                await self.scraper.close()
    
    async def _process_task(self, task: BatchTask):
        """Process a single task."""
        self.status.status = "busy"
        self.status.current_task = task
        task.worker_id = self.worker_id
        task.status = "processing"
        task.started_at = datetime.now()
        
        try:
            # Scrape course
            result = await self.scraper.scrape_course(
                str(task.url),
                output_dir=f"./downloads/{task.task_id}"
            )
            
            # Update status
            task.status = "completed"
            task.completed_at = datetime.now()
            self.status.tasks_completed += 1
            self.status.bytes_downloaded += result.total_size or 0
            
            # Put result in queue
            await self.result_queue.put((task, result))
            
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now()
            self.status.tasks_failed += 1
            
            # Put error result in queue
            await self.result_queue.put((task, None))
        
        finally:
            self.status.status = "idle"
            self.status.current_task = None
            self.update_heartbeat()
            self.update_metrics()


class ThreadWorker(Worker):
    """Thread-based worker."""
    
    def __init__(self, worker_id: str, config: Config, auth_manager: AuthManager,
                 task_queue: TaskQueue, result_queue: TaskQueue):
        super().__init__(worker_id, config, auth_manager)
        self.task_queue = task_queue
        self.result_queue = result_queue
        self.status.worker_type = WorkerType.THREAD
        self.scraper = Scraper(config, auth_manager)
    
    def run(self):
        """Run thread worker."""
        while not self.is_stopped():
            try:
                # Get task with timeout
                task = self.task_queue.get(timeout=1.0)
                
                # Process task
                self._process_task(task)
                
            except TimeoutError:
                # No tasks, continue
                self.update_heartbeat()
                continue
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                self.status.error_count += 1
    
    def _process_task(self, task: BatchTask):
        """Process a single task."""
        self.status.status = "busy"
        self.status.current_task = task
        task.worker_id = self.worker_id
        task.status = "processing"
        task.started_at = datetime.now()
        
        try:
            # Scrape course
            result = self.scraper.scrape_course(
                str(task.url),
                output_dir=f"./downloads/{task.task_id}"
            )
            
            # Update status
            task.status = "completed"
            task.completed_at = datetime.now()
            self.status.tasks_completed += 1
            
            # Put result in queue
            self.result_queue.put((task, result))
            
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            task.status = "failed"
            task.error = str(e)
            task.completed_at = datetime.now()
            self.status.tasks_failed += 1
            
            # Put error result in queue
            self.result_queue.put((task, None))
        
        finally:
            self.status.status = "idle"
            self.status.current_task = None
            self.update_heartbeat()
            self.update_metrics()


def process_worker_task(task_data: bytes, config_data: bytes, auth_data: bytes) -> bytes:
    """Process task in separate process."""
    # Deserialize data
    task = pickle.loads(task_data)
    config = pickle.loads(config_data)
    auth_manager = pickle.loads(auth_data)
    
    # Create scraper and process
    scraper = Scraper(config, auth_manager)
    
    try:
        result = scraper.scrape_course(
            str(task.url),
            output_dir=f"./downloads/{task.task_id}"
        )
        task.status = "completed"
        return pickle.dumps((task, result))
    except Exception as e:
        task.status = "failed"
        task.error = str(e)
        return pickle.dumps((task, None))


class WorkerPool:
    """Pool of workers for concurrent processing."""
    
    def __init__(self, config: Config, auth_manager: AuthManager,
                 worker_config: Optional[WorkerConfig] = None):
        self.config = config
        self.auth_manager = auth_manager
        self.worker_config = worker_config or WorkerConfig()
        self.pool_id = generate_worker_id("pool")
        
        # Worker management
        self.workers: List[Union[AsyncWorker, ThreadWorker]] = []
        self.executor: Optional[Union[ThreadPoolExecutor, ProcessPoolExecutor]] = None
        
        # Task queues
        if self.worker_config.worker_type == WorkerType.ASYNC:
            self.task_queue = AsyncTaskQueue(maxsize=self.worker_config.queue_size)
            self.result_queue = asyncio.Queue()
        else:
            self.task_queue = TaskQueue(maxsize=self.worker_config.queue_size)
            self.result_queue = TaskQueue()
        
        # Status tracking
        self.status = WorkerPoolStatus(
            pool_id=self.pool_id,
            total_workers=self.worker_config.max_workers,
            active_workers=0,
            idle_workers=0,
            error_workers=0,
            tasks_in_queue=0,
            tasks_completed=0,
            tasks_failed=0,
            created_at=datetime.now()
        )
        
        # Control
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
    
    async def start_async(self):
        """Start async worker pool."""
        if self.worker_config.worker_type != WorkerType.ASYNC:
            raise ValueError("Worker type must be ASYNC for async start")
        
        # Create workers
        for i in range(self.worker_config.max_workers):
            worker_id = generate_worker_id(f"async_{i}")
            worker = AsyncWorker(
                worker_id,
                self.config,
                self.auth_manager,
                self.task_queue,
                self.result_queue
            )
            self.workers.append(worker)
            self.status.workers.append(worker.status)
        
        # Start workers
        tasks = [worker.run() for worker in self.workers]
        
        # Start monitor
        self._start_monitor()
        
        # Run workers
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def start_sync(self):
        """Start sync worker pool."""
        if self.worker_config.worker_type == WorkerType.THREAD:
            self.executor = ThreadPoolExecutor(max_workers=self.worker_config.max_workers)
            
            # Create and start thread workers
            for i in range(self.worker_config.max_workers):
                worker_id = generate_worker_id(f"thread_{i}")
                worker = ThreadWorker(
                    worker_id,
                    self.config,
                    self.auth_manager,
                    self.task_queue,
                    self.result_queue
                )
                self.workers.append(worker)
                self.status.workers.append(worker.status)
                
                # Submit worker to executor
                self.executor.submit(worker.run)
        
        elif self.worker_config.worker_type == WorkerType.PROCESS:
            self.executor = ProcessPoolExecutor(max_workers=self.worker_config.max_workers)
        
        # Start monitor
        self._start_monitor()
    
    def _start_monitor(self):
        """Start monitoring thread."""
        self._monitor_thread = threading.Thread(target=self._monitor_workers)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()
    
    def _monitor_workers(self):
        """Monitor worker health."""
        while not self._stop_event.is_set():
            try:
                # Update pool status
                self._update_pool_status()
                
                # Check worker health
                for worker in self.workers:
                    if isinstance(worker, (AsyncWorker, ThreadWorker)):
                        # Check heartbeat
                        time_since_heartbeat = (
                            datetime.now() - worker.status.last_heartbeat
                        ).total_seconds()
                        
                        if time_since_heartbeat > self.worker_config.health_check_interval * 2:
                            logger.warning(f"Worker {worker.worker_id} unresponsive")
                            worker.status.status = "error"
                
                # Sleep for health check interval
                time.sleep(self.worker_config.health_check_interval)
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
    
    def _update_pool_status(self):
        """Update pool status."""
        active = sum(1 for w in self.workers if w.status.status == "busy")
        idle = sum(1 for w in self.workers if w.status.status == "idle")
        error = sum(1 for w in self.workers if w.status.status == "error")
        
        self.status.active_workers = active
        self.status.idle_workers = idle
        self.status.error_workers = error
        self.status.tasks_in_queue = self.task_queue.qsize()
    
    async def submit_task_async(self, task: BatchTask):
        """Submit task to async queue."""
        await self.task_queue.put(task, priority=task.priority)
    
    def submit_task_sync(self, task: BatchTask):
        """Submit task to sync queue."""
        self.task_queue.put(task, priority=task.priority)
    
    async def process_urls_async(self, urls: List[str]) -> BatchResult:
        """Process URLs using async workers."""
        # Create batch result
        batch_result = BatchResult(
            batch_id=generate_worker_id("batch"),
            total_tasks=len(urls),
            completed_tasks=0,
            failed_tasks=0,
            in_progress_tasks=0,
            total_files_downloaded=0,
            total_bytes_downloaded=0,
            start_time=datetime.now()
        )
        
        # Submit tasks
        for i, url in enumerate(urls):
            task = BatchTask(
                task_id=f"task_{i}",
                url=url,
                created_at=datetime.now()
            )
            batch_result.tasks.append(task)
            await self.submit_task_async(task)
        
        # Collect results
        completed = 0
        while completed < len(urls):
            try:
                task, result = await asyncio.wait_for(
                    self.result_queue.get(),
                    timeout=self.worker_config.worker_timeout
                )
                
                if result:
                    batch_result.completed_tasks += 1
                    batch_result.total_files_downloaded += result.files_downloaded
                else:
                    batch_result.failed_tasks += 1
                
                completed += 1
                
            except asyncio.TimeoutError:
                logger.error("Timeout waiting for results")
                break
        
        # Finalize
        batch_result.end_time = datetime.now()
        batch_result.duration = (
            batch_result.end_time - batch_result.start_time
        ).total_seconds()
        
        return batch_result
    
    def shutdown(self):
        """Shutdown worker pool."""
        self._stop_event.set()
        
        # Stop all workers
        for worker in self.workers:
            worker.stop()
        
        # Shutdown executor
        if self.executor:
            self.executor.shutdown(wait=True)
        
        # Wait for monitor to stop
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
    
    def get_status(self) -> WorkerPoolStatus:
        """Get current pool status."""
        self._update_pool_status()
        return self.status