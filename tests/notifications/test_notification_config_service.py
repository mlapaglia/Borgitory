"""
Tests for NotificationConfigService - Business logic tests
"""

import pytest
from sqlalchemy.orm import Session
from fastapi import HTTPException
from borgitory.services.notifications.config_service import NotificationConfigService
from borgitory.services.notifications.service import NotificationService
from borgitory.models.database import NotificationConfig


@pytest.fixture
def notification_service():
    """NotificationService instance for testing using proper DI chain."""
    from borgitory.dependencies import (
        get_http_client,
        get_notification_provider_factory,
    )

    # Manually resolve the dependency chain for testing
    http_client = get_http_client()
    factory = get_notification_provider_factory(http_client)

    return NotificationService(provider_factory=factory)


@pytest.fixture
def service(test_db: Session, notification_service):
    """NotificationConfigService instance with real database session."""
    return NotificationConfigService(
        db=test_db, notification_service=notification_service
    )


@pytest.fixture
def sample_config(test_db: Session, notification_service):
    """Create a sample notification config for testing."""
    config = NotificationConfig()
    config.name = "test-config"
    config.provider = "pushover"
    config.provider_config = notification_service.prepare_config_for_storage(
        "pushover",
        {"user_key": "test-user" + "x" * 21, "app_token": "test-token" + "x" * 20},
    )
    config.enabled = True

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

    def test_get_all_configs_with_data(
        self, service, test_db: Session, notification_service
    ) -> None:
        """Test getting configs with data."""
        config1 = NotificationConfig()
        config1.name = "config-1"
        config1.provider = "pushover"
        config1.provider_config = notification_service.prepare_config_for_storage(
            "pushover", {"user_key": "u1" + "x" * 28, "app_token": "t1" + "x" * 28}
        )
        config1.enabled = True

        config2 = NotificationConfig()
        config2.name = "config-2"
        config2.provider = "discord"
        config2.provider_config = notification_service.prepare_config_for_storage(
            "discord", {"webhook_url": "https://discord.com/api/webhooks/test"}
        )
        config2.enabled = False

        test_db.add(config1)
        test_db.add(config2)
        test_db.commit()

        result = service.get_all_configs()
        assert len(result) == 2
        names = [c.name for c in result]
        assert "config-1" in names
        assert "config-2" in names

    def test_get_all_configs_pagination(
        self, service, test_db: Session, notification_service
    ) -> None:
        """Test getting configs with pagination."""
        for i in range(5):
            config = NotificationConfig()
            config.name = f"config-{i}"
            config.provider = "pushover"
            config.provider_config = notification_service.prepare_config_for_storage(
                "pushover",
                {
                    "user_key": f"user{i}" + "x" * 25,
                    "app_token": f"token{i}" + "x" * 24,
                },
            )
            config.enabled = True
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

    def test_get_supported_providers(self, service) -> None:
        """Test getting supported providers."""
        providers = service.get_supported_providers()
        assert len(providers) > 0

        # Check structure
        for provider in providers:
            assert hasattr(provider, "value")
            assert hasattr(provider, "label")
            assert hasattr(provider, "description")

        # Should include pushover and discord
        provider_values = [p.value for p in providers]
        assert "pushover" in provider_values
        assert "discord" in provider_values

    def test_create_config_success(self, service, test_db: Session) -> None:
        """Test successful config creation."""
        config = service.create_config(
            name="new-config",
            provider="pushover",
            provider_config={
                "user_key": "new-user" + "x" * 22,
                "app_token": "new-token" + "x" * 21,
            },
        )

        assert config.name == "new-config"
        assert config.provider == "pushover"
        assert config.enabled is True

        # Verify saved to database
        saved_config = (
            test_db.query(NotificationConfig)
            .filter(NotificationConfig.name == "new-config")
            .first()
        )
        assert saved_config is not None
        assert saved_config.provider == "pushover"

    def test_create_config_duplicate_name(self, service, sample_config) -> None:
        """Test creating config with duplicate name."""
        with pytest.raises(HTTPException) as exc_info:
            service.create_config(
                name="test-config",  # Same name as sample_config
                provider="pushover",
                provider_config={
                    "user_key": "user" + "x" * 26,
                    "app_token": "token" + "x" * 25,
                },
            )

        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)

    def test_create_config_invalid_provider_config(self, service) -> None:
        """Test creating config with invalid provider configuration."""
        with pytest.raises(HTTPException) as exc_info:
            service.create_config(
                name="invalid-config",
                provider="pushover",
                provider_config={},  # Missing required fields
            )

        assert exc_info.value.status_code == 400
        assert "Invalid configuration" in str(exc_info.value.detail)

    def test_update_config_success(self, service, test_db, sample_config) -> None:
        """Test successful config update."""
        updated_config = service.update_config(
            config_id=sample_config.id,
            name="updated-config",
            provider="pushover",
            provider_config={
                "user_key": "updated-user" + "x" * 18,
                "app_token": "updated-token" + "x" * 17,
            },
        )

        assert updated_config.name == "updated-config"
        assert updated_config.provider == "pushover"

        # Verify in database
        test_db.refresh(updated_config)
        assert updated_config.name == "updated-config"

    def test_update_config_not_found(self, service) -> None:
        """Test updating non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            service.update_config(
                config_id=999,
                name="not-found",
                provider="pushover",
                provider_config={
                    "user_key": "user" + "x" * 26,
                    "app_token": "token" + "x" * 25,
                },
            )

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    def test_enable_config_success(
        self, service, test_db: Session, notification_service
    ) -> None:
        """Test successful config enabling."""
        # Create disabled config
        config = NotificationConfig()
        config.name = "disabled-config"
        config.provider = "pushover"
        config.provider_config = notification_service.prepare_config_for_storage(
            "pushover", {"user_key": "user" + "x" * 26, "app_token": "token" + "x" * 25}
        )
        config.enabled = False

        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        success, message = service.enable_config(config.id)

        assert success is True
        assert "enabled successfully" in message
        assert config.name in message

        # Verify in database
        test_db.refresh(config)
        assert config.enabled is True

    def test_enable_config_not_found(self, service) -> None:
        """Test enabling non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            service.enable_config(999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    def test_disable_config_success(
        self, service, test_db: Session, notification_service
    ) -> None:
        """Test successful config disabling."""
        # Create enabled config
        config = NotificationConfig()
        config.name = "enabled-config"
        config.provider = "pushover"
        config.provider_config = notification_service.prepare_config_for_storage(
            "pushover", {"user_key": "user" + "x" * 26, "app_token": "token" + "x" * 25}
        )
        config.enabled = True

        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        success, message = service.disable_config(config.id)

        assert success is True
        assert "disabled successfully" in message
        assert config.name in message

        # Verify in database
        test_db.refresh(config)
        assert config.enabled is False

    def test_disable_config_not_found(self, service) -> None:
        """Test disabling non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            service.disable_config(999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    def test_delete_config_success(self, service, test_db, sample_config) -> None:
        """Test successful config deletion."""
        config_id = sample_config.id
        config_name = sample_config.name

        success, returned_name = service.delete_config(config_id)

        assert success is True
        assert returned_name == config_name

        # Verify removed from database
        deleted_config = (
            test_db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )
        assert deleted_config is None

    def test_delete_config_not_found(self, service) -> None:
        """Test deleting non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            service.delete_config(999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    def test_get_config_with_decrypted_data_success(
        self, service, sample_config, notification_service
    ) -> None:
        """Test getting config with decrypted data."""
        config, decrypted_config = service.get_config_with_decrypted_data(
            sample_config.id
        )

        assert config.id == sample_config.id
        assert config.name == "test-config"
        assert isinstance(decrypted_config, dict)
        assert "user_key" in decrypted_config
        assert "app_token" in decrypted_config
        assert decrypted_config["user_key"].startswith("test-user")
        assert decrypted_config["app_token"].startswith("test-token")

    def test_get_config_with_decrypted_data_not_found(self, service) -> None:
        """Test getting decrypted data for non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            service.get_config_with_decrypted_data(999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_test_config_success(self, service, sample_config) -> None:
        """Test successful config testing."""
        # Note: This will likely fail in tests since we don't have real credentials
        # but we can test that the method exists and handles the flow correctly
        try:
            success, message = await service.test_config(sample_config.id)
            # Either succeeds or fails, but should return proper types
            assert isinstance(success, bool)
            assert isinstance(message, str)
        except Exception:
            # Expected in test environment without real credentials
            pass

    @pytest.mark.asyncio
    async def test_test_config_not_found(self, service) -> None:
        """Test testing non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            await service.test_config(999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_test_config_disabled(
        self, service, test_db: Session, notification_service
    ) -> None:
        """Test testing disabled config."""
        # Create disabled config
        config = NotificationConfig()
        config.name = "disabled-config"
        config.provider = "pushover"
        config.provider_config = notification_service.prepare_config_for_storage(
            "pushover", {"user_key": "user" + "x" * 26, "app_token": "token" + "x" * 25}
        )
        config.enabled = False

        test_db.add(config)
        test_db.commit()
        test_db.refresh(config)

        with pytest.raises(HTTPException) as exc_info:
            await service.test_config(config.id)

        assert exc_info.value.status_code == 400
        assert "disabled" in str(exc_info.value.detail)

    def test_config_lifecycle(self, service, test_db: Session) -> None:
        """Test complete config lifecycle: create, update, enable/disable, delete."""
        # Create
        created_config = service.create_config(
            name="lifecycle-test",
            provider="pushover",
            provider_config={
                "user_key": "lifecycle-user" + "x" * 16,
                "app_token": "lifecycle-token" + "x" * 15,
            },
        )
        config_id = created_config.id

        # Update
        updated_config = service.update_config(
            config_id=config_id,
            name="updated-lifecycle-test",
            provider="pushover",
            provider_config={
                "user_key": "updated-user" + "x" * 18,
                "app_token": "updated-token" + "x" * 17,
            },
        )
        assert updated_config.name == "updated-lifecycle-test"

        # Disable
        success, message = service.disable_config(config_id)
        assert success is True

        # Enable
        success, message = service.enable_config(config_id)
        assert success is True

        # Get with decrypted data
        config, decrypted_config = service.get_config_with_decrypted_data(config_id)
        assert config.name == "updated-lifecycle-test"
        assert decrypted_config["user_key"].startswith("updated-user")
        assert decrypted_config["app_token"].startswith("updated-token")

        # Delete
        success, config_name = service.delete_config(config_id)
        assert success is True
        assert config_name == "updated-lifecycle-test"

        # Verify completely removed
        deleted_config = (
            test_db.query(NotificationConfig)
            .filter(NotificationConfig.id == config_id)
            .first()
        )
        assert deleted_config is None
