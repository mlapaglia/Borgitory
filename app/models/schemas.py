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
    cloud_backup_config_id: Optional[int] = None


class Schedule(ScheduleBase):
    id: int
    repository_id: int
    enabled: bool
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    created_at: datetime
    cloud_backup_config_id: Optional[int] = None

    class Config:
        from_attributes = True


class BackupRequest(BaseModel):
    repository_id: int
    source_path: Optional[str] = "/data"
    compression: Optional[str] = "zstd"
    dry_run: Optional[Union[bool, str]] = False
    cloud_backup_config_id: Optional[int] = None
    
    @field_validator('dry_run', mode='before')
    @classmethod
    def validate_dry_run(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)


class CloudBackupConfigBase(BaseModel):
    name: str
    provider: str = "s3"
    region: Optional[str] = "us-east-1"
    bucket_name: str
    path_prefix: Optional[str] = ""
    endpoint: Optional[str] = None


class CloudBackupConfigCreate(CloudBackupConfigBase):
    access_key: str
    secret_key: str


class CloudBackupConfigUpdate(BaseModel):
    name: Optional[str] = None
    region: Optional[str] = None
    bucket_name: Optional[str] = None
    path_prefix: Optional[str] = None
    endpoint: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    enabled: Optional[bool] = None


class CloudBackupConfig(CloudBackupConfigBase):
    id: int
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CloudBackupTestRequest(BaseModel):
    config_id: int