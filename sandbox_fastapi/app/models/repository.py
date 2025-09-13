"""
Repository model using SQLAlchemy 2.0 best practices with Alembic support.

Following SQLAlchemy 2.0 tutorial recommendations for proper model design.
"""

from datetime import datetime, UTC
from typing import Optional
from sqlalchemy import String, DateTime, Text, ForeignKey, create_engine, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, relationship

from app.models.enums import JobStatus, JobType, CompressionType, TaskStatus, TaskType, NotificationProvider

# SQLAlchemy 2.0 DeclarativeBase pattern with naming conventions for Alembic
from sqlalchemy import MetaData

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models following 2.0 best practices."""
    
    # Naming conventions for consistent constraint names (Alembic best practice)
    metadata = MetaData(naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s", 
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s"
    })


class Repository(Base):
    """
    Repository model following SQLAlchemy 2.0 patterns.
    
    Uses modern type annotations and proper constraints for Alembic migrations.
    """
    __tablename__ = "repositories"
    
    # Primary key with proper type annotation
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Required fields with constraints
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    path: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    
    # Encrypted passphrase storage (simplified for sandbox)
    encrypted_passphrase: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Timestamps with proper UTC handling
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(UTC),
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )
    
    def set_passphrase(self, passphrase: str):
        """Set passphrase with simple encryption (for sandbox)."""
        # Simplified encryption for sandbox - in production would use proper cipher
        import base64
        encoded = base64.b64encode(passphrase.encode()).decode()
        self.encrypted_passphrase = f"enc_{encoded}"
    
    def get_passphrase(self) -> str:
        """Get decrypted passphrase."""
        if self.encrypted_passphrase.startswith("enc_"):
            import base64
            encoded = self.encrypted_passphrase[4:]  # Remove "enc_" prefix
            return base64.b64decode(encoded).decode()
        return self.encrypted_passphrase  # Fallback for non-encrypted


class Job(Base):
    """
    Job model for tracking background tasks using SQLAlchemy 2.0 patterns.
    
    Designed for FastAPI BackgroundTasks integration following best practices.
    """
    __tablename__ = "jobs"
    
    # Primary key with proper type annotation
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Foreign key to repository (with proper constraint naming)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", name="fk_jobs_repository_id"), 
        nullable=False,
        index=True
    )
    
    # Job metadata (using enums to eliminate magic strings)
    job_type: Mapped[JobType] = mapped_column(SQLEnum(JobType), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(SQLEnum(JobStatus), nullable=False, default=JobStatus.PENDING, index=True)
    
    # Job execution details
    source_path: Mapped[Optional[str]] = mapped_column(String(500))
    compression: Mapped[Optional[CompressionType]] = mapped_column(SQLEnum(CompressionType), default=CompressionType.ZSTD)
    
    # Timestamps with proper UTC handling
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(UTC),
        nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    
    # Job output and error tracking
    output_log: Mapped[Optional[str]] = mapped_column(Text)  # Captured command output
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    return_code: Mapped[Optional[int]] = mapped_column()
    
    # Progress tracking
    progress_percentage: Mapped[Optional[int]] = mapped_column(default=0)
    current_step: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Relationships (SQLAlchemy 2.0 pattern)
    repository: Mapped["Repository"] = relationship("Repository", back_populates="jobs")


class NotificationConfig(Base):
    """
    Notification configuration model using enums following FastAPI best practices.
    
    Stores encrypted credentials for notification providers.
    """
    __tablename__ = "notification_configs"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Configuration details
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider: Mapped[NotificationProvider] = mapped_column(
        SQLEnum(NotificationProvider), 
        nullable=False, 
        default=NotificationProvider.PUSHOVER
    )
    enabled: Mapped[bool] = mapped_column(default=True, index=True)
    
    # Encrypted credentials (simplified for sandbox)
    encrypted_user_key: Mapped[Optional[str]] = mapped_column(String(500))
    encrypted_app_token: Mapped[Optional[str]] = mapped_column(String(500))
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(UTC),
        nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )
    
    def set_pushover_credentials(self, user_key: str, app_token: str):
        """Set encrypted Pushover credentials (simplified for sandbox)."""
        import base64
        self.encrypted_user_key = f"enc_{base64.b64encode(user_key.encode()).decode()}"
        self.encrypted_app_token = f"enc_{base64.b64encode(app_token.encode()).decode()}"
    
    def get_pushover_credentials(self) -> tuple[str, str]:
        """Get decrypted Pushover credentials."""
        if self.encrypted_user_key and self.encrypted_user_key.startswith("enc_"):
            import base64
            user_key = base64.b64decode(self.encrypted_user_key[4:]).decode()
            app_token = base64.b64decode(self.encrypted_app_token[4:]).decode()
            return user_key, app_token
        return "", ""


class Task(Base):
    """
    Individual task within a multi-task job using enums.
    
    Enables job orchestration: backup → prune → notification workflow.
    """
    __tablename__ = "tasks"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    
    # Foreign key to job
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", name="fk_tasks_job_id"),
        nullable=False,
        index=True
    )
    
    # Task details using enums
    task_type: Mapped[TaskType] = mapped_column(SQLEnum(TaskType), nullable=False, index=True)
    task_order: Mapped[int] = mapped_column(nullable=False, index=True)  # Execution sequence
    status: Mapped[TaskStatus] = mapped_column(SQLEnum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    
    # Task configuration
    depends_on_success: Mapped[bool] = mapped_column(default=True)  # Only run if previous task succeeded
    notification_config_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("notification_configs.id", name="fk_tasks_notification_config_id")
    )
    
    # Task execution details
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    return_code: Mapped[Optional[int]] = mapped_column()
    
    # Relationships
    job: Mapped["Job"] = relationship("Job", back_populates="tasks")
    notification_config: Mapped[Optional["NotificationConfig"]] = relationship("NotificationConfig")


# Add relationships to existing models
Repository.jobs = relationship("Job", back_populates="repository", cascade="all, delete-orphan")
Job.tasks = relationship("Task", back_populates="job", cascade="all, delete-orphan", order_by="Task.task_order")


# SQLAlchemy 2.0 engine and session setup following tutorial best practices
def create_database_engine(database_url: str = "sqlite:///./sandbox.db", echo: bool = False):
    """
    Create database engine following SQLAlchemy 2.0 best practices.
    
    Args:
        database_url: Database connection string
        echo: Whether to log SQL statements (False for production)
    """
    # SQLAlchemy 2.0 pattern with proper connection args
    connect_args = {"check_same_thread": False} if "sqlite" in database_url else {}
    
    engine = create_engine(
        database_url, 
        echo=echo,
        connect_args=connect_args
    )
    return engine


def create_session_factory(engine):
    """Create session factory following SQLAlchemy 2.0 patterns."""
    return sessionmaker(
        bind=engine,
        autoflush=False,  # Manual control over when to flush
        expire_on_commit=False  # Keep objects accessible after commit
    )