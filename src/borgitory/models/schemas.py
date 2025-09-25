from datetime import datetime
from typing import Dict, Optional, Union, cast
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
import re

from borgitory.custom_types import ConfigDict
from borgitory.services.hooks.hook_config import validate_hooks_json


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
    CHECK = "check"


class PruneStrategy(str, Enum):
    SIMPLE = "simple"
    ADVANCED = "advanced"


class CheckType(str, Enum):
    FULL = "full"
    REPOSITORY_ONLY = "repository_only"
    ARCHIVES_ONLY = "archives_only"


class CompressionType(str, Enum):
    NONE = "none"
    LZ4 = "lz4"
    ZLIB = "zlib"
    LZMA = "lzma"
    ZSTD = "zstd"


# NotificationProvider enum removed - using flexible string field instead


class RepositoryBase(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9-_\s]+$",
        description="Repository name (alphanumeric, hyphens, underscores, spaces only)",
    )
    path: str = Field(
        min_length=1,
        pattern=r"^/.*",
        description="Absolute path to repository (must start with /)",
    )

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, v: str) -> str:
        from borgitory.utils.path_prefix import normalize_path_with_mnt_prefix

        return normalize_path_with_mnt_prefix(v)


class RepositoryCreate(RepositoryBase):
    passphrase: str = Field(
        min_length=8, description="Passphrase must be at least 8 characters"
    )


class RepositoryUpdate(BaseModel):
    name: Optional[str] = Field(
        None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9-_\s]+$"
    )
    path: Optional[str] = Field(None, min_length=1, pattern=r"^/.*")
    passphrase: Optional[str] = Field(None, min_length=8)

    @field_validator("path", mode="before")
    @classmethod
    def validate_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        from borgitory.utils.path_prefix import normalize_path_with_mnt_prefix

        return normalize_path_with_mnt_prefix(v)


class Repository(RepositoryBase):
    id: int = Field(gt=0)
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid",
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
        "extra": "forbid",
    }


class ScheduleBase(BaseModel):
    name: str = Field(min_length=1, max_length=128, description="Schedule name")
    cron_expression: str = Field(
        min_length=5,
        description="Cron expression (e.g., '0 2 * * *' for daily at 2 AM)",
    )

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v: str) -> str:
        """Basic cron expression validation"""
        parts = v.strip().split()
        if len(parts) != 5:
            raise ValueError(
                "Cron expression must have 5 parts: minute hour day month weekday"
            )

        # Basic validation of each part
        for i, part in enumerate(parts):
            if not re.match(r"^[\d\*\-\,\/]+$", part):
                raise ValueError(f"Invalid cron expression part {i + 1}: {part}")

        return v


class ScheduleCreate(ScheduleBase):
    repository_id: int
    source_path: Optional[str] = "/data"
    cloud_sync_config_id: Optional[int] = None
    prune_config_id: Optional[int] = None
    check_config_id: Optional[int] = None
    notification_config_id: Optional[int] = None
    pre_job_hooks: Optional[str] = None
    post_job_hooks: Optional[str] = None

    @field_validator("source_path", mode="before")
    @classmethod
    def validate_source_path(cls, v: Union[str, int, float, bool, None]) -> str:
        from borgitory.utils.path_prefix import normalize_path_with_mnt_prefix

        return normalize_path_with_mnt_prefix(str(v))

    @field_validator("cloud_sync_config_id", mode="before")
    @classmethod
    def validate_cloud_sync_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("prune_config_id", mode="before")
    @classmethod
    def validate_prune_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("check_config_id", mode="before")
    @classmethod
    def validate_check_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("notification_config_id", mode="before")
    @classmethod
    def validate_notification_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("pre_job_hooks", mode="before")
    @classmethod
    def validate_pre_job_hooks(cls, v: Union[str, None]) -> Optional[str]:
        if not v or v.strip() == "":
            return None

        is_valid, error_msg = validate_hooks_json(v)
        if not is_valid:
            raise ValueError(f"Invalid pre-job hooks configuration: {error_msg}")
        return v.strip()

    @field_validator("post_job_hooks", mode="before")
    @classmethod
    def validate_post_job_hooks(cls, v: Union[str, None]) -> Optional[str]:
        if not v or v.strip() == "":
            return None

        is_valid, error_msg = validate_hooks_json(v)
        if not is_valid:
            raise ValueError(f"Invalid post-job hooks configuration: {error_msg}")
        return v.strip()


class ScheduleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    cron_expression: Optional[str] = Field(None, min_length=5)
    repository_id: Optional[int] = None
    source_path: Optional[str] = None
    cloud_sync_config_id: Optional[int] = None
    prune_config_id: Optional[int] = None
    check_config_id: Optional[int] = None
    notification_config_id: Optional[int] = None
    enabled: Optional[bool] = None
    pre_job_hooks: Optional[str] = None
    post_job_hooks: Optional[str] = None

    @field_validator("source_path", mode="before")
    @classmethod
    def validate_source_path(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        from borgitory.utils.path_prefix import normalize_path_with_mnt_prefix

        return normalize_path_with_mnt_prefix(v)

    @field_validator("pre_job_hooks", mode="before")
    @classmethod
    def validate_pre_job_hooks_update(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None

        is_valid, error_msg = validate_hooks_json(v)
        if not is_valid:
            raise ValueError(f"Invalid pre-job hooks configuration: {error_msg}")
        return v.strip()

    @field_validator("post_job_hooks", mode="before")
    @classmethod
    def validate_post_job_hooks_update(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None

        is_valid, error_msg = validate_hooks_json(v)
        if not is_valid:
            raise ValueError(f"Invalid post-job hooks configuration: {error_msg}")
        return v.strip()

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        parts = v.split()
        if len(parts) != 5:
            raise ValueError(
                "Invalid cron expression format. Expected 5 parts: minute hour day_of_month month day_of_week"
            )
        for i, part in enumerate(parts):
            if not re.match(r"^[\d\*\-\,\/]+$", part):
                raise ValueError(f"Invalid cron expression part {i + 1}: {part}")
        return v

    @field_validator("cloud_sync_config_id", mode="before")
    @classmethod
    def validate_cloud_sync_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("prune_config_id", mode="before")
    @classmethod
    def validate_prune_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("check_config_id", mode="before")
    @classmethod
    def validate_check_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("notification_config_id", mode="before")
    @classmethod
    def validate_notification_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
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
    prune_config_id: Optional[int] = Field(None, gt=0)

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid",
    }


class PruneConfigBase(BaseModel):
    name: str = Field(
        min_length=1, max_length=128, description="Prune configuration name"
    )
    strategy: PruneStrategy = PruneStrategy.SIMPLE
    keep_within_days: Optional[int] = Field(
        None, gt=0, description="Days to keep (simple strategy)"
    )
    keep_secondly: Optional[int] = Field(
        None, ge=0, description="Secondly backups to keep"
    )
    keep_minutely: Optional[int] = Field(
        None, ge=0, description="Minutely backups to keep"
    )
    keep_hourly: Optional[int] = Field(None, ge=0, description="Hourly backups to keep")
    keep_daily: Optional[int] = Field(None, ge=0, description="Daily backups to keep")
    keep_weekly: Optional[int] = Field(None, ge=0, description="Weekly backups to keep")
    keep_monthly: Optional[int] = Field(
        None, ge=0, description="Monthly backups to keep"
    )
    keep_yearly: Optional[int] = Field(None, ge=0, description="Yearly backups to keep")
    show_list: bool = True
    show_stats: bool = True
    save_space: bool = False


class PruneConfigCreate(PruneConfigBase):
    pass


class PruneConfigUpdate(BaseModel):
    name: Optional[str] = None
    strategy: Optional[str] = None
    keep_within_days: Optional[int] = None
    keep_secondly: Optional[int] = None
    keep_minutely: Optional[int] = None
    keep_hourly: Optional[int] = None
    keep_daily: Optional[int] = None
    keep_weekly: Optional[int] = None
    keep_monthly: Optional[int] = None
    keep_yearly: Optional[int] = None
    show_list: Optional[bool] = None
    show_stats: Optional[bool] = None
    save_space: Optional[bool] = None
    enabled: Optional[bool] = None


class PruneConfig(PruneConfigBase):
    id: int = Field(gt=0)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid",
    }


class NotificationConfigBase(BaseModel):
    name: str = Field(
        min_length=1, max_length=128, description="Notification configuration name"
    )
    provider: str = Field(
        description="Notification provider (pushover, discord, slack, email, etc.)"
    )
    provider_config: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Provider-specific configuration"
    )


class NotificationConfigCreate(NotificationConfigBase):
    pass


class NotificationConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    provider_config: Optional[Dict[str, Union[str, int, float, bool]]] = None
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
        "extra": "forbid",
    }


class BackupRequest(BaseModel):
    repository_id: int = Field(gt=0)
    source_path: str = Field(
        default="/",
        pattern=r"^/.*",
        description="Absolute path to source directory",
    )
    compression: CompressionType = CompressionType.ZSTD
    dry_run: bool = False
    ignore_lock: bool = False
    cloud_sync_config_id: Optional[int] = Field(None, gt=0)
    prune_config_id: Optional[int] = Field(None, gt=0)
    check_config_id: Optional[int] = Field(None, gt=0)
    notification_config_id: Optional[int] = Field(None, gt=0)
    pre_job_hooks: Optional[str] = None
    post_job_hooks: Optional[str] = None

    @field_validator("source_path", mode="before")
    @classmethod
    def validate_source_path(cls, v: Union[str, int, float, bool, None]) -> str:
        from borgitory.utils.path_prefix import normalize_path_with_mnt_prefix

        return normalize_path_with_mnt_prefix(str(v))

    @field_validator("dry_run", mode="before")
    @classmethod
    def validate_dry_run(cls, v: Union[str, bool, int]) -> bool:
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("cloud_sync_config_id", mode="before")
    @classmethod
    def validate_cloud_sync_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("prune_config_id", mode="before")
    @classmethod
    def validate_prune_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("check_config_id", mode="before")
    @classmethod
    def validate_check_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @field_validator("notification_config_id", mode="before")
    @classmethod
    def validate_notification_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
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
        description="Configuration name (alphanumeric, hyphens, underscores, spaces only)",
    )
    provider: str = "s3"
    path_prefix: str = Field(
        default="", max_length=255, description="Optional path prefix for cloud storage"
    )
    provider_config: ConfigDict = Field(
        default_factory=dict, description="Provider-specific configuration"
    )

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        """Validate that provider is registered in the registry."""
        from borgitory.services.cloud_providers.registry import (
            is_provider_registered,
            get_all_provider_info,
        )

        if not v:
            raise ValueError("Provider is required")

        if not is_provider_registered(v):
            supported = sorted(get_all_provider_info().keys())
            raise ValueError(
                f"Unknown provider '{v}'. Supported providers: {supported}"
            )

        return v


class CloudSyncConfigCreate(CloudSyncConfigBase):
    @model_validator(mode="after")
    def validate_provider_config(self) -> "CloudSyncConfigCreate":
        """Validate provider_config using the registry"""
        from borgitory.services.cloud_providers.registry import validate_provider_config

        if not self.provider_config:
            raise ValueError("provider_config is required")

        validate_provider_config(
            self.provider, cast(Dict[str, object], self.provider_config)
        )
        return self


class CloudSyncConfigUpdate(BaseModel):
    name: Optional[str] = Field(
        None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9-_\s]+$"
    )
    provider: Optional[str] = None
    path_prefix: Optional[str] = Field(None, max_length=255)
    provider_config: Optional[ConfigDict] = Field(
        None, description="Provider-specific configuration"
    )
    enabled: Optional[bool] = None

    @field_validator("provider")
    @classmethod
    def validate_provider_field(cls, v: Optional[str]) -> Optional[str]:
        """Validate that provider is registered in the registry if provided."""
        if v is None:
            return v

        from borgitory.services.cloud_providers.registry import (
            is_provider_registered,
            get_all_provider_info,
        )

        if not is_provider_registered(v):
            supported = sorted(get_all_provider_info().keys())
            raise ValueError(
                f"Unknown provider '{v}'. Supported providers: {supported}"
            )

        return v

    @model_validator(mode="after")
    def validate_provider_config(self) -> "CloudSyncConfigUpdate":
        """Validate provider_config if provided"""

        if self.provider and self.provider_config:
            from borgitory.services.cloud_providers.registry import (
                validate_provider_config,
            )

            validate_provider_config(
                self.provider, cast(Dict[str, object], self.provider_config)
            )

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
        "extra": "forbid",
    }


class RepositoryCheckConfigBase(BaseModel):
    name: str = Field(
        min_length=1, max_length=128, description="Repository check configuration name"
    )
    description: Optional[str] = Field(None, max_length=500)
    check_type: CheckType = CheckType.FULL
    verify_data: bool = False
    repair_mode: bool = False
    save_space: bool = False
    max_duration: Optional[int] = Field(
        None, gt=0, description="Max duration in seconds"
    )
    archive_prefix: Optional[str] = Field(None, max_length=255)
    archive_glob: Optional[str] = Field(None, max_length=255)
    first_n_archives: Optional[int] = Field(None, gt=0)
    last_n_archives: Optional[int] = Field(None, gt=0)

    @field_validator("max_duration", mode="before")
    @classmethod
    def validate_max_duration(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v is None:
            return None
        return int(v)

    @field_validator("first_n_archives", mode="before")
    @classmethod
    def validate_first_n_archives(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v is None:
            return None
        return int(v)

    @field_validator("last_n_archives", mode="before")
    @classmethod
    def validate_last_n_archives(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v is None:
            return None
        return int(v)

    @model_validator(mode="after")
    def validate_check_constraints(self) -> "RepositoryCheckConfigBase":
        """Validate check configuration constraints"""
        # Can't use verify_data with repository_only
        if self.check_type == CheckType.REPOSITORY_ONLY and self.verify_data:
            raise ValueError("Cannot use verify_data with repository_only checks")

        # Can't use repair mode with max_duration (partial checks)
        if self.max_duration is not None and self.repair_mode:
            raise ValueError(
                "Cannot use repair mode with partial checks (max_duration)"
            )

        # Max duration requires repository_only
        if (
            self.max_duration is not None
            and self.check_type != CheckType.REPOSITORY_ONLY
        ):
            raise ValueError(
                "max_duration can only be used with repository_only checks"
            )

        # Archive filters only make sense with archive checks
        if self.check_type == CheckType.REPOSITORY_ONLY:
            if (
                self.archive_prefix
                or self.archive_glob
                or self.first_n_archives
                or self.last_n_archives
            ):
                raise ValueError(
                    "Archive filters cannot be used with repository_only checks"
                )

        # Can't specify both first_n and last_n
        if self.first_n_archives is not None and self.last_n_archives is not None:
            raise ValueError("Cannot specify both first_n_archives and last_n_archives")

        return self


class RepositoryCheckConfigCreate(RepositoryCheckConfigBase):
    pass


class RepositoryCheckConfigUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = Field(None, max_length=500)
    check_type: Optional[CheckType] = None
    verify_data: Optional[bool] = None
    repair_mode: Optional[bool] = None
    save_space: Optional[bool] = None
    max_duration: Optional[int] = Field(None, gt=0)
    archive_prefix: Optional[str] = Field(None, max_length=255)
    archive_glob: Optional[str] = Field(None, max_length=255)
    first_n_archives: Optional[int] = Field(None, gt=0)
    last_n_archives: Optional[int] = Field(None, gt=0)
    enabled: Optional[bool] = None


class RepositoryCheckConfig(RepositoryCheckConfigBase):
    id: int = Field(gt=0)
    enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "str_strip_whitespace": True,
        "validate_assignment": True,
        "extra": "forbid",
    }


class PruneRequest(BaseModel):
    repository_id: int = Field(gt=0)
    strategy: PruneStrategy = PruneStrategy.SIMPLE
    # Simple strategy
    keep_within_days: Optional[int] = Field(None, gt=0)
    # Advanced strategy
    keep_secondly: Optional[int] = Field(None, ge=0)
    keep_minutely: Optional[int] = Field(None, ge=0)
    keep_hourly: Optional[int] = Field(None, ge=0)
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

    @field_validator("dry_run", mode="before")
    @classmethod
    def validate_dry_run(cls, v: Union[str, bool, int]) -> bool:
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)


class CloudSyncTestRequest(BaseModel):
    config_id: int = Field(gt=0, description="Cloud sync configuration ID to test")


class CheckRequest(BaseModel):
    repository_id: int = Field(gt=0)
    check_config_id: Optional[int] = Field(
        None, gt=0, description="Use existing check policy, or None for custom check"
    )

    # Custom check parameters (used when check_config_id is None)
    check_type: Optional[CheckType] = CheckType.FULL
    verify_data: bool = False
    repair_mode: bool = False
    save_space: bool = False
    max_duration: Optional[int] = Field(
        None, gt=0, description="Max duration in seconds"
    )
    archive_prefix: Optional[str] = Field(None, max_length=255)
    archive_glob: Optional[str] = Field(None, max_length=255)
    first_n_archives: Optional[int] = Field(None, gt=0)
    last_n_archives: Optional[int] = Field(None, gt=0)

    @field_validator("check_config_id", mode="before")
    @classmethod
    def validate_check_config_id(cls, v: Union[str, int, None]) -> Optional[int]:
        if v == "" or v == "none":
            return None
        if v is None:
            return None
        return int(v)

    @model_validator(mode="after")
    def validate_check_request(self) -> "CheckRequest":
        """Validate check request constraints"""
        # If using a policy, don't allow custom parameters
        if self.check_config_id is not None:
            custom_params = [
                self.check_type != CheckType.FULL,
                self.verify_data,
                self.repair_mode,
                self.save_space,
                self.max_duration is not None,
                self.archive_prefix is not None,
                self.archive_glob is not None,
                self.first_n_archives is not None,
                self.last_n_archives is not None,
            ]
            if any(custom_params):
                raise ValueError(
                    "Cannot specify custom check parameters when using a check policy"
                )

        # Validate custom parameters when not using a policy
        if self.check_config_id is None:
            # Can't use verify_data with repository_only
            if self.check_type == CheckType.REPOSITORY_ONLY and self.verify_data:
                raise ValueError("Cannot use verify_data with repository_only checks")

            # Can't use repair mode with max_duration (partial checks)
            if self.max_duration is not None and self.repair_mode:
                raise ValueError(
                    "Cannot use repair mode with partial checks (max_duration)"
                )

            # Max duration requires repository_only
            if (
                self.max_duration is not None
                and self.check_type != CheckType.REPOSITORY_ONLY
            ):
                raise ValueError(
                    "max_duration can only be used with repository_only checks"
                )

            # Archive filters only make sense with archive checks
            if self.check_type == CheckType.REPOSITORY_ONLY:
                if (
                    self.archive_prefix
                    or self.archive_glob
                    or self.first_n_archives
                    or self.last_n_archives
                ):
                    raise ValueError(
                        "Archive filters cannot be used with repository_only checks"
                    )

            # Can't specify both first_n and last_n
            if self.first_n_archives is not None and self.last_n_archives is not None:
                raise ValueError(
                    "Cannot specify both first_n_archives and last_n_archives"
                )

        return self
