"""Data models for hw-scraper."""

from enum import Enum
from typing import Optional, List, Dict, Any
from pathlib import Path
from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime


class InputFormat(str, Enum):
    """Supported input file formats."""
    JSON = "json"
    XML = "xml"
    CSV = "csv"
    TXT = "txt"


class OutputFormat(str, Enum):
    """Supported output formats."""
    JSON = "json"
    CSV = "csv"
    TABLE = "table"


class FileType(str, Enum):
    """Types of course files."""
    LECTURE_VIDEO = "lecture_video"
    LECTURE_SLIDE = "lecture_slide"
    ASSIGNMENT = "assignment"
    RESOURCE = "resource"
    READING = "reading"
    SYLLABUS = "syllabus"
    OTHER = "other"


class AuthMethod(str, Enum):
    """Authentication methods."""
    ENV = "env"
    KEYRING = "keyring"
    COOKIES = "cookies"
    PROMPT = "prompt"


class BrowserProfile(str, Enum):
    """Browser profiles for impersonation."""
    CHROME = "chrome120"
    FIREFOX = "firefox120"
    SAFARI = "safari17_0"
    EDGE = "edge120"


class Course(BaseModel):
    """Course information model."""
    id: str
    name: str
    url: HttpUrl
    instructor: Optional[str] = None
    semester: Optional[str] = None
    description: Optional[str] = None
    last_updated: Optional[datetime] = None


class CourseFile(BaseModel):
    """Course file model."""
    name: str
    url: HttpUrl
    type: FileType
    size: Optional[int] = None
    course_id: Optional[str] = None
    course_name: Optional[str] = None
    description: Optional[str] = None
    date: Optional[datetime] = None
    local_path: Optional[Path] = None


class DownloadResult(BaseModel):
    """Result of a file download."""
    file: CourseFile
    success: bool
    local_path: Optional[Path] = None
    error: Optional[str] = None
    download_time: Optional[float] = None
    bytes_downloaded: Optional[int] = None


class ScrapeResult(BaseModel):
    """Result of scraping a course."""
    course_name: str
    course_url: str
    files_found: int
    files_downloaded: int
    files_failed: int
    total_size: Optional[int] = None
    duration: float
    errors: List[str] = Field(default_factory=list)
    files: List[CourseFile] = Field(default_factory=list)
    
    @property
    def files_count(self) -> int:
        """Get total count of downloaded files."""
        return self.files_downloaded


class Credentials(BaseModel):
    """User credentials model."""
    username: Optional[str] = None
    password: Optional[str] = None
    session_token: Optional[str] = None
    cookies: Dict[str, str] = Field(default_factory=dict)


class ScraperConfig(BaseModel):
    """Configuration for the scraper."""
    base_url: Optional[HttpUrl] = None
    download_path: Path = Path("./downloads")
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: int = 30
    rate_limit: float = 0.5  # seconds between requests
    user_agents: List[str] = Field(default_factory=lambda: [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
    ])
    browser_profile: BrowserProfile = BrowserProfile.CHROME
    parallel_downloads: int = 3
    chunk_size: int = 8192
    verify_ssl: bool = True
    follow_redirects: bool = True
    
    class Config:
        use_enum_values = True


class OrganizationScheme(BaseModel):
    """File organization scheme."""
    by_course: bool = True
    by_type: bool = True
    flatten: bool = False
    
    # Directory names
    lectures_dir: str = "lectures"
    assignments_dir: str = "assignments"
    resources_dir: str = "resources"
    videos_dir: str = "videos"
    slides_dir: str = "slides"
    
    # Filename patterns
    sanitize_names: bool = True
    preserve_dates: bool = True
    add_course_prefix: bool = False


class WorkerType(str, Enum):
    """Types of workers for concurrent processing."""
    THREAD = "thread"
    PROCESS = "process"
    ASYNC = "async"


class WorkerConfig(BaseModel):
    """Configuration for worker pool."""
    max_workers: int = 3
    worker_type: WorkerType = WorkerType.THREAD
    connection_pool_size: int = 10
    queue_size: int = 100
    enable_checkpointing: bool = True
    checkpoint_interval: int = 60  # seconds
    health_check_interval: int = 30  # seconds
    max_retries_per_worker: int = 3
    worker_timeout: int = 300  # seconds


class BatchTask(BaseModel):
    """Task for batch processing."""
    task_id: str
    url: HttpUrl
    course_name: Optional[str] = None
    priority: int = 0
    retry_count: int = 0
    status: str = "pending"  # pending, processing, completed, failed
    error: Optional[str] = None
    worker_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class BatchResult(BaseModel):
    """Result of batch processing."""
    batch_id: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    in_progress_tasks: int
    total_files_downloaded: int
    total_bytes_downloaded: int
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    tasks: List[BatchTask] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_tasks == 0:
            return 0.0
        return self.completed_tasks / self.total_tasks


class WorkerStatus(BaseModel):
    """Status of a worker."""
    worker_id: str
    worker_type: WorkerType
    status: str  # idle, busy, error, stopped
    current_task: Optional[BatchTask] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    bytes_downloaded: int = 0
    start_time: datetime
    last_heartbeat: datetime
    error_count: int = 0
    memory_usage: Optional[int] = None  # bytes
    cpu_usage: Optional[float] = None  # percentage


class WorkerPoolStatus(BaseModel):
    """Status of the entire worker pool."""
    pool_id: str
    total_workers: int
    active_workers: int
    idle_workers: int
    error_workers: int
    tasks_in_queue: int
    tasks_completed: int
    tasks_failed: int
    workers: List[WorkerStatus] = Field(default_factory=list)
    created_at: datetime
    
    @property
    def utilization(self) -> float:
        """Calculate worker pool utilization."""
        if self.total_workers == 0:
            return 0.0
        return self.active_workers / self.total_workers