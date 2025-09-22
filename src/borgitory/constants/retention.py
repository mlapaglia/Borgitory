"""
Retention field constants and utilities for consolidating duplicate retention handling patterns.

This module provides centralized definitions and utilities for handling Borg retention fields
across the codebase, eliminating the need for repetitive if/elif blocks in multiple services.
"""

from typing import Dict, List, Optional, Union, Protocol, runtime_checkable
from dataclasses import dataclass


# Ordered list of retention fields (from most frequent to least frequent)
RETENTION_FIELDS = [
    "secondly",
    "minutely",
    "hourly",
    "daily",
    "weekly",
    "monthly",
    "yearly",
]

# Mapping of retention fields to their borg command line arguments
RETENTION_FIELD_MAPPING = {
    "secondly": "--keep-secondly",
    "minutely": "--keep-minutely",
    "hourly": "--keep-hourly",
    "daily": "--keep-daily",
    "weekly": "--keep-weekly",
    "monthly": "--keep-monthly",
    "yearly": "--keep-yearly",
}

# Default values for retention fields (used in forms and templates)
DEFAULT_RETENTION_VALUES = {
    "secondly": 0,
    "minutely": 0,
    "hourly": 0,
    "daily": 7,
    "weekly": 4,
    "monthly": 6,
    "yearly": 2,
}

# Human-readable labels for retention fields
RETENTION_FIELD_LABELS = {
    "secondly": "secondly",
    "minutely": "minutely",
    "hourly": "hourly",
    "daily": "daily",
    "weekly": "weekly",
    "monthly": "monthly",
    "yearly": "yearly",
}


@runtime_checkable
class RetentionConfigProtocol(Protocol):
    """Protocol for objects that contain retention configuration fields."""

    keep_secondly: Optional[int]
    keep_minutely: Optional[int]
    keep_hourly: Optional[int]
    keep_daily: Optional[int]
    keep_weekly: Optional[int]
    keep_monthly: Optional[int]
    keep_yearly: Optional[int]


@runtime_checkable
class RetentionConfigWithKeepWithinProtocol(RetentionConfigProtocol, Protocol):
    """Protocol for objects that contain retention fields plus keep_within."""

    keep_within: Optional[str]


RetentionDict = Dict[str, Optional[Union[int, str]]]


@dataclass
class RetentionPolicy:
    """Data class representing a complete retention policy"""

    secondly: Optional[int] = None
    minutely: Optional[int] = None
    hourly: Optional[int] = None
    daily: Optional[int] = None
    weekly: Optional[int] = None
    monthly: Optional[int] = None
    yearly: Optional[int] = None

    def to_dict(self) -> Dict[str, Optional[int]]:
        """Convert to dictionary format"""
        return {
            "secondly": self.secondly,
            "minutely": self.minutely,
            "hourly": self.hourly,
            "daily": self.daily,
            "weekly": self.weekly,
            "monthly": self.monthly,
            "yearly": self.yearly,
        }

    def get_active_fields(self) -> Dict[str, int]:
        """Get only the retention fields that have non-None, non-zero values"""
        return {
            field: value
            for field, value in self.to_dict().items()
            if value is not None and value > 0
        }


class RetentionFieldHandler:
    """Utility class for handling retention fields across the codebase"""

    @staticmethod
    def build_borg_args(
        config_or_params: Union[RetentionConfigWithKeepWithinProtocol, RetentionDict],
        include_keep_within: bool = True,
    ) -> List[str]:
        """
        Build borg retention arguments from config object or parameters dictionary.

        Args:
            config_or_params: Object with retention fields (keep_daily, keep_weekly, etc.) or dict
            include_keep_within: Whether to include --keep-within if present

        Returns:
            List of borg command arguments
        """
        args = []

        if include_keep_within:
            keep_within = None
            if hasattr(config_or_params, "keep_within"):
                keep_within = getattr(config_or_params, "keep_within", None)
            elif isinstance(config_or_params, dict):
                keep_within = config_or_params.get("keep_within")

            if keep_within:
                args.extend(["--keep-within", str(keep_within)])

        for field in RETENTION_FIELDS:
            value = None

            if hasattr(config_or_params, f"keep_{field}"):
                value = getattr(config_or_params, f"keep_{field}", None)
            elif isinstance(config_or_params, dict):
                value = config_or_params.get(f"keep_{field}")

            if value is not None:
                try:
                    int_value = int(value) if isinstance(value, (str, int)) else None
                    if int_value is not None and int_value > 0:
                        args.extend([RETENTION_FIELD_MAPPING[field], str(int_value)])
                except (ValueError, TypeError):
                    continue

        return args

    @staticmethod
    def build_borg_args_explicit(
        *,
        keep_within: Optional[str] = None,
        keep_secondly: Optional[int] = None,
        keep_minutely: Optional[int] = None,
        keep_hourly: Optional[int] = None,
        keep_daily: Optional[int] = None,
        keep_weekly: Optional[int] = None,
        keep_monthly: Optional[int] = None,
        keep_yearly: Optional[int] = None,
        include_keep_within: bool = True,
    ) -> List[str]:
        """
        Build borg retention arguments from explicit parameters (type-safe alternative).

        Args:
            keep_within: Keep archives within this time range
            keep_secondly: Number of secondly archives to keep
            keep_minutely: Number of minutely archives to keep
            keep_hourly: Number of hourly archives to keep
            keep_daily: Number of daily archives to keep
            keep_weekly: Number of weekly archives to keep
            keep_monthly: Number of monthly archives to keep
            keep_yearly: Number of yearly archives to keep
            include_keep_within: Whether to include --keep-within if present

        Returns:
            List of borg command arguments
        """
        args = []

        if include_keep_within and keep_within:
            args.extend(["--keep-within", keep_within])

        retention_values = {
            "secondly": keep_secondly,
            "minutely": keep_minutely,
            "hourly": keep_hourly,
            "daily": keep_daily,
            "weekly": keep_weekly,
            "monthly": keep_monthly,
            "yearly": keep_yearly,
        }

        for field, value in retention_values.items():
            if value is not None and value > 0:
                args.extend([RETENTION_FIELD_MAPPING[field], str(value)])

        return args

    @staticmethod
    def copy_fields(
        source: RetentionConfigProtocol, target: RetentionConfigProtocol
    ) -> None:
        """
        Copy retention fields from source to target object.

        Args:
            source: Object to copy retention fields from
            target: Object to copy retention fields to
        """
        for field in RETENTION_FIELDS:
            source_attr = f"keep_{field}"
            if hasattr(source, source_attr):
                setattr(target, source_attr, getattr(source, source_attr))

    @staticmethod
    def to_dict(
        config: RetentionConfigProtocol, prefix: str = "keep_"
    ) -> Dict[str, Optional[int]]:
        """
        Convert config object to retention dictionary.

        Args:
            config: Object with retention fields
            prefix: Prefix for field names (default: 'keep_')

        Returns:
            Dictionary with retention field values
        """
        result = {}
        for field in RETENTION_FIELDS:
            attr_name = f"{prefix}{field}"
            result[f"{prefix}{field}"] = getattr(config, attr_name, None)
        return result

    @staticmethod
    def build_description(config: RetentionConfigProtocol) -> str:
        """
        Build human-readable description of retention policy.

        Args:
            config: Object with retention fields

        Returns:
            Human-readable description string
        """
        parts = []
        for field in RETENTION_FIELDS:
            value = getattr(config, f"keep_{field}", None)
            if value is not None and value > 0:
                label = RETENTION_FIELD_LABELS[field]
                parts.append(f"{value} {label}")

        return ", ".join(parts) if parts else "No retention rules"

    @staticmethod
    def extract_from_params(params: RetentionDict) -> Dict[str, Optional[int]]:
        """
        Extract retention fields from a parameters dictionary.

        Args:
            params: Dictionary that may contain retention parameters

        Returns:
            Dictionary with retention field values
        """
        result = {}
        for field in RETENTION_FIELDS:
            key = f"keep_{field}"
            value = params.get(key)
            if value is not None:
                try:
                    result[key] = int(value) if value else None
                except (ValueError, TypeError):
                    result[key] = None
            else:
                result[key] = None
        return result

    @staticmethod
    def create_policy_from_config(config: RetentionConfigProtocol) -> RetentionPolicy:
        """
        Create a RetentionPolicy from any config object.

        Args:
            config: Object with retention fields

        Returns:
            RetentionPolicy instance
        """
        return RetentionPolicy(
            secondly=getattr(config, "keep_secondly", None),
            minutely=getattr(config, "keep_minutely", None),
            hourly=getattr(config, "keep_hourly", None),
            daily=getattr(config, "keep_daily", None),
            weekly=getattr(config, "keep_weekly", None),
            monthly=getattr(config, "keep_monthly", None),
            yearly=getattr(config, "keep_yearly", None),
        )


def get_retention_field_names(with_prefix: bool = True) -> List[str]:
    """
    Get list of retention field names.

    Args:
        with_prefix: Whether to include 'keep_' prefix

    Returns:
        List of field names
    """
    if with_prefix:
        return [f"keep_{field}" for field in RETENTION_FIELDS]
    return RETENTION_FIELDS.copy()


def validate_retention_values(
    retention_values: RetentionDict,
) -> Dict[str, Optional[int]]:
    """
    Validate and normalize retention field values from a dictionary.

    Args:
        retention_values: Dictionary with retention field values (keep_daily=7, keep_weekly=4, etc.)

    Returns:
        Dictionary with validated retention values

    Raises:
        ValueError: If any retention value is invalid
    """
    result: Dict[str, Optional[int]] = {}
    for field in RETENTION_FIELDS:
        key = f"keep_{field}"
        value = retention_values.get(key)

        if value is None:
            result[key] = None
        elif isinstance(value, (int, str)):
            try:
                int_value = int(value)
                if int_value < 0:
                    raise ValueError(f"{key} must be non-negative, got {int_value}")
                result[key] = int_value if int_value > 0 else None
            except ValueError as e:
                raise ValueError(f"Invalid value for {key}: {value}") from e
        else:
            raise ValueError(f"Invalid type for {key}: {type(value)}")

    return result


def validate_retention_values_explicit(
    *,
    keep_secondly: Optional[Union[int, str]] = None,
    keep_minutely: Optional[Union[int, str]] = None,
    keep_hourly: Optional[Union[int, str]] = None,
    keep_daily: Optional[Union[int, str]] = None,
    keep_weekly: Optional[Union[int, str]] = None,
    keep_monthly: Optional[Union[int, str]] = None,
    keep_yearly: Optional[Union[int, str]] = None,
) -> Dict[str, Optional[int]]:
    """
    Validate and normalize retention field values with explicit parameters (type-safe).

    Args:
        keep_secondly: Number of secondly archives to keep
        keep_minutely: Number of minutely archives to keep
        keep_hourly: Number of hourly archives to keep
        keep_daily: Number of daily archives to keep
        keep_weekly: Number of weekly archives to keep
        keep_monthly: Number of monthly archives to keep
        keep_yearly: Number of yearly archives to keep

    Returns:
        Dictionary with validated retention values

    Raises:
        ValueError: If any retention value is invalid
    """
    values = {
        "keep_secondly": keep_secondly,
        "keep_minutely": keep_minutely,
        "keep_hourly": keep_hourly,
        "keep_daily": keep_daily,
        "keep_weekly": keep_weekly,
        "keep_monthly": keep_monthly,
        "keep_yearly": keep_yearly,
    }

    return validate_retention_values(values)
