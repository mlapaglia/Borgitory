import base64
import hashlib
import logging
import uuid
import os
from datetime import datetime, UTC

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
from sqlalchemy.orm import sessionmaker, relationship

from borgitory.config import DATABASE_URL, get_secret_key, DATA_DIR

logger = logging.getLogger(__name__)


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Lazy-loaded cipher suite
_cipher_suite = None


def get_cipher_suite():
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )

    jobs = relationship(
        "Job", back_populates="repository", cascade="all, delete-orphan"
    )
    schedules = relationship(
        "Schedule", back_populates="repository", cascade="all, delete-orphan"
    )

    def set_passphrase(self, passphrase: str):
        self.encrypted_passphrase = (
            get_cipher_suite().encrypt(passphrase.encode()).decode()
        )

    def get_passphrase(self) -> str:
        return get_cipher_suite().decrypt(self.encrypted_passphrase.encode()).decode()


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
    cleanup_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cleanup_configs.id"), nullable=True
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

    repository = relationship("Repository", back_populates="jobs")
    cloud_backup_config = relationship("CloudSyncConfig")
    check_config = relationship("RepositoryCheckConfig")
    tasks = relationship("JobTask", back_populates="job", cascade="all, delete-orphan")


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

    job = relationship("Job", back_populates="tasks")


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    cloud_sync_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cloud_sync_configs.id"), nullable=True
    )
    cleanup_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("cleanup_configs.id"), nullable=True
    )
    check_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("repository_check_configs.id"), nullable=True
    )
    notification_config_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("notification_configs.id"), nullable=True
    )

    repository = relationship("Repository", back_populates="schedules")
    cloud_sync_config = relationship("CloudSyncConfig")
    cleanup_config = relationship("CleanupConfig")
    check_config = relationship("RepositoryCheckConfig")
    notification_config = relationship("NotificationConfig")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String, unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions = relationship("UserSession", back_populates="user")

    def set_password(self, password: str):
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)

    user = relationship("User", back_populates="sessions")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class CleanupConfig(Base):
    __tablename__ = "cleanup_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    strategy: Mapped[str] = mapped_column(
        String, nullable=False
    )  # "simple" or "advanced"

    # Simple strategy
    keep_within_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Advanced strategy
    keep_daily: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_weekly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_monthly: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_yearly: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Options
    show_list: Mapped[bool] = mapped_column(Boolean, default=True)
    show_stats: Mapped[bool] = mapped_column(Boolean, default=True)
    save_space: Mapped[bool] = mapped_column(Boolean, default=False)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class NotificationConfig(Base):
    __tablename__ = "notification_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)  # "pushover"

    # Pushover-specific fields
    encrypted_user_key: Mapped[str | None] = mapped_column(String, nullable=True)
    encrypted_app_token: Mapped[str | None] = mapped_column(String, nullable=True)

    # Notification settings
    notify_on_success: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_on_failure: Mapped[bool] = mapped_column(Boolean, default=True)

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def set_pushover_credentials(self, user_key: str, app_token: str):
        """Encrypt and store Pushover credentials"""
        self.encrypted_user_key = get_cipher_suite().encrypt(user_key.encode()).decode()
        self.encrypted_app_token = (
            get_cipher_suite().encrypt(app_token.encode()).decode()
        )

    def get_pushover_credentials(self) -> tuple[str, str]:
        """Decrypt and return Pushover credentials"""
        if not self.encrypted_user_key or not self.encrypted_app_token:
            raise ValueError("Pushover credentials not set")
        user_key = get_cipher_suite().decrypt(self.encrypted_user_key.encode()).decode()
        app_token = (
            get_cipher_suite().decrypt(self.encrypted_app_token.encode()).decode()
        )
        return user_key, app_token


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


async def init_db():
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
                result = connection.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs';"
                    )
                )
                if not result.fetchone():
                    logger.info(
                        "Tables not found, creating them from borgitory.models..."
                    )
                    Base.metadata.create_all(bind=engine)
                    logger.info("Database tables created successfully")
                else:
                    logger.info("Database tables already exist")
            except Exception as e:
                logger.warning(f"Could not check/create tables: {e}")

        try:
            from borgitory.utils.migrations import get_current_revision

            current_revision = get_current_revision()
            logger.info(f"Current database revision: {current_revision}")
        except Exception as e:
            logger.warning(f"Could not check migration status: {e}")

        logger.info("Database initialization completed successfully")

    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        logger.error("Make sure migrations have been run with: alembic upgrade head")
        raise


def reset_db():
    """Reset the entire database - USE WITH CAUTION"""
    logger.info("Resetting database...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.info("Database reset complete")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
