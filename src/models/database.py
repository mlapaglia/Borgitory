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
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

from config import DATABASE_URL, get_secret_key, DATA_DIR

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

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    path = Column(String, nullable=False)
    encrypted_passphrase = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))

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

    id = Column(
        String, primary_key=True, index=True, default=lambda: str(uuid.uuid4())
    )  # UUID as primary key
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    type = Column(String, nullable=False)  # backup, restore, list, etc.
    status = Column(
        String, nullable=False, default="pending"
    )  # pending, running, completed, failed
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    log_output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    container_id = Column(String, nullable=True)
    cloud_sync_config_id = Column(
        Integer, ForeignKey("cloud_sync_configs.id"), nullable=True
    )
    cleanup_config_id = Column(Integer, ForeignKey("cleanup_configs.id"), nullable=True)
    check_config_id = Column(
        Integer, ForeignKey("repository_check_configs.id"), nullable=True
    )
    notification_config_id = Column(
        Integer, ForeignKey("notification_configs.id"), nullable=True
    )

    job_type = Column(String, nullable=False, default="simple")  # 'simple', 'composite'
    total_tasks = Column(Integer, default=1)
    completed_tasks = Column(Integer, default=0)

    repository = relationship("Repository", back_populates="jobs")
    cloud_backup_config = relationship("CloudSyncConfig")
    check_config = relationship("RepositoryCheckConfig")
    tasks = relationship("JobTask", back_populates="job", cascade="all, delete-orphan")


class JobTask(Base):
    __tablename__ = "job_tasks"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)  # UUID foreign key
    task_type = Column(String, nullable=False)  # 'backup', 'cloud_sync', 'verify', etc.
    task_name = Column(String, nullable=False)
    status = Column(
        String, nullable=False, default="pending"
    )  # 'pending', 'running', 'completed', 'failed', 'skipped'
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    return_code = Column(Integer, nullable=True)
    task_order = Column(Integer, nullable=False)  # Order of execution within the job

    job = relationship("Job", back_populates="tasks")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    name = Column(String, nullable=False)
    cron_expression = Column(String, nullable=False)
    source_path = Column(String, nullable=False, default="/data")
    enabled = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    cloud_sync_config_id = Column(
        Integer, ForeignKey("cloud_sync_configs.id"), nullable=True
    )
    cleanup_config_id = Column(Integer, ForeignKey("cleanup_configs.id"), nullable=True)
    check_config_id = Column(
        Integer, ForeignKey("repository_check_configs.id"), nullable=True
    )
    notification_config_id = Column(
        Integer, ForeignKey("notification_configs.id"), nullable=True
    )

    repository = relationship("Repository", back_populates="schedules")
    cloud_sync_config = relationship("CloudSyncConfig")
    cleanup_config = relationship("CleanupConfig")
    check_config = relationship("RepositoryCheckConfig")
    notification_config = relationship("NotificationConfig")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    last_login = Column(DateTime, nullable=True)

    sessions = relationship("UserSession", back_populates="user")

    def set_password(self, password: str):
        """Hash and store the password"""
        self.password_hash = pwd_context.hash(password)

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash"""
        return pwd_context.verify(password, self.password_hash)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    remember_me = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    last_activity = Column(DateTime, default=lambda: datetime.now(UTC))
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)

    user = relationship("User", back_populates="sessions")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class CleanupConfig(Base):
    __tablename__ = "cleanup_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    strategy = Column(String, nullable=False)  # "simple" or "advanced"

    # Simple strategy
    keep_within_days = Column(Integer, nullable=True)

    # Advanced strategy
    keep_daily = Column(Integer, nullable=True)
    keep_weekly = Column(Integer, nullable=True)
    keep_monthly = Column(Integer, nullable=True)
    keep_yearly = Column(Integer, nullable=True)

    # Options
    show_list = Column(Boolean, default=True)
    show_stats = Column(Boolean, default=True)
    save_space = Column(Boolean, default=False)

    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class NotificationConfig(Base):
    __tablename__ = "notification_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)  # "pushover"

    # Pushover-specific fields
    encrypted_user_key = Column(String, nullable=True)
    encrypted_app_token = Column(String, nullable=True)

    # Notification settings
    notify_on_success = Column(Boolean, default=True)
    notify_on_failure = Column(Boolean, default=True)

    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
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
        user_key = get_cipher_suite().decrypt(self.encrypted_user_key.encode()).decode()
        app_token = (
            get_cipher_suite().decrypt(self.encrypted_app_token.encode()).decode()
        )
        return user_key, app_token


class CloudSyncConfig(Base):
    __tablename__ = "cloud_sync_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)  # "s3", "sftp", "azure", "gcp", etc.

    # S3-specific fields
    bucket_name = Column(String, nullable=True)  # Made nullable for non-S3 providers
    encrypted_access_key = Column(
        String, nullable=True
    )  # Made nullable for non-S3 providers
    encrypted_secret_key = Column(
        String, nullable=True
    )  # Made nullable for non-S3 providers

    # SFTP-specific fields
    host = Column(String, nullable=True)
    port = Column(Integer, nullable=True, default=22)
    username = Column(String, nullable=True)
    encrypted_password = Column(String, nullable=True)
    encrypted_private_key = Column(Text, nullable=True)  # SSH private key
    remote_path = Column(String, nullable=True)  # Remote directory path

    # Common fields
    path_prefix = Column(String, default="", nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    def set_credentials(self, access_key: str, secret_key: str):
        """For S3 providers"""
        self.encrypted_access_key = (
            get_cipher_suite().encrypt(access_key.encode()).decode()
        )
        self.encrypted_secret_key = (
            get_cipher_suite().encrypt(secret_key.encode()).decode()
        )

    def get_credentials(self) -> tuple[str, str]:
        """For S3 providers"""
        access_key = (
            get_cipher_suite().decrypt(self.encrypted_access_key.encode()).decode()
        )
        secret_key = (
            get_cipher_suite().decrypt(self.encrypted_secret_key.encode()).decode()
        )
        return access_key, secret_key

    def set_sftp_credentials(self, password: str = None, private_key: str = None):
        """For SFTP providers"""
        if password:
            self.encrypted_password = (
                get_cipher_suite().encrypt(password.encode()).decode()
            )
        if private_key:
            self.encrypted_private_key = (
                get_cipher_suite().encrypt(private_key.encode()).decode()
            )

    def get_sftp_credentials(self) -> tuple[str, str]:
        """For SFTP providers - returns (password, private_key)"""
        password = ""
        private_key = ""

        if self.encrypted_password:
            password = (
                get_cipher_suite().decrypt(self.encrypted_password.encode()).decode()
            )
        if self.encrypted_private_key:
            private_key = (
                get_cipher_suite().decrypt(self.encrypted_private_key.encode()).decode()
            )

        return password, private_key


class RepositoryCheckConfig(Base):
    __tablename__ = "repository_check_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(String, nullable=True)

    # Check Type
    check_type = Column(
        String, nullable=False, default="full"
    )  # "full", "repository_only", "archives_only"

    # Verification Options
    verify_data = Column(Boolean, default=False)
    repair_mode = Column(Boolean, default=False)
    save_space = Column(Boolean, default=False)

    # Advanced Options
    max_duration = Column(Integer, nullable=True)  # seconds
    archive_prefix = Column(String, nullable=True)
    archive_glob = Column(String, nullable=True)
    first_n_archives = Column(Integer, nullable=True)
    last_n_archives = Column(Integer, nullable=True)

    # Metadata
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(
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
                    logger.info("Tables not found, creating them from models...")
                    Base.metadata.create_all(bind=engine)
                    logger.info("Database tables created successfully")
                else:
                    logger.info("Database tables already exist")
            except Exception as e:
                logger.warning(f"Could not check/create tables: {e}")

        try:
            from utils.migrations import get_current_revision

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
