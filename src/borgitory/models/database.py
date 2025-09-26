import base64
import hashlib
import logging
import uuid
import os
from datetime import datetime
from borgitory.utils.datetime_utils import now_utc
from typing import List

from cryptography.fernet import Fernet
from passlib.context import CryptContext
from sqlalchemy import (
    create_engine,
    Integer,
    String,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, declarative_base, mapped_column
from sqlalchemy.orm import sessionmaker, relationship, Session
from typing import Generator

from borgitory.config_module import DATABASE_URL, get_secret_key, DATA_DIR

logger = logging.getLogger(__name__)


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Lazy-loaded cipher suite
_cipher_suite = None


def get_cipher_suite() -> Fernet:
    """Get or create the Fernet cipher suite."""
    global _cipher_suite
    if _cipher_suite is None:
        secret_key = get_secret_key()
        fernet_key = base64.urlsafe_b64encode(
            hashlib.sha256(secret_key.encode()).digest()
        )
        _cipher_suite = Fernet(fernet_key)
    return _cipher_suite


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    encrypted_passphrase: Mapped[str] = mapped_column(String, nullable=False)
    encryption_type: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # "repokey", "keyfile", "none", etc.
    encrypted_keyfile_content: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Encrypted keyfile content
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())

    jobs: Mapped[List["Job"]] = relationship(
        "Job", back_populates="repository", cascade="all, delete-orphan"
    )
    schedules: Mapped[List["Schedule"]] = relationship(
        "Schedule", back_populates="repository", cascade="all, delete-orphan"
    )

    def set_passphrase(self, passphrase: str) -> None:
        self.encrypted_passphrase = (
            get_cipher_suite().encrypt(passphrase.encode()).decode()
        )

    def get_passphrase(self) -> str:
        return get_cipher_suite().decrypt(self.encrypted_passphrase.encode()).decode()

    def set_keyfile_content(self, keyfile_content: str) -> None:
        """Encrypt and store keyfile content."""
        if keyfile_content:
            self.encrypted_keyfile_content = (
                get_cipher_suite().encrypt(keyfile_content.encode()).decode()
            )
        else:
            self.encrypted_keyfile_content = None

    def get_keyfile_content(self) -> str | None:
        """Decrypt and return keyfile content."""
        if self.encrypted_keyfile_content:
            return (
                get_cipher_suite()
                .decrypt(self.encrypted_keyfile_content.encode())
                .decode()
            )
        return None


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, index=True, default=lambda: str(uuid.uuid4())
    )  # UUID as primary key
    repository_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id"), nullable=False
    )
    type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # backup, restore, list, etc.
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )  # pending, running, completed, failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    log_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    container_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cloud_sync_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cloud_sync_configs.id"), nullable=True
    )
    prune_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("prune_configs.id"), nullable=True
    )
    check_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("repository_check_configs.id"), nullable=True
    )
    notification_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notification_configs.id"), nullable=True
    )

    job_type: Mapped[str] = mapped_column(
        String, nullable=False, default="simple"
    )  # 'simple', 'composite'
    total_tasks: Mapped[int] = mapped_column(Integer, default=1)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0)

    repository: Mapped["Repository"] = relationship("Repository", back_populates="jobs")
    cloud_backup_config: Mapped["CloudSyncConfig"] = relationship("CloudSyncConfig")
    check_config: Mapped["RepositoryCheckConfig"] = relationship(
        "RepositoryCheckConfig"
    )
    tasks: Mapped[List["JobTask"]] = relationship(
        "JobTask", back_populates="job", cascade="all, delete-orphan"
    )


class JobTask(Base):
    __tablename__ = "job_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    job_id: Mapped[str] = mapped_column(
        String, ForeignKey("jobs.id"), nullable=False
    )  # UUID foreign key
    task_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # 'backup', 'cloud_sync', 'verify', etc.
    task_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )  # 'pending', 'running', 'completed', 'failed', 'skipped'
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    task_order: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # Order of execution within the job

    job: Mapped["Job"] = relationship("Job", back_populates="tasks")


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    repository_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("repositories.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String, nullable=False)
    source_path: Mapped[str] = mapped_column(String, nullable=False, default="/data")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())
    cloud_sync_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cloud_sync_configs.id"), nullable=True
    )
    prune_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("prune_configs.id"), nullable=True
    )
    check_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("repository_check_configs.id"), nullable=True
    )
    notification_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notification_configs.id"), nullable=True
    )
    pre_job_hooks: Mapped[str | None] = mapped_column(Text, nullable=True)
    post_job_hooks: Mapped[str | None] = mapped_column(Text, nullable=True)

    repository: Mapped["Repository"] = relationship(
        "Repository", back_populates="schedules"
    )
    cloud_sync_config: Mapped["CloudSyncConfig"] = relationship("CloudSyncConfig")
    prune_config: Mapped["PruneConfig"] = relationship("PruneConfig")
    check_config: Mapped["RepositoryCheckConfig"] = relationship(
        "RepositoryCheckConfig"
    )
    notification_config: Mapped["NotificationConfig"] = relationship(
        "NotificationConfig"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession", back_populates="user"
    )

    def set_password(self, password: str) -> None:
        """Hash and store the password"""
        self.password_hash = pwd_context.hash(password)

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash"""
        return pwd_context.verify(password, self.password_hash)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    session_token: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    remember_me: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: now_utc(), onupdate=lambda: now_utc()
    )


class PruneConfig(Base):
    __tablename__ = "prune_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "simple" or "advanced"

    # Simple strategy
    keep_within_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Advanced strategy
    keep_secondly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_minutely: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_hourly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_daily: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_weekly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_monthly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_yearly: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Options
    show_list: Mapped[bool] = mapped_column(Boolean, default=True)
    show_stats: Mapped[bool] = mapped_column(Boolean, default=True)
    save_space: Mapped[bool] = mapped_column(Boolean, default=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: now_utc(), onupdate=lambda: now_utc()
    )


class NotificationConfig(Base):
    __tablename__ = "notification_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "pushover", "discord", "slack", "email", etc.

    # JSON configuration field for provider-specific settings
    provider_config: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON field for provider configuration

    # Common fields
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: now_utc(), onupdate=lambda: now_utc()
    )


class CloudSyncConfig(Base):
    __tablename__ = "cloud_sync_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "s3", "sftp", "azure", "gcp", etc.

    # JSON configuration field for provider-specific settings
    provider_config: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON field for provider configuration

    # Common fields
    path_prefix: Mapped[str] = mapped_column(String, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: now_utc(), onupdate=lambda: now_utc()
    )


class RepositoryCheckConfig(Base):
    __tablename__ = "repository_check_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # Check Type
    check_type: Mapped[str] = mapped_column(
        String, nullable=False, default="full"
    )  # "full", "repository_only", "archives_only"

    # Verification Options
    verify_data: Mapped[bool] = mapped_column(Boolean, default=False)
    repair_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    save_space: Mapped[bool] = mapped_column(Boolean, default=False)

    # Advanced Options
    max_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)  # seconds
    archive_prefix: Mapped[str | None] = mapped_column(String, nullable=True)
    archive_glob: Mapped[str | None] = mapped_column(String, nullable=True)
    first_n_archives: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_n_archives: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Metadata
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: now_utc(), onupdate=lambda: now_utc()
    )


class UserInstalledPackage(Base):
    """Model for tracking user-installed packages for persistence across container restarts."""

    __tablename__ = "user_installed_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    package_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: now_utc())

    # Metadata about the installation
    install_command: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # The exact command used
    dependencies_installed: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON list of deps that were also installed


async def init_db() -> None:
    """Initialize database - assumes migrations have already been run"""

    try:
        logger.info(f"Initializing database at: {DATABASE_URL}")
        logger.info(f"Data directory: {DATA_DIR}")

        os.makedirs(DATA_DIR, exist_ok=True)
        logger.info("Data directory ensured")

        from sqlalchemy import text

        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            result.fetchone()
            logger.info("Database connection test successful")

        try:
            from borgitory.utils.migrations import get_current_revision

            current_revision = get_current_revision()
            logger.info(f"Current database revision: {current_revision}")
        except Exception as e:
            logger.warning(f"Could not check migration status: {e}")
            logger.error("Make sure migrations have been run with: borgitory migrate")

        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        logger.error("Make sure migrations have been run with: borgitory migrate")
        raise


def reset_db() -> None:
    """Reset the entire database - USE WITH CAUTION"""
    logger.info("Resetting database...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("Database reset complete")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
