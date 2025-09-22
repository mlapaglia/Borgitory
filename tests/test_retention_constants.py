"""Tests for retention constants and utilities."""

import pytest
from dataclasses import dataclass
from typing import Optional
from unittest.mock import Mock

from borgitory.constants.retention import (
    RETENTION_FIELDS,
    RETENTION_FIELD_MAPPING,
    DEFAULT_RETENTION_VALUES,
    RETENTION_FIELD_LABELS,
    RetentionConfigProtocol,
    RetentionConfigWithKeepWithinProtocol,
    RetentionPolicy,
    RetentionFieldHandler,
    get_retention_field_names,
    validate_retention_values,
    validate_retention_values_explicit,
)


@dataclass
class MockRetentionConfig:
    """Mock retention config for testing"""

    keep_secondly: Optional[int] = None
    keep_minutely: Optional[int] = None
    keep_hourly: Optional[int] = None
    keep_daily: Optional[int] = 7
    keep_weekly: Optional[int] = 4
    keep_monthly: Optional[int] = 6
    keep_yearly: Optional[int] = 2


@dataclass
class MockRetentionConfigWithKeepWithin:
    """Mock retention config with keep_within for testing"""

    keep_within: Optional[str] = "7d"
    keep_secondly: Optional[int] = None
    keep_minutely: Optional[int] = None
    keep_hourly: Optional[int] = None
    keep_daily: Optional[int] = 7
    keep_weekly: Optional[int] = 4
    keep_monthly: Optional[int] = 6
    keep_yearly: Optional[int] = 2


class TestRetentionConstants:
    """Test retention constant definitions"""

    def test_retention_fields_order(self):
        """Test that retention fields are in expected order"""
        expected = [
            "secondly",
            "minutely",
            "hourly",
            "daily",
            "weekly",
            "monthly",
            "yearly",
        ]
        assert RETENTION_FIELDS == expected

    def test_retention_field_mapping_completeness(self):
        """Test that mapping covers all retention fields"""
        for field in RETENTION_FIELDS:
            assert field in RETENTION_FIELD_MAPPING
            assert RETENTION_FIELD_MAPPING[field] == f"--keep-{field}"

    def test_default_retention_values_completeness(self):
        """Test that defaults cover all retention fields"""
        for field in RETENTION_FIELDS:
            assert field in DEFAULT_RETENTION_VALUES
            assert isinstance(DEFAULT_RETENTION_VALUES[field], int)
            assert DEFAULT_RETENTION_VALUES[field] >= 0

    def test_retention_field_labels_completeness(self):
        """Test that labels cover all retention fields"""
        for field in RETENTION_FIELDS:
            assert field in RETENTION_FIELD_LABELS
            assert RETENTION_FIELD_LABELS[field] == field


class TestRetentionPolicy:
    """Test RetentionPolicy dataclass"""

    def test_default_initialization(self):
        """Test default initialization"""
        policy = RetentionPolicy()
        assert policy.secondly is None
        assert policy.minutely is None
        assert policy.hourly is None
        assert policy.daily is None
        assert policy.weekly is None
        assert policy.monthly is None
        assert policy.yearly is None

    def test_explicit_initialization(self):
        """Test explicit initialization"""
        policy = RetentionPolicy(daily=7, weekly=4, monthly=6, yearly=2)
        assert policy.daily == 7
        assert policy.weekly == 4
        assert policy.monthly == 6
        assert policy.yearly == 2
        assert policy.secondly is None
        assert policy.minutely is None
        assert policy.hourly is None

    def test_to_dict(self):
        """Test conversion to dictionary"""
        policy = RetentionPolicy(daily=7, weekly=4)
        result = policy.to_dict()

        expected = {
            "secondly": None,
            "minutely": None,
            "hourly": None,
            "daily": 7,
            "weekly": 4,
            "monthly": None,
            "yearly": None,
        }
        assert result == expected

    def test_get_active_fields(self):
        """Test getting only active (non-None, non-zero) fields"""
        policy = RetentionPolicy(
            secondly=0,  # Should be excluded (zero)
            daily=7,
            weekly=4,
            monthly=None,  # Should be excluded (None)
            yearly=2,
        )

        result = policy.get_active_fields()
        expected = {"daily": 7, "weekly": 4, "yearly": 2}
        assert result == expected

    def test_get_active_fields_empty(self):
        """Test getting active fields when all are None or zero"""
        policy = RetentionPolicy(daily=0, weekly=None)
        result = policy.get_active_fields()
        assert result == {}


class TestRetentionFieldHandler:
    """Test RetentionFieldHandler utility methods"""

    def test_build_borg_args_from_config_object(self):
        """Test building borg args from config object"""
        config = MockRetentionConfig(keep_daily=7, keep_weekly=4, keep_monthly=6)

        args = RetentionFieldHandler.build_borg_args(config, include_keep_within=False)

        expected = [
            "--keep-daily",
            "7",
            "--keep-weekly",
            "4",
            "--keep-monthly",
            "6",
            "--keep-yearly",
            "2",
        ]
        assert args == expected

    def test_build_borg_args_from_dict(self):
        """Test building borg args from dictionary"""
        params = {
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": 6,
            "keep_yearly": None,  # Should be excluded
        }

        args = RetentionFieldHandler.build_borg_args(params, include_keep_within=False)

        expected = ["--keep-daily", "7", "--keep-weekly", "4", "--keep-monthly", "6"]
        assert args == expected

    def test_build_borg_args_with_keep_within(self):
        """Test building borg args with keep_within"""
        config = MockRetentionConfigWithKeepWithin(keep_within="14d", keep_daily=7)

        args = RetentionFieldHandler.build_borg_args(config, include_keep_within=True)

        assert "--keep-within" in args
        assert "14d" in args
        assert "--keep-daily" in args
        assert "7" in args

    def test_build_borg_args_skip_keep_within(self):
        """Test building borg args without keep_within"""
        config = MockRetentionConfigWithKeepWithin(keep_within="14d", keep_daily=7)

        args = RetentionFieldHandler.build_borg_args(config, include_keep_within=False)

        assert "--keep-within" not in args
        assert "14d" not in args
        assert "--keep-daily" in args
        assert "7" in args

    def test_build_borg_args_handles_string_values(self):
        """Test that string values are converted to integers"""
        params = {"keep_daily": "7", "keep_weekly": "4"}

        args = RetentionFieldHandler.build_borg_args(params, include_keep_within=False)

        expected = ["--keep-daily", "7", "--keep-weekly", "4"]
        assert args == expected

    def test_build_borg_args_skips_invalid_values(self):
        """Test that invalid values are skipped"""
        params = {
            "keep_daily": "invalid",
            "keep_weekly": 4,
            "keep_monthly": -1,  # Negative should be skipped
        }

        args = RetentionFieldHandler.build_borg_args(params, include_keep_within=False)

        expected = ["--keep-weekly", "4"]
        assert args == expected

    def test_build_borg_args_skips_zero_values(self):
        """Test that zero values are skipped"""
        params = {"keep_daily": 0, "keep_weekly": 4}

        args = RetentionFieldHandler.build_borg_args(params, include_keep_within=False)

        expected = ["--keep-weekly", "4"]
        assert args == expected

    def test_build_borg_args_explicit(self):
        """Test explicit parameter method"""
        args = RetentionFieldHandler.build_borg_args_explicit(
            keep_within="7d",
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            include_keep_within=True,
        )

        expected = [
            "--keep-within",
            "7d",
            "--keep-daily",
            "7",
            "--keep-weekly",
            "4",
            "--keep-monthly",
            "6",
        ]
        assert args == expected

    def test_build_borg_args_explicit_skip_keep_within(self):
        """Test explicit method without keep_within"""
        args = RetentionFieldHandler.build_borg_args_explicit(
            keep_within="7d", keep_daily=7, include_keep_within=False
        )

        expected = ["--keep-daily", "7"]
        assert args == expected

    def test_build_borg_args_explicit_skip_none_and_zero(self):
        """Test explicit method skips None and zero values"""
        args = RetentionFieldHandler.build_borg_args_explicit(
            keep_daily=7,
            keep_weekly=0,  # Should be skipped
            keep_monthly=None,  # Should be skipped
            keep_yearly=2,
        )

        expected = ["--keep-daily", "7", "--keep-yearly", "2"]
        assert args == expected

    def test_copy_fields(self):
        """Test copying retention fields between objects"""
        source = MockRetentionConfig(keep_daily=10, keep_weekly=5, keep_monthly=12)
        target = MockRetentionConfig()

        RetentionFieldHandler.copy_fields(source, target)

        assert target.keep_daily == 10
        assert target.keep_weekly == 5
        assert target.keep_monthly == 12
        assert target.keep_yearly == 2  # Original value preserved

    def test_to_dict(self):
        """Test converting config to dictionary"""
        config = MockRetentionConfig(keep_daily=7, keep_weekly=4)

        result = RetentionFieldHandler.to_dict(config)

        expected = {
            "keep_secondly": None,
            "keep_minutely": None,
            "keep_hourly": None,
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": 6,
            "keep_yearly": 2,
        }
        assert result == expected

    def test_to_dict_with_custom_prefix(self):
        """Test converting config to dictionary with custom prefix"""
        # Create a mock object with custom prefix
        mock_obj = Mock()
        mock_obj.retain_daily = 7
        mock_obj.retain_weekly = 4

        # Mock the getattr calls for all fields
        def mock_getattr(obj, attr, default=None):
            if attr == "retain_daily":
                return 7
            elif attr == "retain_weekly":
                return 4
            else:
                return default

        # Temporarily replace getattr for this test
        import builtins

        original_getattr = builtins.getattr
        builtins.getattr = mock_getattr

        try:
            result = RetentionFieldHandler.to_dict(mock_obj, prefix="retain_")
            expected = {
                "retain_secondly": None,
                "retain_minutely": None,
                "retain_hourly": None,
                "retain_daily": 7,
                "retain_weekly": 4,
                "retain_monthly": None,
                "retain_yearly": None,
            }
            assert result == expected
        finally:
            builtins.getattr = original_getattr

    def test_build_description(self):
        """Test building human-readable description"""
        config = MockRetentionConfig(keep_daily=7, keep_weekly=4, keep_yearly=2)

        result = RetentionFieldHandler.build_description(config)
        assert result == "7 daily, 4 weekly, 6 monthly, 2 yearly"

    def test_build_description_empty(self):
        """Test description when no retention rules are active"""
        config = MockRetentionConfig(
            keep_daily=0, keep_weekly=None, keep_monthly=0, keep_yearly=None
        )

        result = RetentionFieldHandler.build_description(config)
        assert result == "No retention rules"

    def test_extract_from_params(self):
        """Test extracting retention fields from parameters"""
        params = {
            "keep_daily": "7",
            "keep_weekly": 4,
            "keep_monthly": "",  # Empty string should become None
            "keep_yearly": "invalid",  # Invalid should become None
            "other_param": "ignored",
        }

        result = RetentionFieldHandler.extract_from_params(params)

        expected = {
            "keep_secondly": None,
            "keep_minutely": None,
            "keep_hourly": None,
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": None,
            "keep_yearly": None,
        }
        assert result == expected

    def test_create_policy_from_config(self):
        """Test creating RetentionPolicy from config object"""
        config = MockRetentionConfig(keep_daily=7, keep_weekly=4)

        policy = RetentionFieldHandler.create_policy_from_config(config)

        assert isinstance(policy, RetentionPolicy)
        assert policy.daily == 7
        assert policy.weekly == 4
        assert policy.monthly == 6
        assert policy.yearly == 2
        assert policy.secondly is None


class TestRetentionUtilityFunctions:
    """Test standalone utility functions"""

    def test_get_retention_field_names_with_prefix(self):
        """Test getting field names with prefix"""
        result = get_retention_field_names(with_prefix=True)
        expected = [
            "keep_secondly",
            "keep_minutely",
            "keep_hourly",
            "keep_daily",
            "keep_weekly",
            "keep_monthly",
            "keep_yearly",
        ]
        assert result == expected

    def test_get_retention_field_names_without_prefix(self):
        """Test getting field names without prefix"""
        result = get_retention_field_names(with_prefix=False)
        expected = [
            "secondly",
            "minutely",
            "hourly",
            "daily",
            "weekly",
            "monthly",
            "yearly",
        ]
        assert result == expected

    def test_validate_retention_values_valid(self):
        """Test validation with valid values"""
        values = {
            "keep_daily": 7,
            "keep_weekly": "4",  # String should be converted
            "keep_monthly": 0,  # Zero should become None
            "keep_yearly": None,  # None should stay None
        }

        result = validate_retention_values(values)

        expected = {
            "keep_secondly": None,
            "keep_minutely": None,
            "keep_hourly": None,
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": None,
            "keep_yearly": None,
        }
        assert result == expected

    def test_validate_retention_values_negative(self):
        """Test validation rejects negative values"""
        values = {"keep_daily": -1}

        with pytest.raises(ValueError, match="Invalid value for keep_daily"):
            validate_retention_values(values)

    def test_validate_retention_values_invalid_string(self):
        """Test validation rejects invalid string values"""
        values = {"keep_daily": "invalid"}

        with pytest.raises(ValueError, match="Invalid value for keep_daily"):
            validate_retention_values(values)

    def test_validate_retention_values_invalid_type(self):
        """Test validation rejects invalid types"""
        values = {"keep_daily": [1, 2, 3]}

        with pytest.raises(ValueError, match="Invalid type for keep_daily"):
            validate_retention_values(values)

    def test_validate_retention_values_explicit_valid(self):
        """Test explicit validation with valid values"""
        result = validate_retention_values_explicit(
            keep_daily=7, keep_weekly="4", keep_monthly=0, keep_yearly=None
        )

        expected = {
            "keep_secondly": None,
            "keep_minutely": None,
            "keep_hourly": None,
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": None,
            "keep_yearly": None,
        }
        assert result == expected

    def test_validate_retention_values_explicit_invalid(self):
        """Test explicit validation with invalid values"""
        with pytest.raises(ValueError, match="Invalid value for keep_daily"):
            validate_retention_values_explicit(keep_daily=-1)


class TestProtocolCompliance:
    """Test that mock objects comply with protocols"""

    def test_mock_config_implements_retention_config_protocol(self):
        """Test that MockRetentionConfig implements RetentionConfigProtocol"""
        config = MockRetentionConfig()
        assert isinstance(config, RetentionConfigProtocol)

    def test_mock_config_with_keep_within_implements_protocol(self):
        """Test that MockRetentionConfigWithKeepWithin implements extended protocol"""
        config = MockRetentionConfigWithKeepWithin()
        assert isinstance(config, RetentionConfigWithKeepWithinProtocol)

    def test_retention_policy_has_correct_fields(self):
        """Test that RetentionPolicy has the expected retention fields"""
        policy = RetentionPolicy()
        # RetentionPolicy uses field names without keep_ prefix
        assert hasattr(policy, "secondly")
        assert hasattr(policy, "minutely")
        assert hasattr(policy, "hourly")
        assert hasattr(policy, "daily")
        assert hasattr(policy, "weekly")
        assert hasattr(policy, "monthly")
        assert hasattr(policy, "yearly")


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_build_borg_args_empty_config(self):
        """Test building args with empty config"""
        config = MockRetentionConfig(
            keep_daily=None, keep_weekly=None, keep_monthly=None, keep_yearly=None
        )

        args = RetentionFieldHandler.build_borg_args(config, include_keep_within=False)
        assert args == []

    def test_build_borg_args_empty_dict(self):
        """Test building args with empty dictionary"""
        args = RetentionFieldHandler.build_borg_args({}, include_keep_within=False)
        assert args == []

    def test_build_description_single_field(self):
        """Test description with single retention field"""
        config = MockRetentionConfig(
            keep_daily=7, keep_weekly=None, keep_monthly=None, keep_yearly=None
        )

        result = RetentionFieldHandler.build_description(config)
        assert result == "7 daily"

    def test_copy_fields_missing_attributes(self):
        """Test copying fields when source is missing some attributes"""

        # Create a partial source object with only some retention fields
        @dataclass
        class PartialRetentionConfig:
            keep_daily: Optional[int] = 10
            keep_yearly: Optional[int] = 1
            # Missing other keep_* fields

        source = PartialRetentionConfig()
        target = MockRetentionConfig()
        original_weekly = target.keep_weekly

        # Should not raise an error, just copy available attributes
        RetentionFieldHandler.copy_fields(source, target)

        assert target.keep_daily == 10  # Should be copied
        assert target.keep_yearly == 1  # Should be copied
        assert target.keep_weekly == original_weekly  # Should remain original value
