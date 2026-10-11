"""
Tests for NotificationConfigService - Business logic tests
"""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.models.database import NotificationConfig
from borgitory.services.encryption_service import EncryptionService
from borgitory.services.notifications.apprise_catalog import get_apprise_catalog
from borgitory.services.notifications.apprise_storage import (
    AppriseSubmission,
    StoredAppriseConfig,
)
from borgitory.services.notifications.config_service import NotificationConfigService
from borgitory.services.notifications.service import NotificationService
from borgitory.services.notifications.types import NotificationResult
from tests.fixtures.notification_fixtures import (
    DISCORD_WEBHOOK_TOKEN,
    create_notification_config,
    discord_values,
)


@pytest.fixture
def notification_service() -> NotificationService:
    return NotificationService(catalog=get_apprise_catalog())


@pytest.fixture
def service(notification_service: NotificationService) -> NotificationConfigService:
    return NotificationConfigService(notification_service=notification_service)


@pytest_asyncio.fixture
async def sample_config(test_db: AsyncSession) -> NotificationConfig:
    config = create_notification_config("test-config")
    test_db.add(config)
    await test_db.commit()
    await test_db.refresh(config)
    return config


def discord_submission(**values: str) -> AppriseSubmission:
    merged = discord_values()
    merged.update(values)
    return AppriseSubmission(mode="service", service="discord", values=merged)


class TestNotificationConfigService:
    async def test_get_all_configs_empty(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        assert await service.get_all_configs(test_db) == []

    async def test_get_all_configs(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        configs = await service.get_all_configs(test_db)

        assert [c.name for c in configs] == ["test-config"]

    async def test_get_config_by_id_not_found(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        assert await service.get_config_by_id(test_db, 999) is None

    async def test_create_config(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        config = await service.create_config(test_db, "new", discord_submission())

        assert config.id is not None
        assert config.provider == "apprise"
        assert config.enabled is True
        stored = StoredAppriseConfig.decode(config.provider_config)
        assert stored.service == "discord"
        assert stored.service_name == "Discord"

    async def test_create_config_duplicate_name(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await service.create_config(test_db, "test-config", discord_submission())

        assert exc_info.value.status_code == 400
        assert "already exists" in str(exc_info.value.detail)

    async def test_create_config_invalid(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await service.create_config(
                test_db, "bad", discord_submission(webhook_token="")
            )

        assert exc_info.value.status_code == 400
        assert "Webhook Token" in str(exc_info.value.detail)

    async def test_update_config_keeps_secrets(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        updated = await service.update_config(
            test_db,
            sample_config.id,
            "renamed",
            discord_submission(webhook_id="", webhook_token="", botname="Other"),
        )

        assert updated.name == "renamed"
        stored = StoredAppriseConfig.decode(updated.provider_config)
        assert stored.fields["botname"] == "Other"
        token = EncryptionService().decrypt_value(
            stored.encrypted_fields["webhook_token"]
        )
        assert token == DISCORD_WEBHOOK_TOKEN

    async def test_update_config_not_found(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await service.update_config(test_db, 999, "x", discord_submission())

        assert exc_info.value.status_code == 404

    async def test_update_config_duplicate_name(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        other = await service.create_config(test_db, "other", discord_submission())

        with pytest.raises(HTTPException) as exc_info:
            await service.update_config(
                test_db, other.id, "test-config", discord_submission()
            )

        assert exc_info.value.status_code == 400

    async def test_delete_config(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        success, name = await service.delete_config(test_db, sample_config.id)

        assert success is True
        assert name == "test-config"
        assert await service.get_config_by_id(test_db, sample_config.id) is None

    async def test_enable_disable_config(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        await service.disable_config(test_db, sample_config.id)
        assert sample_config.enabled is False

        await service.enable_config(test_db, sample_config.id)
        assert sample_config.enabled is True

    async def test_enable_config_with_migration_error(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        config = create_notification_config(
            "broken",
            enabled=False,
            stored=StoredAppriseConfig(
                mode="manual", service_name="Custom", migration_error="broken"
            ),
        )
        test_db.add(config)
        await test_db.commit()

        with pytest.raises(HTTPException) as exc_info:
            await service.enable_config(test_db, config.id)

        assert exc_info.value.status_code == 400

    async def test_test_config_with_service(
        self,
        service: NotificationConfigService,
        notification_service: NotificationService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        notification_service.send_test = AsyncMock(  # type: ignore[method-assign]
            return_value=NotificationResult(success=True, message="ok")
        )

        success, message = await service.test_config_with_service(
            test_db, sample_config.id, notification_service
        )

        assert success is True
        assert "test-config" in message

    async def test_test_config_disabled(
        self,
        service: NotificationConfigService,
        notification_service: NotificationService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        await service.disable_config(test_db, sample_config.id)

        with pytest.raises(HTTPException) as exc_info:
            await service.test_config_with_service(
                test_db, sample_config.id, notification_service
            )

        assert exc_info.value.status_code == 400

    async def test_test_submission_failure_message(
        self,
        service: NotificationConfigService,
        notification_service: NotificationService,
        test_db: AsyncSession,
    ) -> None:
        notification_service.send_test = AsyncMock(  # type: ignore[method-assign]
            return_value=NotificationResult(
                success=False, message="failed", error="Discord: 404"
            )
        )

        success, message = await service.test_submission(test_db, discord_submission())

        assert success is False
        assert "Discord: 404" in message

    async def test_get_config_for_edit_hides_secrets(
        self,
        service: NotificationConfigService,
        test_db: AsyncSession,
        sample_config: NotificationConfig,
    ) -> None:
        config, view = await service.get_config_for_edit(test_db, sample_config.id)

        assert config.id == sample_config.id
        assert view.service is not None and view.service.id == "discord"
        assert view.field_values == {"botname": "Borgitory"}
        assert view.stored_private_keys == {"webhook_id", "webhook_token"}

    async def test_get_config_for_edit_legacy_row(
        self, service: NotificationConfigService, test_db: AsyncSession
    ) -> None:
        config = NotificationConfig()
        config.name = "legacy"
        config.provider = "pushover"
        config.provider_config = '{"user_key": "x"}'
        config.enabled = True
        test_db.add(config)
        await test_db.commit()

        _, view = await service.get_config_for_edit(test_db, config.id)

        assert view.migration_error is not None
