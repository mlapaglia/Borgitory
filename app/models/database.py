import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from cryptography.fernet import Fernet

from app.config import DATABASE_URL, SECRET_KEY, DATA_DIR

import os

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

import base64
import hashlib
from passlib.context import CryptContext

# Generate a proper Fernet key from the secret
fernet_key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
cipher_suite = Fernet(fernet_key)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    path = Column(String, nullable=False)
    encrypted_passphrase = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    jobs = relationship("Job", back_populates="repository", cascade="all, delete-orphan")
    schedules = relationship("Schedule", back_populates="repository", cascade="all, delete-orphan")

    def set_passphrase(self, passphrase: str):
        self.encrypted_passphrase = cipher_suite.encrypt(passphrase.encode()).decode()
    
    def get_passphrase(self) -> str:
        return cipher_suite.decrypt(self.encrypted_passphrase.encode()).decode()


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id"), nullable=False)
    job_uuid = Column(String, nullable=True, index=True)  # Links to JobManager UUID
    type = Column(String, nullable=False)  # backup, restore, list, etc.
    status = Column(String, nullable=False, default="pending")  # pending, running, completed, failed
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    log_output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    container_id = Column(String, nullable=True)
    cloud_backup_config_id = Column(Integer, ForeignKey("cloud_backup_configs.id"), nullable=True)
    
    # New composite job fields
    job_type = Column(String, nullable=False, default="simple")  # 'simple', 'composite'
    total_tasks = Column(Integer, default=1)
    completed_tasks = Column(Integer, default=0)
    
    repository = relationship("Repository", back_populates="jobs")
    cloud_backup_config = relationship("CloudBackupConfig")
    tasks = relationship("JobTask", back_populates="job", cascade="all, delete-orphan")


class JobTask(Base):
    __tablename__ = "job_tasks"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    task_type = Column(String, nullable=False)  # 'backup', 'cloud_sync', 'verify', etc.
    task_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")  # 'pending', 'running', 'completed', 'failed', 'skipped'
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
    enabled = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    cloud_backup_config_id = Column(Integer, ForeignKey("cloud_backup_configs.id"), nullable=True)
    
    repository = relationship("Repository", back_populates="schedules")
    cloud_backup_config = relationship("CloudBackupConfig")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
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
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    user_agent = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)
    
    user = relationship("User", back_populates="sessions")


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CloudBackupConfig(Base):
    __tablename__ = "cloud_backup_configs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    provider = Column(String, nullable=False)  # "s3", "sftp", "azure", "gcp", etc.
    
    # S3-specific fields
    region = Column(String, nullable=True)
    bucket_name = Column(String, nullable=True)  # Made nullable for non-S3 providers
    endpoint = Column(String, nullable=True)
    encrypted_access_key = Column(String, nullable=True)  # Made nullable for non-S3 providers
    encrypted_secret_key = Column(String, nullable=True)  # Made nullable for non-S3 providers
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_credentials(self, access_key: str, secret_key: str):
        """For S3 providers"""
        self.encrypted_access_key = cipher_suite.encrypt(access_key.encode()).decode()
        self.encrypted_secret_key = cipher_suite.encrypt(secret_key.encode()).decode()
    
    def get_credentials(self) -> tuple[str, str]:
        """For S3 providers"""
        access_key = cipher_suite.decrypt(self.encrypted_access_key.encode()).decode()
        secret_key = cipher_suite.decrypt(self.encrypted_secret_key.encode()).decode()
        return access_key, secret_key
    
    def set_sftp_credentials(self, password: str = None, private_key: str = None):
        """For SFTP providers"""
        if password:
            self.encrypted_password = cipher_suite.encrypt(password.encode()).decode()
        if private_key:
            self.encrypted_private_key = cipher_suite.encrypt(private_key.encode()).decode()
    
    def get_sftp_credentials(self) -> tuple[str, str]:
        """For SFTP providers - returns (password, private_key)"""
        password = ""
        private_key = ""
        
        if self.encrypted_password:
            password = cipher_suite.decrypt(self.encrypted_password.encode()).decode()
        if self.encrypted_private_key:
            private_key = cipher_suite.decrypt(self.encrypted_private_key.encode()).decode()
            
        return password, private_key


async def init_db():
    """Initialize database with schema migration support"""
    try:
        print(f"Initializing database at: {DATABASE_URL}")
        print(f"Data directory: {DATA_DIR}")
        
        # Create all tables (will create new tables only)
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables created/verified")

    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        print("If you're getting schema errors, you may need to reset the database.")
        print("You can do this by deleting the database file and restarting the container.")
        raise  # Re-raise the exception so the app doesn't start with a broken database

def reset_db():
    """Reset the entire database - USE WITH CAUTION"""
    print("🔄 Resetting database...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("✅ Database reset complete")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()