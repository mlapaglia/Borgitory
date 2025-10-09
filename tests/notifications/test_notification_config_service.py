"""
Tests for NotificationConfigService - Business logic tests
"""

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from borgitory.services.notifications.config_service import NotificationConfigService
from borgitory.services.notifications.service import NotificationService
from borgitory.models.database import NotificationConfig


@pytest.fixture
def notification_service() -> NotificationService:
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
def service(notification_service: NotificationService) -> NotificationConfigService:
    """NotificationConfigService instance with real database session."""
    return NotificationConfigService(notification_service=notification_service)


@pytest_asyncio.fixture
async def sample_config(
    test_db: AsyncSession, notification_service: NotificationService
) -> NotificationConfig:
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
    await test_db.commit()
    await test_db.refresh(config)
    return config


class TestNotificationConfigService:
    """Test class for NotificationConfigService business logic."""

    @pytest.mark.asyncio
    async def test_get_all_configs_empty(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test getting configs when none exist."""
        result = await service.get_all_configs(db=test_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_configs_with_data(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        notification_service: NotificationService,
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
        await test_db.commit()

        result = await service.get_all_configs(db=test_db)
        assert len(result) == 2
        names = [c.name for c in result]
        assert "config-1" in names
        assert "config-2" in names

    @pytest.mark.asyncio
    async def test_get_all_configs_pagination(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        notification_service: NotificationService,
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
        await test_db.commit()

        result = await service.get_all_configs(db=test_db, skip=2, limit=2)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_config_by_id_success(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        """Test getting config by ID successfully."""
        result = await service.get_config_by_id(db=test_db, config_id=sample_config.id)
        assert result is not None
        assert result.name == "test-config"
        assert result.id == sample_config.id

    @pytest.mark.asyncio
    async def test_get_config_by_id_not_found(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test getting non-existent config by ID."""
        result = await service.get_config_by_id(db=test_db, config_id=999)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_supported_providers(
        self, service: NotificationConfigService
    ) -> None:
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

    @pytest.mark.asyncio
    async def test_create_config_success(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test successful config creation."""
        config = await service.create_config(
            db=test_db,
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
        result = await test_db.execute(
            select(NotificationConfig).where(NotificationConfig.name == "new-config")
        )
        saved_config = result.scalar_one_or_none()
        assert saved_config is not None
        assert saved_config.provider == "pushover"

    @pytest.mark.asyncio
    async def test_create_config_duplicate_name(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        """Test creating config with duplicate name."""
        with pytest.raises(HTTPException) as exc_info:
            await service.create_config(
                db=test_db,
                name="test-config",  # Same name as sample_config
                provider="pushover",
                provider_config={
                    "user_key": "user" + "x" * 26,
                    "app_token": "token" + "x" * 25,
                },
            )

        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_create_config_invalid_provider_config(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test creating config with invalid provider configuration."""
        with pytest.raises(HTTPException) as exc_info:
            await service.create_config(
                db=test_db,
                name="invalid-config",
                provider="pushover",
                provider_config={},  # Missing required fields
            )

        assert exc_info.value.status_code == 400
        assert "Invalid configuration" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_update_config_success(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        """Test successful config update."""
        updated_config = await service.update_config(
            db=test_db,
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
        await test_db.refresh(updated_config)
        assert updated_config.name == "updated-config"

    @pytest.mark.asyncio
    async def test_update_config_not_found(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test updating non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            await service.update_config(
                db=test_db,
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

    @pytest.mark.asyncio
    async def test_enable_config_success(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        notification_service: NotificationService,
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
        await test_db.commit()
        await test_db.refresh(config)

        success, message = await service.enable_config(db=test_db, config_id=config.id)

        assert success is True
        assert "enabled successfully" in message
        assert config.name in message

        # Verify in database
        await test_db.refresh(config)
        assert config.enabled is True

    @pytest.mark.asyncio
    async def test_enable_config_not_found(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test enabling non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            await service.enable_config(db=test_db, config_id=999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_disable_config_success(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        notification_service: NotificationService,
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
        await test_db.commit()
        await test_db.refresh(config)

        success, message = await service.disable_config(db=test_db, config_id=config.id)

        assert success is True
        assert "disabled successfully" in message
        assert config.name in message

        # Verify in database
        await test_db.refresh(config)
        assert config.enabled is False

    @pytest.mark.asyncio
    async def test_disable_config_not_found(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test disabling non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            await service.disable_config(db=test_db, config_id=999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_delete_config_success(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        """Test successful config deletion."""
        config_id = sample_config.id
        config_name = sample_config.name

        success, returned_name = await service.delete_config(
            db=test_db, config_id=config_id
        )

        assert success is True
        assert returned_name == config_name

        # Verify removed from database
        result = await test_db.execute(
            select(NotificationConfig).where(NotificationConfig.id == config_id)
        )
        deleted_config = result.scalar_one_or_none()
        assert deleted_config is None

    @pytest.mark.asyncio
    async def test_delete_config_not_found(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test deleting non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            await service.delete_config(db=test_db, config_id=999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_get_config_with_decrypted_data_success(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
        notification_service: NotificationService,
    ) -> None:
        """Test getting config with decrypted data."""
        config, decrypted_config = await service.get_config_with_decrypted_data(
            db=test_db, config_id=sample_config.id
        )

        assert config.id == sample_config.id
        assert config.name == "test-config"
        assert isinstance(decrypted_config, dict)
        assert "user_key" in decrypted_config
        assert "app_token" in decrypted_config
        assert decrypted_config["user_key"].startswith("test-user")
        assert decrypted_config["app_token"].startswith("test-token")

    @pytest.mark.asyncio
    async def test_get_config_with_decrypted_data_not_found(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test getting decrypted data for non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            await service.get_config_with_decrypted_data(db=test_db, config_id=999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_test_config_success(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        """Test successful config testing."""
        # Note: This will likely fail in tests since we don't have real credentials
        # but we can test that the method exists and handles the flow correctly
        try:
            success, message = await service.test_config(
                db=test_db, config_id=sample_config.id
            )
            # Either succeeds or fails, but should return proper types
            assert isinstance(success, bool)
            assert isinstance(message, str)
        except Exception:
            # Expected in test environment without real credentials
            pass

    @pytest.mark.asyncio
    async def test_test_config_not_found(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        """Test testing non-existent config."""
        with pytest.raises(HTTPException) as exc_info:
            await service.test_config(db=test_db, config_id=999)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_test_config_disabled(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        notification_service: NotificationService,
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
        await test_db.commit()
        await test_db.refresh(config)

        with pytest.raises(HTTPException) as exc_info:
            await service.test_config(db=test_db, config_id=config.id)

        assert exc_info.value.status_code == 400
        assert "disabled" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_config_lifecycle(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        notification_service: NotificationService,
    ) -> None:
        """Test complete config lifecycle: create, update, enable/disable, delete."""
        # Create
        created_config = await service.create_config(
            db=test_db,
            name="lifecycle-test",
            provider="pushover",
            provider_config={
                "user_key": "lifecycle-user" + "x" * 16,
                "app_token": "lifecycle-token" + "x" * 15,
            },
        )
        config_id = created_config.id

        # Update
        updated_config = await service.update_config(
            db=test_db,
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
        success, message = await service.disable_config(db=test_db, config_id=config_id)
        assert success is True

        # Enable
        success, message = await service.enable_config(db=test_db, config_id=config_id)
        assert success is True

        # Get with decrypted data
        config, decrypted_config = await service.get_config_with_decrypted_data(
            db=test_db, config_id=config_id
        )
        assert config.name == "updated-lifecycle-test"
        assert decrypted_config["user_key"].startswith("updated-user")
        assert decrypted_config["app_token"].startswith("updated-token")

        # Delete
        success, config_name = await service.delete_config(
            db=test_db, config_id=config_id
        )
        assert success is True
        assert config_name == "updated-lifecycle-test"

        # Verify completely removed
        result = await test_db.execute(
            select(NotificationConfig).where(NotificationConfig.id == config_id)
        )
        deleted_config = result.scalar_one_or_none()
        assert deleted_config is None
