"""
Tests for NotificationConfigService - Business logic tests
"""

import pytest
from sqlalchemy.orm import Session
from borgitory.services.notifications.notification_config_service import (
    NotificationConfigService,
)
from borgitory.models.database import NotificationConfig


@pytest.fixture
def service(test_db: Session):
    """NotificationConfigService instance with real database session."""
    return NotificationConfigService(test_db)


@pytest.fixture
def sample_config(test_db: Session):
    """Create a sample notification config for testing."""
    config = NotificationConfig(
        name="test-config",
        provider="pushover",
        notify_on_success=True,
        notify_on_failure=False,
        enabled=True,
    )
    config.set_pushover_credentials("test-user", "test-token")
    test_db.add(config)
    test_db.commit()
    test_db.refresh(config)
    return config


class TestNotificationConfigService:
    """Test class for NotificationConfigService business logic."""

    def test_get_all_configs_empty(self, service) -> None:
        """Test getting configs when none exist."""
        result = service.get_all_configs()
        assert result == []

    def test_get_all_configs_with_data(self, service, test_db: Session) -> None:
        """Test getting configs with data."""
        config1 = NotificationConfig(
            name="config-1",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=False,
            enabled=True,
        )
        config1.set_pushover_credentials("user1", "token1")

        config2 = NotificationConfig(
            name="config-2",
            provider="pushover",
            notify_on_success=False,
            notify_on_failure=True,
            enabled=False,
        )
        config2.set_pushover_credentials("user2", "token2")

        test_db.add(config1)
        test_db.add(config2)
        test_db.commit()

        result = service.get_all_configs()
        assert len(result) == 2
        names = [c.name for c in result]
        assert "config-1" in names
        assert "config-2" in names

    def test_get_all_configs_pagination(self, service, test_db: Session) -> None:
        """Test getting configs with pagination."""
        for i in range(5):
            config = NotificationConfig(
                name=f"config-{i}",
                provider="pushover",
                notify_on_success=True,
                notify_on_failure=False,
                enabled=True,
            )
            config.set_pushover_credentials(f"user{i}", f"token{i}")
            test_db.add(config)
        test_db.commit()

        result = service.get_all_configs(skip=2, limit=2)
        assert len(result) == 2

    def test_get_config_by_id_success(self, service, sample_config) -> None:
        """Test getting config by ID successfully."""
        result = service.get_config_by_id(sample_config.id)
        assert result is not None
        assert result.name == "test-config"
        assert result.id == sample_config.id

    def test_get_config_by_id_not_found(self, service) -> None:
        """Test getting non-existent config by ID."""
        result = service.get_config_by_id(999)
        assert result is None

    def test_create_config_success(self, service, test_db: Session) -> None:
        """Test successful config creation."""
        success, config, error = service.create_config(
            name="new-config",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=False,
            user_key="new-user",
            app_token="new-token",
        )

        assert success is True
        assert error is None
        assert config.name == "new-config"
        assert config.provider == "pushover"
        assert config.notify_on_success is True
        assert config.notify_on_failure is False
        assert config.enabled is True  # Default value

        # Verify saved to database
        saved_config = (
            test_db.query(NotificationConfig)
            .filter(NotificationConfig.name == "new-config")
            .first()
        )
        assert saved_config is not None
        assert saved_config.provider == "pushover"

        # Verify credentials were set
        user_key, app_token = saved_config.get_pushover_credentials()
        assert user_key == "new-user"
        assert app_token == "new-token"

    def test_create_config_database_error(self, service, test_db: Session) -> None:
        """Test config creation with database error."""
        from unittest.mock import patch

        # Mock the database commit to raise an exception
        with patch.object(test_db, "commit", side_effect=Exception("Database error")):
            success, config, error = service.create_config(
                name="error-config",
                provider="pushover",
                notify_on_success=True,
                notify_on_failure=False,
                user_key="user",
                app_token="token",
            )

            assert success is False
            assert config is None
            assert "Failed to create notification configuration" in error

    def test_update_config_success(self, service, test_db, sample_config) -> None:
        """Test successful config update."""
        success, updated_config, error = service.update_config(
            config_id=sample_config.id,
            name="updated-config",
            provider="pushover",
            notify_on_success=False,
            notify_on_failure=True,
            user_key="updated-user",
            app_token="updated-token",
        )

        assert success is True
        assert error is None
        assert updated_config.name == "updated-config"
        assert updated_config.notify_on_success is False
        assert updated_config.notify_on_failure is True

        # Verify credentials were updated
        user_key, app_token = updated_config.get_pushover_credentials()
        assert user_key == "updated-user"
        assert app_token == "updated-token"

    def test_update_config_not_found(self, service) -> None:
        """Test updating non-existent config."""
        success, config, error = service.update_config(
            config_id=999,
            name="not-found",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=False,
            user_key="user",
            app_token="token",
        )

        assert success is False
        assert config is None
        assert "not found" in error

    def test_enable_config_success(self, service, test_db: Session) -> None:
        """Test successful config enabling."""
        # Create disabled config
        config = NotificationConfig(
            name="disabled-config",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=False,
            enabled=False,
        )
        config.set_pushover_credentials("user", "token")
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        success, success_msg, error = service.enable_config(config.id)

        assert success is True
        assert error is None
        assert "enabled successfully" in success_msg
        assert config.name in success_msg

        # Verify in database
        test_db.refresh(config)
        assert config.enabled is True

    def test_enable_config_not_found(self, service) -> None:
        """Test enabling non-existent config."""
        success, success_msg, error = service.enable_config(999)

        assert success is False
        assert success_msg is None
        assert "not found" in error

    def test_disable_config_success(self, service, test_db: Session) -> None:
        """Test successful config disabling."""
        # Create enabled config
        config = NotificationConfig(
            name="enabled-config",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=False,
            enabled=True,
        )
        config.set_pushover_credentials("user", "token")
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        success, success_msg, error = service.disable_config(config.id)

        assert success is True
        assert error is None
        assert "disabled successfully" in success_msg
        assert config.name in success_msg

        # Verify in database
        test_db.refresh(config)
        assert config.enabled is False

    def test_disable_config_not_found(self, service) -> None:
        """Test disabling non-existent config."""
        success, success_msg, error = service.disable_config(999)

        assert success is False
        assert success_msg is None
        assert "not found" in error

    def test_delete_config_success(self, service, test_db, sample_config) -> None:
        """Test successful config deletion."""
        config_id = sample_config.id
        config_name = sample_config.name

        success, returned_name, error = service.delete_config(config_id)

        assert success is True
        assert returned_name == config_name
        assert error is None

        # Verify removed from database
        deleted_config = (
            test_db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )
        assert deleted_config is None

    def test_delete_config_not_found(self, service) -> None:
        """Test deleting non-existent config."""
        success, name, error = service.delete_config(999)

        assert success is False
        assert name is None
        assert "not found" in error

    def test_get_configs_with_descriptions_success(
        self, service, test_db: Session
    ) -> None:
        """Test getting configs with computed descriptions."""
        # Config that notifies on both success and failure
        config1 = NotificationConfig(
            name="both-notifications",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=True,
            enabled=True,
        )
        config1.set_pushover_credentials("user1", "token1")

        # Config that only notifies on failure
        config2 = NotificationConfig(
            name="failure-only",
            provider="pushover",
            notify_on_success=False,
            notify_on_failure=True,
            enabled=True,
        )
        config2.set_pushover_credentials("user2", "token2")

        # Config that doesn't notify on anything
        config3 = NotificationConfig(
            name="no-notifications",
            provider="pushover",
            notify_on_success=False,
            notify_on_failure=False,
            enabled=True,
        )
        config3.set_pushover_credentials("user3", "token3")

        test_db.add_all([config1, config2, config3])
        test_db.commit()

        result = service.get_configs_with_descriptions()

        assert len(result) == 3

        # Find each config and check descriptions
        both_config = next(c for c in result if c["name"] == "both-notifications")
        assert both_config["notification_desc"] == "Success, Failures"

        failure_config = next(c for c in result if c["name"] == "failure-only")
        assert failure_config["notification_desc"] == "Failures"

        none_config = next(c for c in result if c["name"] == "no-notifications")
        assert none_config["notification_desc"] == "No notifications"

    def test_get_configs_with_descriptions_empty(self, service) -> None:
        """Test getting config descriptions when database is empty."""
        result = service.get_configs_with_descriptions()
        assert result == []

    def test_get_config_credentials_success(self, service, sample_config) -> None:
        """Test getting config credentials successfully."""
        success, user_key, app_token, error = service.get_config_credentials(
            sample_config.id
        )

        assert success is True
        assert user_key == "test-user"
        assert app_token == "test-token"
        assert error is None

    def test_get_config_credentials_not_found(self, service) -> None:
        """Test getting credentials for non-existent config."""
        success, user_key, app_token, error = service.get_config_credentials(999)

        assert success is False
        assert user_key is None
        assert app_token is None
        assert "not found" in error

    def test_get_config_credentials_unsupported_provider(
        self, service, test_db: Session
    ) -> None:
        """Test getting credentials for unsupported provider."""
        # Create config with unsupported provider (shouldn't happen normally)
        config = NotificationConfig(
            name="unsupported-config",
            provider="unsupported",
            notify_on_success=True,
            notify_on_failure=False,
            enabled=True,
        )
        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        success, user_key, app_token, error = service.get_config_credentials(config.id)

        assert success is False
        assert user_key is None
        assert app_token is None
        assert "Unsupported notification provider" in error

    def test_config_lifecycle(self, service, test_db: Session) -> None:
        """Test complete config lifecycle: create, update, enable/disable, delete."""
        # Create
        success, created_config, error = service.create_config(
            name="lifecycle-test",
            provider="pushover",
            notify_on_success=True,
            notify_on_failure=False,
            user_key="lifecycle-user",
            app_token="lifecycle-token",
        )
        assert success is True
        config_id = created_config.id

        # Update
        success, updated_config, error = service.update_config(
            config_id=config_id,
            name="updated-lifecycle-test",
            provider="pushover",
            notify_on_success=False,
            notify_on_failure=True,
            user_key="updated-user",
            app_token="updated-token",
        )
        assert success is True
        assert updated_config.name == "updated-lifecycle-test"
        assert updated_config.notify_on_success is False
        assert updated_config.notify_on_failure is True

        # Disable
        success, success_msg, error = service.disable_config(config_id)
        assert success is True

        # Enable
        success, success_msg, error = service.enable_config(config_id)
        assert success is True

        # Get credentials
        success, user_key, app_token, error = service.get_config_credentials(config_id)
        assert success is True
        assert user_key == "updated-user"
        assert app_token == "updated-token"

        # Delete
        success, config_name, error = service.delete_config(config_id)
        assert success is True
        assert config_name == "updated-lifecycle-test"

        # Verify completely removed
        deleted_config = (
            test_db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )
        assert deleted_config is None
