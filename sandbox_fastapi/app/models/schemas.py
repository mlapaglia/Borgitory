"""
Pydantic schemas for API requests and responses.
"""

from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional
import re

from app.models.enums import (
    JobStatus, JobType, TaskStatus, TaskType, 
    NotificationProvider, CompressionType
)


class RepositoryBase(BaseModel):
    """Base repository schema with comprehensive validation."""
    name: str = Field(
        ..., 
        min_length=1, 
        max_length=100,
        description="Repository name (alphanumeric, spaces, hyphens, underscores only)"
    )
    path: str = Field(
        ..., 
        min_length=1,
        max_length=500,
        description="Repository path (must start with /mnt/)"
    )
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        """Validate repository name follows security best practices."""
        if not v or not v.strip():
            raise ValueError("Repository name cannot be empty")
        
        # Check for dangerous patterns
        dangerous_patterns = [
            r"\.\.+",  # Directory traversal
            r"[<>|&;`$]",  # Command injection characters
            r"\$\(",  # Command substitution
            r"\n|\r",  # Newlines
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, v):
                raise ValueError(f"Repository name contains invalid characters")
        
        return v.strip()
    
    @field_validator('path')
    @classmethod  
    def validate_path(cls, v):
        """Validate repository path is secure."""
        if not v.startswith("/mnt/"):
            raise ValueError("Repository path must start with /mnt/")
        
        if ".." in v:
            raise ValueError("Repository path cannot contain directory traversal")
            
        return v


class RepositoryCreate(RepositoryBase):
    """Schema for creating a repository."""
    passphrase: str = Field(
        ..., 
        min_length=8,
        max_length=256,
        description="Repository passphrase (minimum 8 characters)"
    )
    
    @field_validator('passphrase')
    @classmethod
    def validate_passphrase(cls, v):
        """Validate passphrase strength and security."""
        if len(v) < 8:
            raise ValueError("Passphrase must be at least 8 characters")
        
        # Check for dangerous shell characters
        dangerous_chars = ["'", '"', "`", "$", "\\", "\n", "\r", ";", "&", "|"]
        for char in dangerous_chars:
            if char in v:
                raise ValueError(f"Passphrase contains invalid character: {char}")
        
        return v


class RepositoryImport(RepositoryBase):
    """Schema for importing a repository."""
    passphrase: str = Field(..., min_length=1)
    keyfile_content: Optional[bytes] = None


class RepositoryResponse(RepositoryBase):
    """Schema for repository responses."""
    id: int = Field(..., gt=0, description="Repository ID")
    created_at: datetime = Field(..., description="Repository creation timestamp")
    
    # Pydantic v2 configuration
    model_config = ConfigDict(from_attributes=True)


class BackupRequest(BaseModel):
    """
    Schema for backup job requests following FastAPI best practices.
    
    Comprehensive validation for backup operations.
    """
    repository_id: int = Field(..., gt=0, description="Repository ID to backup")
    source_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Source path to backup (must start with /mnt/)"
    )
    compression: CompressionType = Field(
        CompressionType.ZSTD,
        description="Compression algorithm"
    )
    dry_run: bool = Field(False, description="Whether to perform a dry run")
    
    @field_validator('source_path')
    @classmethod
    def validate_source_path(cls, v):
        """Validate source path is secure."""
        if not v.startswith("/mnt/"):
            raise ValueError("Source path must start with /mnt/")
        
        if ".." in v:
            raise ValueError("Source path cannot contain directory traversal")
            
        return v


class JobResponse(BaseModel):
    """Schema for job responses."""
    id: int = Field(..., gt=0, description="Job ID")
    repository_id: int = Field(..., gt=0, description="Repository ID")
    job_type: JobType = Field(..., description="Type of job")
    status: JobStatus = Field(..., description="Current job status")
    source_path: Optional[str] = Field(None, description="Source path being backed up")
    compression: Optional[CompressionType] = Field(None, description="Compression algorithm used")
    created_at: datetime = Field(..., description="Job creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Job start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")
    progress_percentage: Optional[int] = Field(None, ge=0, le=100, description="Job progress percentage")
    current_step: Optional[str] = Field(None, description="Current step being executed")
    error_message: Optional[str] = Field(None, description="Error message if job failed")
    output_log: Optional[str] = Field(None, description="Captured command output")
    return_code: Optional[int] = Field(None, description="Command return code")
    
    # Pydantic v2 configuration
    model_config = ConfigDict(from_attributes=True)


class BackupResult(BaseModel):
    """Result of backup job creation."""
    job_id: int = Field(..., gt=0, description="Created job ID")
    status: str = Field(..., description="Initial job status")
    message: str = Field(..., description="Result message")


class NotificationConfigCreate(BaseModel):
    """Schema for creating notification configuration."""
    name: str = Field(..., min_length=1, max_length=100, description="Configuration name")
    provider: NotificationProvider = Field(NotificationProvider.PUSHOVER, description="Notification provider")
    user_key: str = Field(..., min_length=1, description="Pushover user key")
    app_token: str = Field(..., min_length=1, description="Pushover app token")
    enabled: bool = Field(True, description="Whether notifications are enabled")


class NotificationConfigResponse(BaseModel):
    """Schema for notification configuration responses."""
    id: int = Field(..., gt=0, description="Configuration ID")
    name: str = Field(..., description="Configuration name")
    provider: NotificationProvider = Field(..., description="Notification provider")
    enabled: bool = Field(..., description="Whether notifications are enabled")
    created_at: datetime = Field(..., description="Configuration creation timestamp")
    
    # Pydantic v2 configuration
    model_config = ConfigDict(from_attributes=True)


class WorkflowJobRequest(BaseModel):
    """Schema for creating multi-task workflow jobs."""
    repository_id: int = Field(..., gt=0, description="Repository ID to backup")
    source_path: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Source path to backup (must start with /mnt/)"
    )
    compression: CompressionType = Field(CompressionType.ZSTD, description="Compression algorithm")
    dry_run: bool = Field(False, description="Whether to perform a dry run")
    notification_config_id: Optional[int] = Field(None, gt=0, description="Notification config ID (optional)")
    
    @field_validator('source_path')
    @classmethod
    def validate_source_path(cls, v):
        """Validate source path is secure."""
        if not v.startswith("/mnt/"):
            raise ValueError("Source path must start with /mnt/")
        if ".." in v:
            raise ValueError("Source path cannot contain directory traversal")
        return v


class TaskResponse(BaseModel):
    """Schema for task responses."""
    id: int = Field(..., gt=0, description="Task ID")
    job_id: int = Field(..., gt=0, description="Job ID")
    task_type: TaskType = Field(..., description="Task type")
    task_order: int = Field(..., description="Task execution order")
    status: TaskStatus = Field(..., description="Task status")
    depends_on_success: bool = Field(..., description="Whether task depends on previous success")
    started_at: Optional[datetime] = Field(None, description="Task start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Task completion timestamp")
    error_message: Optional[str] = Field(None, description="Error message if task failed")
    return_code: Optional[int] = Field(None, description="Task return code")
    
    # Pydantic v2 configuration
    model_config = ConfigDict(from_attributes=True)


class ImportResult(BaseModel):
    """Result of repository import operation."""
    success: bool
    repository: Optional[RepositoryResponse] = None
    message: str


class RepositoryScanResult(BaseModel):
    """Result of repository scanning operation."""
    path: str = Field(..., description="Repository path")
    name: str = Field(..., description="Repository name")
    encryption_mode: str = Field(..., description="Encryption mode (e.g., repokey, keyfile)")
    requires_keyfile: bool = Field(..., description="Whether repository requires a keyfile")
    verified: bool = Field(..., description="Whether repository access was verified")
    preview: str = Field(..., description="Preview information about the repository")


class ValidationResult(BaseModel):
    """Result of repository validation operation."""
    is_valid: bool = Field(..., description="Whether validation passed")
    message: str = Field(..., description="Validation message")
    repository_info: Optional[dict] = Field(None, description="Repository information if valid")