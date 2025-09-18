"""Thread-safe and async-safe session management."""

import threading
import asyncio
from typing import Dict, Optional, Any, Union
from contextlib import asynccontextmanager, contextmanager
import logging
from urllib.parse import urlparse
import time

import httpx
import aiohttp
from curl_cffi import requests
from curl_cffi.requests import Session as CurlSession

from hw_scraper.config import Config
from hw_scraper.auth import AuthManager
from hw_scraper.concurrency import ThreadSafeDict, AsyncRateLimiter, ThreadSafeRateLimiter
from hw_scraper.models import BrowserProfile

logger = logging.getLogger(__name__)


class ThreadLocalSessionManager:
    """Thread-local session storage for thread-safe operations."""
    
    def __init__(self, config: Config, auth_manager: AuthManager):
        self.config = config
        self.auth_manager = auth_manager
        self._local = threading.local()
        self._lock = threading.Lock()
        self._sessions: ThreadSafeDict[CurlSession] = ThreadSafeDict()
        self._rate_limiter = ThreadSafeRateLimiter(config.scraper_config.rate_limit)
    
    def get_session(self, domain: Optional[str] = None) -> CurlSession:
        """Get or create thread-local session."""
        thread_id = threading.get_ident()
        session_key = f"{thread_id}_{domain or 'default'}"
        
        session = self._sessions.get(session_key)
        if session is None:
            session = self._create_session(domain)
            self._sessions.set(session_key, session)
        
        return session
    
    def _create_session(self, domain: Optional[str] = None) -> CurlSession:
        """Create new curl-cffi session."""
        impersonate = self.config.scraper_config.browser_profile
        
        session = requests.Session(
            impersonate=impersonate,
            timeout=self.config.scraper_config.timeout,
            verify=self.config.scraper_config.verify_ssl
        )
        
        # Set cookies if available
        if self.auth_manager.get_cookies():
            for name, value in self.auth_manager.get_cookies().items():
                session.cookies.set(name, value, domain=domain)
        
        return session
    
    @contextmanager
    def session_context(self, url: str):
        """Context manager for session with rate limiting."""
        domain = urlparse(url).netloc
        
        # Apply rate limiting
        self._rate_limiter.acquire(domain)
        
        session = self.get_session(domain)
        try:
            yield session
        finally:
            # Update cookies after request
            if session.cookies:
                cookies = {k: v for k, v in session.cookies.items()}
                self.auth_manager.update_cookies(cookies)
    
    def close_all(self):
        """Close all sessions."""
        for _, session in self._sessions.items():
            try:
                session.close()
            except Exception as e:
                logger.error(f"Error closing session: {e}")
        self._sessions.clear()


class AsyncSessionManager:
    """Async session manager with connection pooling."""
    
    def __init__(self, config: Config, auth_manager: AuthManager):
        self.config = config
        self.auth_manager = auth_manager
        self._sessions: Dict[str, Union[httpx.AsyncClient, aiohttp.ClientSession]] = {}
        self._lock = asyncio.Lock()
        self._rate_limiter = AsyncRateLimiter(config.scraper_config.rate_limit)
        self._use_httpx = True  # Toggle between httpx and aiohttp
    
    async def get_httpx_client(self, domain: Optional[str] = None) -> httpx.AsyncClient:
        """Get or create httpx async client."""
        async with self._lock:
            key = domain or 'default'
            
            if key not in self._sessions:
                limits = httpx.Limits(
                    max_connections=self.config.scraper_config.connection_pool_size,
                    max_keepalive_connections=5
                )
                
                headers = {}
                if self.config.scraper_config.user_agents:
                    import random
                    headers['User-Agent'] = random.choice(self.config.scraper_config.user_agents)
                
                client = httpx.AsyncClient(
                    limits=limits,
                    timeout=self.config.scraper_config.timeout,
                    verify=self.config.scraper_config.verify_ssl,
                    follow_redirects=self.config.scraper_config.follow_redirects,
                    headers=headers,
                    cookies=self.auth_manager.get_cookies()
                )
                
                self._sessions[key] = client
            
            return self._sessions[key]
    
    async def get_aiohttp_session(self, domain: Optional[str] = None) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        async with self._lock:
            key = f"aiohttp_{domain or 'default'}"
            
            if key not in self._sessions:
                connector = aiohttp.TCPConnector(
                    limit=self.config.scraper_config.connection_pool_size,
                    limit_per_host=10,
                    ttl_dns_cache=300
                )
                
                headers = {}
                if self.config.scraper_config.user_agents:
                    import random
                    headers['User-Agent'] = random.choice(self.config.scraper_config.user_agents)
                
                timeout = aiohttp.ClientTimeout(total=self.config.scraper_config.timeout)
                
                session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                    headers=headers,
                    cookies=self.auth_manager.get_cookies()
                )
                
                self._sessions[key] = session
            
            return self._sessions[key]
    
    @asynccontextmanager
    async def httpx_context(self, url: str):
        """Context manager for httpx client with rate limiting."""
        domain = urlparse(url).netloc
        
        # Apply rate limiting
        await self._rate_limiter.acquire(domain)
        
        client = await self.get_httpx_client(domain)
        try:
            yield client
        finally:
            # Update cookies after request
            pass  # httpx handles cookies automatically
    
    @asynccontextmanager
    async def aiohttp_context(self, url: str):
        """Context manager for aiohttp session with rate limiting."""
        domain = urlparse(url).netloc
        
        # Apply rate limiting
        await self._rate_limiter.acquire(domain)
        
        session = await self.get_aiohttp_session(domain)
        try:
            yield session
        finally:
            # Update cookies if needed
            pass
    
    async def close_all(self):
        """Close all sessions."""
        for key, session in self._sessions.items():
            try:
                if isinstance(session, httpx.AsyncClient):
                    await session.aclose()
                elif isinstance(session, aiohttp.ClientSession):
                    await session.close()
            except Exception as e:
                logger.error(f"Error closing session {key}: {e}")
        self._sessions.clear()


class ConnectionPool:
    """Connection pool for managing multiple sessions."""
    
    def __init__(self, config: Config, pool_size: int = 10):
        self.config = config
        self.pool_size = pool_size
        self._available: asyncio.Queue = asyncio.Queue(maxsize=pool_size)
        self._in_use: set = set()
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self):
        """Initialize connection pool."""
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            for _ in range(self.pool_size):
                client = await self._create_client()
                await self._available.put(client)
            
            self._initialized = True
    
    async def _create_client(self) -> httpx.AsyncClient:
        """Create new HTTP client."""
        return httpx.AsyncClient(
            timeout=self.config.scraper_config.timeout,
            verify=self.config.scraper_config.verify_ssl,
            follow_redirects=self.config.scraper_config.follow_redirects
        )
    
    async def acquire(self) -> httpx.AsyncClient:
        """Acquire client from pool."""
        if not self._initialized:
            await self.initialize()
        
        client = await self._available.get()
        self._in_use.add(id(client))
        return client
    
    async def release(self, client: httpx.AsyncClient):
        """Release client back to pool."""
        if id(client) in self._in_use:
            self._in_use.remove(id(client))
            await self._available.put(client)
    
    @asynccontextmanager
    async def client(self):
        """Context manager for client."""
        client = await self.acquire()
        try:
            yield client
        finally:
            await self.release(client)
    
    async def close(self):
        """Close all clients in pool."""
        async with self._lock:
            # Close available clients
            while not self._available.empty():
                try:
                    client = await self._available.get()
                    await client.aclose()
                except Exception as e:
                    logger.error(f"Error closing client: {e}")
            
            self._initialized = False


class SessionMetrics:
    """Track session metrics for monitoring."""
    
    def __init__(self):
        self._requests: Dict[str, int] = {}
        self._errors: Dict[str, int] = {}
        self._bytes: Dict[str, int] = {}
        self._latencies: Dict[str, list] = {}
        self._lock = threading.Lock()
    
    def record_request(self, domain: str, bytes_transferred: int = 0, latency: float = 0):
        """Record successful request."""
        with self._lock:
            self._requests[domain] = self._requests.get(domain, 0) + 1
            self._bytes[domain] = self._bytes.get(domain, 0) + bytes_transferred
            
            if domain not in self._latencies:
                self._latencies[domain] = []
            self._latencies[domain].append(latency)
            
            # Keep only last 100 latencies
            if len(self._latencies[domain]) > 100:
                self._latencies[domain] = self._latencies[domain][-100:]
    
    def record_error(self, domain: str):
        """Record failed request."""
        with self._lock:
            self._errors[domain] = self._errors.get(domain, 0) + 1
    
    def get_stats(self, domain: Optional[str] = None) -> Dict[str, Any]:
        """Get statistics for domain or all domains."""
        with self._lock:
            if domain:
                latencies = self._latencies.get(domain, [])
                avg_latency = sum(latencies) / len(latencies) if latencies else 0
                
                return {
                    'requests': self._requests.get(domain, 0),
                    'errors': self._errors.get(domain, 0),
                    'bytes': self._bytes.get(domain, 0),
                    'avg_latency': avg_latency
                }
            else:
                total_requests = sum(self._requests.values())
                total_errors = sum(self._errors.values())
                total_bytes = sum(self._bytes.values())
                
                all_latencies = []
                for domain_latencies in self._latencies.values():
                    all_latencies.extend(domain_latencies)
                
                avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
                
                return {
                    'total_requests': total_requests,
                    'total_errors': total_errors,
                    'total_bytes': total_bytes,
                    'avg_latency': avg_latency,
                    'domains': len(self._requests)
                }
    
    def reset(self):
        """Reset all metrics."""
        with self._lock:
            self._requests.clear()
            self._errors.clear()
            self._bytes.clear()
            self._latencies.clear()