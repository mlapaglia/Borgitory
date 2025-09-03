from datetime import datetime
from typing import Optional, Union
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
import re


# Enums for type safety and validation
class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    QUEUED = "queued"


class JobType(str, Enum):
    BACKUP = "backup"
    RESTORE = "restore"
    LIST = "list"
    SYNC = "sync"
    SCHEDULED_BACKUP = "scheduled_backup"


class ProviderType(str, Enum):
    S3 = "s3"
    SFTP = "sftp"
    AZURE = "azure"
    GCP = "gcp"


class CleanupStrategy(str, Enum):
    SIMPLE = "simple"
    ADVANCED = "advanced"


class CompressionType(str, Enum):
    NONE = "none"
    LZ4 = "lz4"
    ZLIB = "zlib" 
    LZMA = "lzma"
    ZSTD = "zstd"


class NotificationProvider(str, Enum):
    PUSHOVER = "pushover"
    EMAIL = "email"
    SLACK = "slack"


class RepositoryBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9-_\s]+$",
        description="Repository name (alphanumeric, hyphens, underscores, spaces only)"
    )
    path: str = Field(
        min_length=1,
        pattern=r"^/.*",
        description="Absolute path to repository (must start with /)"
    )


class RepositoryCreate(RepositoryBase):
    passphrase: str = Field(
        min_length=8,
        description="Passphrase must be at least 8 characters"
    )


class RepositoryUpdate(BaseModel):
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9-_\s]+$"
    )
    path: Optional[str] = Field(
        None,
        min_length=1,
        pattern=r"^/.*"
    )
    passphrase: Optional[str] = Field(
        None,
        min_length=8
    )


class Repository(RepositoryBase):
    id: int = Field(gt=0)
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid"
    }


class JobBase(BaseModel):
    type: JobType


class JobCreate(JobBase):
    repository_id: int = Field(gt=0)


class Job(JobBase):
    id: int = Field(gt=0)
    repository_id: int = Field(gt=0)
    status: JobStatus
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    log_output: Optional[str] = Field(None, max_length=1_000_000)
    error: Optional[str] = Field(None, max_length=10_000)
    container_id: Optional[str] = Field(None, pattern=r"^[a-f0-9]{64}$")

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid"
    }


class ScheduleBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=128,
        description="Schedule name"
    )
    cron_expression: str = Field(
        min_length=5,
        description="Cron expression (e.g., '0 2 * * *' for daily at 2 AM)"
    )
    
    @field_validator('cron_expression')
    @classmethod
    def validate_cron_expression(cls, v):
        """Basic cron expression validation"""
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError("Cron expression must have 5 parts: minute hour day month weekday")
        
        # Basic validation of each part
        for i, part in enumerate(parts):
            if not re.match(r'^[\d\*\-\,\/]+$', part):
                raise ValueError(f"Invalid cron expression part {i+1}: {part}")
        
        return v


class ScheduleCreate(ScheduleBase):
    repository_id: int
    source_path: Optional[str] = "/data"
    cloud_sync_config_id: Optional[int] = None
    cleanup_config_id: Optional[int] = None
    notification_config_id: Optional[int] = None
    
    @field_validator('cloud_sync_config_id', mode='before')
    @classmethod
    def validate_cloud_sync_config_id(cls, v):
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)
    
    @field_validator('cleanup_config_id', mode='before')
    @classmethod
    def validate_cleanup_config_id(cls, v):
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)


class Schedule(ScheduleBase):
    id: int = Field(gt=0)
    repository_id: int = Field(gt=0)
    source_path: str = Field(default="/data", pattern=r"^/.*")
    enabled: bool
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: datetime
    cloud_sync_config_id: Optional[int] = Field(None, gt=0)
    cleanup_config_id: Optional[int] = Field(None, gt=0)

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid"
    }


class CleanupConfigBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=128,
        description="Cleanup configuration name"
    )
    strategy: CleanupStrategy = CleanupStrategy.SIMPLE
    keep_within_days: Optional[int] = Field(None, gt=0, description="Days to keep (simple strategy)")
    keep_daily: Optional[int] = Field(None, ge=0, description="Daily backups to keep")
    keep_weekly: Optional[int] = Field(None, ge=0, description="Weekly backups to keep")
    keep_monthly: Optional[int] = Field(None, ge=0, description="Monthly backups to keep")
    keep_yearly: Optional[int] = Field(None, ge=0, description="Yearly backups to keep")
    show_list: bool = True
    show_stats: bool = True
    save_space: bool = False

class CleanupConfigCreate(CleanupConfigBase):
    pass

class CleanupConfigUpdate(BaseModel):
    name: Optional[str] = None
    strategy: Optional[str] = None
    keep_within_days: Optional[int] = None
    keep_daily: Optional[int] = None
    keep_weekly: Optional[int] = None
    keep_monthly: Optional[int] = None
    keep_yearly: Optional[int] = None
    show_list: Optional[bool] = None
    show_stats: Optional[bool] = None
    save_space: Optional[bool] = None
    enabled: Optional[bool] = None

class CleanupConfig(CleanupConfigBase):
    id: int = Field(gt=0)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid"
    }

class NotificationConfigBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=128,
        description="Notification configuration name"
    )
    provider: NotificationProvider = NotificationProvider.PUSHOVER
    notify_on_success: bool = True
    notify_on_failure: bool = True

class NotificationConfigCreate(NotificationConfigBase):
    user_key: str
    app_token: str

class NotificationConfigUpdate(BaseModel):
    name: Optional[str] = None
    user_key: Optional[str] = None
    app_token: Optional[str] = None
    notify_on_success: Optional[bool] = None
    notify_on_failure: Optional[bool] = None
    enabled: Optional[bool] = None

class NotificationConfig(NotificationConfigBase):
    id: int = Field(gt=0)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid"
    }

class BackupRequest(BaseModel):
    repository_id: int = Field(gt=0)
    source_path: str = Field(
        default="/data",
        pattern=r"^/.*",
        description="Absolute path to source directory"
    )
    compression: CompressionType = CompressionType.ZSTD
    dry_run: bool = False
    cloud_sync_config_id: Optional[int] = Field(None, gt=0)
    cleanup_config_id: Optional[int] = Field(None, gt=0)
    notification_config_id: Optional[int] = Field(None, gt=0)
    
    @field_validator('dry_run', mode='before')
    @classmethod
    def validate_dry_run(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    @field_validator('cloud_sync_config_id', mode='before')
    @classmethod
    def validate_cloud_sync_config_id(cls, v):
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)
    
    @field_validator('cleanup_config_id', mode='before')
    @classmethod
    def validate_cleanup_config_id(cls, v):
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)
    
    @field_validator('notification_config_id', mode='before')
    @classmethod
    def validate_notification_config_id(cls, v):
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)


class CloudSyncConfigBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9-_\s]+$",
        description="Configuration name (alphanumeric, hyphens, underscores, spaces only)"
    )
    provider: ProviderType = ProviderType.S3
    path_prefix: str = Field(
        default="",
        max_length=255,
        description="Optional path prefix for cloud storage"
    )
    
    # S3-specific fields (no validation constraints here - will be validated conditionally)
    bucket_name: Optional[str] = None
    
    # SFTP-specific fields (no validation constraints here - will be validated conditionally)
    host: Optional[str] = None
    port: int = 22
    username: Optional[str] = None
    remote_path: Optional[str] = None


class CloudSyncConfigCreate(CloudSyncConfigBase):
    # S3 credentials (no field validation - will be validated conditionally)
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    
    # SFTP credentials (no field validation - will be validated conditionally)
    password: Optional[str] = None
    private_key: Optional[str] = None
    
    @model_validator(mode='after')
    def validate_provider_specific_fields(self):
        """Validate fields based on the selected provider"""
        
        if self.provider == ProviderType.S3:
            # S3 provider validation
            if not self.bucket_name:
                raise ValueError("S3 bucket name is required for S3 provider")
            
            # Validate S3 bucket name format
            if not re.match(r"^[a-z0-9.-]+$", self.bucket_name):
                raise ValueError("S3 bucket name can only contain lowercase letters, numbers, dots, and hyphens")
            
            if len(self.bucket_name) < 3 or len(self.bucket_name) > 63:
                raise ValueError("S3 bucket name must be between 3 and 63 characters")
            
            if not self.access_key:
                raise ValueError("AWS Access Key ID is required for S3 provider")
            
            if not self.secret_key:
                raise ValueError("AWS Secret Access Key is required for S3 provider")
            
            # Validate AWS Access Key ID
            if len(self.access_key) != 20:
                raise ValueError("AWS Access Key ID must be exactly 20 characters")
            
            if not re.match(r"^[A-Z0-9]+$", self.access_key):
                raise ValueError("AWS Access Key ID can only contain uppercase letters A-Z and digits 0-9")
            
            if not (self.access_key.startswith("AKIA") or self.access_key.startswith("ASIA")):
                raise ValueError("AWS Access Key ID must start with 'AKIA' (standard) or 'ASIA' (temporary)")
            
            # Validate AWS Secret Access Key
            if len(self.secret_key) != 40:
                raise ValueError("AWS Secret Access Key must be exactly 40 characters")
            
            if not re.match(r"^[A-Za-z0-9+/=]+$", self.secret_key):
                raise ValueError("AWS Secret Access Key contains invalid characters")
        
        elif self.provider == ProviderType.SFTP:
            # SFTP provider validation
            if not self.host:
                raise ValueError("SFTP host is required for SFTP provider")
            
            if len(self.host) > 255:
                raise ValueError("SFTP host must be 255 characters or less")
            
            if not self.username:
                raise ValueError("SFTP username is required for SFTP provider")
            
            if len(self.username) > 128:
                raise ValueError("SFTP username must be 128 characters or less")
            
            if self.port < 1 or self.port > 65535:
                raise ValueError("SFTP port must be between 1 and 65535")
            
            if self.remote_path and not self.remote_path.startswith("/"):
                raise ValueError("SFTP remote path must be absolute (start with /)")
            
            # Require either password or private key
            if not self.password and not self.private_key:
                raise ValueError("Either SFTP password or private key is required for SFTP provider")
        
        return self


class CloudSyncConfigUpdate(BaseModel):
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9-_\s]+$"
    )
    provider: Optional[ProviderType] = None
    path_prefix: Optional[str] = Field(None, max_length=255)
    
    # S3 fields (no validation constraints - will be validated conditionally)
    bucket_name: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    
    # SFTP fields (no validation constraints - will be validated conditionally)  
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    remote_path: Optional[str] = None
    password: Optional[str] = None
    private_key: Optional[str] = None
    
    enabled: Optional[bool] = None
    
    @model_validator(mode='after')
    def validate_provider_specific_fields(self):
        """Validate fields based on the selected provider (only validate provided fields)"""
        
        # Only validate if provider is specified (for updates, provider might not be changed)
        if self.provider == ProviderType.S3:
            # S3 provider validation (only validate fields that are provided)
            if self.bucket_name is not None:
                if not self.bucket_name:
                    raise ValueError("S3 bucket name cannot be empty")
                
                if not re.match(r"^[a-z0-9.-]+$", self.bucket_name):
                    raise ValueError("S3 bucket name can only contain lowercase letters, numbers, dots, and hyphens")
                
                if len(self.bucket_name) < 3 or len(self.bucket_name) > 63:
                    raise ValueError("S3 bucket name must be between 3 and 63 characters")
            
            if self.access_key is not None:
                if not self.access_key:
                    raise ValueError("AWS Access Key ID cannot be empty")
                
                if len(self.access_key) != 20:
                    raise ValueError("AWS Access Key ID must be exactly 20 characters")
                
                if not re.match(r"^[A-Z0-9]+$", self.access_key):
                    raise ValueError("AWS Access Key ID can only contain uppercase letters A-Z and digits 0-9")
                
                if not (self.access_key.startswith("AKIA") or self.access_key.startswith("ASIA")):
                    raise ValueError("AWS Access Key ID must start with 'AKIA' (standard) or 'ASIA' (temporary)")
            
            if self.secret_key is not None:
                if not self.secret_key:
                    raise ValueError("AWS Secret Access Key cannot be empty")
                
                if len(self.secret_key) != 40:
                    raise ValueError("AWS Secret Access Key must be exactly 40 characters")
                
                if not re.match(r"^[A-Za-z0-9+/=]+$", self.secret_key):
                    raise ValueError("AWS Secret Access Key contains invalid characters")
        
        elif self.provider == ProviderType.SFTP:
            # SFTP provider validation (only validate fields that are provided)
            if self.host is not None:
                if not self.host:
                    raise ValueError("SFTP host cannot be empty")
                
                if len(self.host) > 255:
                    raise ValueError("SFTP host must be 255 characters or less")
            
            if self.username is not None:
                if not self.username:
                    raise ValueError("SFTP username cannot be empty")
                
                if len(self.username) > 128:
                    raise ValueError("SFTP username must be 128 characters or less")
            
            if self.port is not None:
                if self.port < 1 or self.port > 65535:
                    raise ValueError("SFTP port must be between 1 and 65535")
            
            if self.remote_path is not None:
                if self.remote_path and not self.remote_path.startswith("/"):
                    raise ValueError("SFTP remote path must be absolute (start with /)")
        
        return self


class CloudSyncConfig(CloudSyncConfigBase):
    id: int = Field(gt=0)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid"
    }


class PruneRequest(BaseModel):
    repository_id: int = Field(gt=0)
    strategy: CleanupStrategy = CleanupStrategy.SIMPLE
    # Simple strategy
    keep_within_days: Optional[int] = Field(None, gt=0)
    # Advanced strategy
    keep_daily: Optional[int] = Field(None, ge=0)
    keep_weekly: Optional[int] = Field(None, ge=0)
    keep_monthly: Optional[int] = Field(None, ge=0)
    keep_yearly: Optional[int] = Field(None, ge=0)
    # Options
    show_list: bool = True
    show_stats: bool = True
    save_space: bool = False
    force_prune: bool = False
    dry_run: bool = True
    
    @field_validator('dry_run', mode='before')
    @classmethod
    def validate_dry_run(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)

class CloudSyncTestRequest(BaseModel):
    config_id: int = Field(gt=0, description="Cloud sync configuration ID to test")