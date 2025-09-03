from datetime import datetime
from typing import Optional, Union
from pydantic import BaseModel, field_validator


class RepositoryBase(BaseModel):
    name: str
    path: str


class RepositoryCreate(RepositoryBase):
    passphrase: str


class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    path: Optional[str] = None
    passphrase: Optional[str] = None


class Repository(RepositoryBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class JobBase(BaseModel):
    type: str


class JobCreate(JobBase):
    repository_id: int


class Job(JobBase):
    id: int
    repository_id: int
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    log_output: Optional[str]
    error: Optional[str]
    container_id: Optional[str]

    class Config:
        from_attributes = True


class ScheduleBase(BaseModel):
    name: str
    cron_expression: str


class ScheduleCreate(ScheduleBase):
    repository_id: int
    source_path: Optional[str] = "/data"
    cloud_backup_config_id: Optional[int] = None
    cleanup_config_id: Optional[int] = None
    notification_config_id: Optional[int] = None
    
    @field_validator('cloud_backup_config_id', mode='before')
    @classmethod
    def validate_cloud_backup_config_id(cls, v):
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
    id: int
    repository_id: int
    source_path: str = "/data"
    enabled: bool
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    created_at: datetime
    cloud_backup_config_id: Optional[int] = None
    cleanup_config_id: Optional[int] = None

    class Config:
        from_attributes = True


class CleanupConfigBase(BaseModel):
    name: str
    strategy: str = "simple"  # "simple" or "advanced"
    keep_within_days: Optional[int] = None
    keep_daily: Optional[int] = None
    keep_weekly: Optional[int] = None
    keep_monthly: Optional[int] = None
    keep_yearly: Optional[int] = None
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
    id: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class NotificationConfigBase(BaseModel):
    name: str
    provider: str = "pushover"
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
    id: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BackupRequest(BaseModel):
    repository_id: int
    source_path: Optional[str] = "/data"
    compression: Optional[str] = "zstd"
    dry_run: Optional[Union[bool, str]] = False
    cloud_backup_config_id: Optional[int] = None
    cleanup_config_id: Optional[int] = None
    notification_config_id: Optional[int] = None
    
    @field_validator('dry_run', mode='before')
    @classmethod
    def validate_dry_run(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    @field_validator('cloud_backup_config_id', mode='before')
    @classmethod
    def validate_cloud_backup_config_id(cls, v):
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


class CloudBackupConfigBase(BaseModel):
    name: str
    provider: str = "s3"  # "s3" or "sftp"
    path_prefix: Optional[str] = ""
    
    # S3-specific fields
    bucket_name: Optional[str] = None
    
    # SFTP-specific fields
    host: Optional[str] = None
    port: Optional[int] = 22
    username: Optional[str] = None
    remote_path: Optional[str] = None


class CloudBackupConfigCreate(CloudBackupConfigBase):
    # S3 credentials
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    
    # SFTP credentials
    password: Optional[str] = None
    private_key: Optional[str] = None


class CloudBackupConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    path_prefix: Optional[str] = None
    
    # S3 fields
    bucket_name: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    
    # SFTP fields
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    remote_path: Optional[str] = None
    password: Optional[str] = None
    private_key: Optional[str] = None
    
    enabled: Optional[bool] = None


class CloudBackupConfig(CloudBackupConfigBase):
    id: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PruneRequest(BaseModel):
    repository_id: int
    strategy: str = "simple"  # "simple" or "advanced"
    # Simple strategy
    keep_within_days: Optional[int] = None
    # Advanced strategy
    keep_daily: Optional[int] = None
    keep_weekly: Optional[int] = None
    keep_monthly: Optional[int] = None
    keep_yearly: Optional[int] = None
    # Options
    show_list: Optional[bool] = True
    show_stats: Optional[bool] = True
    save_space: Optional[bool] = False
    force_prune: Optional[bool] = False
    dry_run: Optional[bool] = True
    
    @field_validator('dry_run', mode='before')
    @classmethod
    def validate_dry_run(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)

class CloudBackupTestRequest(BaseModel):
    config_id: int