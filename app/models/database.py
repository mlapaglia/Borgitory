import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, ForeignKey, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from cryptography.fernet import Fernet

from app.config import DATABASE_URL, SECRET_KEY

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

import base64
import hashlib

# Generate a proper Fernet key from the secret
fernet_key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
cipher_suite = Fernet(fernet_key)


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
    type = Column(String, nullable=False)  # backup, restore, list, etc.
    status = Column(String, nullable=False, default="pending")  # pending, running, completed, failed
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    log_output = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    container_id = Column(String, nullable=True)
    
    repository = relationship("Repository", back_populates="jobs")


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
    
    repository = relationship("Repository", back_populates="schedules")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    credentials = relationship("Credential", back_populates="user")
    sessions = relationship("UserSession", back_populates="user")


class Credential(Base):
    __tablename__ = "credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    credential_id = Column(String, unique=True, nullable=False)
    public_key = Column(LargeBinary, nullable=False)
    sign_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="credentials")


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


async def init_db():
    """Initialize database with schema migration support"""
    try:
        # First, try to create all tables (will create new tables only)
        Base.metadata.create_all(bind=engine)
        
        # Handle specific migrations for existing tables
        migrate_user_table()
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        print("If you're getting schema errors, you may need to reset the database.")
        print("You can do this by deleting the database file and restarting the container.")
        raise


def migrate_user_table():
    """Handle migration of users table to add new columns"""
    from sqlalchemy import text
    
    try:
        with engine.begin() as conn:
            # Check if last_login column exists
            try:
                conn.execute(text("SELECT last_login FROM users LIMIT 1"))
                print("Database schema is up to date")
            except Exception:
                # Column doesn't exist, add it
                print("Migrating users table: adding last_login column...")
                conn.execute(text("ALTER TABLE users ADD COLUMN last_login DATETIME"))
                print("✅ Migration completed: users.last_login column added")
    
    except Exception as e:
        print(f"⚠️  Migration error: {e}")
        print("💡 If you see 'no such column' errors, try deleting the database file and restarting")


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