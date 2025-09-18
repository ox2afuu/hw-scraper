"""Concurrency utilities for thread-safe and async-safe operations."""

import asyncio
import threading
import time
import hashlib
import random
from typing import Dict, Any, Optional, Callable, TypeVar, Generic
from collections import defaultdict
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ThreadSafeDict(Generic[T]):
    """Thread-safe dictionary implementation."""
    
    def __init__(self):
        self._dict: Dict[str, T] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """Thread-safe get."""
        with self._lock:
            return self._dict.get(key, default)
    
    def set(self, key: str, value: T) -> None:
        """Thread-safe set."""
        with self._lock:
            self._dict[key] = value
    
    def pop(self, key: str, default: Optional[T] = None) -> Optional[T]:
        """Thread-safe pop."""
        with self._lock:
            return self._dict.pop(key, default)
    
    def items(self) -> list:
        """Thread-safe items."""
        with self._lock:
            return list(self._dict.items())
    
    def clear(self) -> None:
        """Thread-safe clear."""
        with self._lock:
            self._dict.clear()
    
    def update(self, other: Dict[str, T]) -> None:
        """Thread-safe update."""
        with self._lock:
            self._dict.update(other)


class AsyncRateLimiter:
    """Async-safe rate limiter with per-domain support."""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self._last_call: Dict[str, float] = {}
        self._lock = asyncio.Lock()
    
    async def acquire(self, domain: Optional[str] = None) -> None:
        """Acquire rate limit slot."""
        async with self._lock:
            key = domain or 'default'
            current = time.time()
            last_call = self._last_call.get(key, 0)
            elapsed = current - last_call
            
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            
            self._last_call[key] = time.time()
    
    @asynccontextmanager
    async def limit(self, domain: Optional[str] = None):
        """Context manager for rate limiting."""
        await self.acquire(domain)
        yield


class ThreadSafeRateLimiter:
    """Thread-safe rate limiter."""
    
    def __init__(self, calls_per_second: float = 1.0):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self._last_call: Dict[str, float] = {}
        self._lock = threading.Lock()
    
    def acquire(self, domain: Optional[str] = None) -> None:
        """Acquire rate limit slot."""
        with self._lock:
            key = domain or 'default'
            current = time.time()
            last_call = self._last_call.get(key, 0)
            elapsed = current - last_call
            
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            
            self._last_call[key] = current
    
    @contextmanager
    def limit(self, domain: Optional[str] = None):
        """Context manager for rate limiting."""
        self.acquire(domain)
        yield


class AsyncSemaphorePool:
    """Pool of semaphores for domain-based concurrency limiting."""
    
    def __init__(self, default_limit: int = 5):
        self.default_limit = default_limit
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()
    
    async def get_semaphore(self, domain: str, limit: Optional[int] = None) -> asyncio.Semaphore:
        """Get or create semaphore for domain."""
        async with self._lock:
            if domain not in self._semaphores:
                sem_limit = limit or self.default_limit
                self._semaphores[domain] = asyncio.Semaphore(sem_limit)
            return self._semaphores[domain]
    
    @asynccontextmanager
    async def acquire(self, domain: str, limit: Optional[int] = None):
        """Acquire semaphore for domain."""
        sem = await self.get_semaphore(domain, limit)
        async with sem:
            yield


@dataclass
class CircuitBreaker:
    """Circuit breaker for handling failing services."""
    
    failure_threshold: int = 5
    timeout: float = 60.0
    half_open_max: int = 1
    
    _failures: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _last_failure: Dict[str, float] = field(default_factory=dict)
    _state: Dict[str, str] = field(default_factory=lambda: defaultdict(lambda: 'closed'))
    _half_open_count: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    
    def is_open(self, service: str) -> bool:
        """Check if circuit is open for service."""
        with self._lock:
            state = self._state[service]
            
            if state == 'open':
                # Check if timeout has passed
                if time.time() - self._last_failure.get(service, 0) > self.timeout:
                    self._state[service] = 'half_open'
                    self._half_open_count[service] = 0
                    return False
                return True
            
            return False
    
    def record_success(self, service: str) -> None:
        """Record successful call."""
        with self._lock:
            if self._state[service] == 'half_open':
                self._half_open_count[service] += 1
                if self._half_open_count[service] >= self.half_open_max:
                    self._state[service] = 'closed'
                    self._failures[service] = 0
    
    def record_failure(self, service: str) -> None:
        """Record failed call."""
        with self._lock:
            self._failures[service] += 1
            self._last_failure[service] = time.time()
            
            if self._failures[service] >= self.failure_threshold:
                self._state[service] = 'open'
    
    def get_state(self, service: str) -> str:
        """Get current state of circuit."""
        with self._lock:
            return self._state[service]


class AsyncCircuitBreaker:
    """Async version of circuit breaker."""
    
    def __init__(self, failure_threshold: int = 5, timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self._failures: Dict[str, int] = defaultdict(int)
        self._last_failure: Dict[str, float] = {}
        self._state: Dict[str, str] = defaultdict(lambda: 'closed')
        self._lock = asyncio.Lock()
    
    async def is_open(self, service: str) -> bool:
        """Check if circuit is open for service."""
        async with self._lock:
            state = self._state[service]
            
            if state == 'open':
                if time.time() - self._last_failure.get(service, 0) > self.timeout:
                    self._state[service] = 'half_open'
                    return False
                return True
            
            return False
    
    async def record_success(self, service: str) -> None:
        """Record successful call."""
        async with self._lock:
            if self._state[service] == 'half_open':
                self._state[service] = 'closed'
                self._failures[service] = 0
    
    async def record_failure(self, service: str) -> None:
        """Record failed call."""
        async with self._lock:
            self._failures[service] += 1
            self._last_failure[service] = time.time()
            
            if self._failures[service] >= self.failure_threshold:
                self._state[service] = 'open'


class ExponentialBackoff:
    """Exponential backoff with jitter."""
    
    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0, jitter: bool = True):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
    
    def get_delay(self, attempt: int) -> float:
        """Get delay for attempt number."""
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        
        if self.jitter:
            # Add random jitter (0.5 to 1.5 times the delay)
            delay *= (0.5 + random.random())
        
        return delay
    
    async def wait(self, attempt: int) -> None:
        """Async wait with backoff."""
        delay = self.get_delay(attempt)
        await asyncio.sleep(delay)
    
    def wait_sync(self, attempt: int) -> None:
        """Sync wait with backoff."""
        delay = self.get_delay(attempt)
        time.sleep(delay)


class TaskQueue:
    """Thread-safe task queue with priority support."""
    
    def __init__(self, maxsize: int = 0):
        self._queue: list = []
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self.maxsize = maxsize
    
    def put(self, item: Any, priority: int = 0, timeout: Optional[float] = None) -> None:
        """Put item in queue with priority."""
        with self._not_full:
            if self.maxsize > 0:
                while len(self._queue) >= self.maxsize:
                    if not self._not_full.wait(timeout):
                        raise TimeoutError("Queue is full")
            
            # Insert based on priority
            inserted = False
            for i, (p, _) in enumerate(self._queue):
                if priority > p:
                    self._queue.insert(i, (priority, item))
                    inserted = True
                    break
            
            if not inserted:
                self._queue.append((priority, item))
            
            self._not_empty.notify()
    
    def get(self, timeout: Optional[float] = None) -> Any:
        """Get item from queue."""
        with self._not_empty:
            while not self._queue:
                if not self._not_empty.wait(timeout):
                    raise TimeoutError("Queue is empty")
            
            priority, item = self._queue.pop(0)
            self._not_full.notify()
            return item
    
    def qsize(self) -> int:
        """Get queue size."""
        with self._lock:
            return len(self._queue)
    
    def empty(self) -> bool:
        """Check if queue is empty."""
        with self._lock:
            return len(self._queue) == 0


class AsyncTaskQueue:
    """Async task queue with priority support."""
    
    def __init__(self, maxsize: int = 0):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize)
        self._counter = 0
        self._lock = asyncio.Lock()
    
    async def put(self, item: Any, priority: int = 0) -> None:
        """Put item in queue with priority."""
        async with self._lock:
            # Use negative priority for max-heap behavior
            # Add counter to ensure FIFO for same priority
            self._counter += 1
            await self._queue.put((-priority, self._counter, item))
    
    async def get(self) -> Any:
        """Get item from queue."""
        priority, counter, item = await self._queue.get()
        return item
    
    def qsize(self) -> int:
        """Get queue size."""
        return self._queue.qsize()
    
    def empty(self) -> bool:
        """Check if queue is empty."""
        return self._queue.empty()


def generate_worker_id(prefix: str = "worker") -> str:
    """Generate unique worker ID."""
    timestamp = datetime.now().isoformat()
    hash_val = hashlib.md5(f"{prefix}_{timestamp}_{random.random()}".encode()).hexdigest()
    return f"{prefix}_{hash_val[:8]}"


def chunk_list(lst: list, chunk_size: int) -> list:
    """Split list into chunks."""
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


async def run_with_timeout(coro, timeout: float):
    """Run coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Coroutine timed out after {timeout} seconds")
        return None


def safe_execute(func: Callable, *args, **kwargs) -> tuple[bool, Any]:
    """Safely execute function and return success status and result/error."""
    try:
        result = func(*args, **kwargs)
        return True, result
    except Exception as e:
        logger.error(f"Error executing function: {e}")
        return False, e


async def safe_async_execute(coro) -> tuple[bool, Any]:
    """Safely execute async function and return success status and result/error."""
    try:
        result = await coro
        return True, result
    except Exception as e:
        logger.error(f"Error executing async function: {e}")
        return False, e