"""
Tests for notification API endpoints - HTMX responses for Apprise configurations.
Business logic tests are in tests/unit/notifications.
"""

from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from borgitory.models.database import NotificationConfig
from borgitory.services.encryption_service import EncryptionService
from borgitory.services.notifications.apprise_storage import (
    StoredAppriseConfig,
)
from borgitory.services.notifications.service import NotificationService
from borgitory.services.notifications.types import NotificationResult
from tests.fixtures.notification_fixtures import (
    DISCORD_WEBHOOK_ID,
    DISCORD_WEBHOOK_TOKEN,
    build_stored_config,
    create_notification_config,
    discord_form,
)


async def _add(test_db: AsyncSession, config: NotificationConfig) -> NotificationConfig:
    test_db.add(config)
    await test_db.commit()
    await test_db.refresh(config)
    return config


async def _reload(test_db: AsyncSession, config_id: int) -> NotificationConfig:
    test_db.expire_all()
    result = await test_db.execute(
        select(NotificationConfig).where(NotificationConfig.id == config_id)
    )
    return result.scalar_one()


class TestServiceFields:
    async def test_no_service_returns_empty(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/api/notifications/service-fields")

        assert response.status_code == 200
        assert response.text == ""

    async def test_discord_fields_are_generated(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/notifications/service-fields?service=discord"
        )

        assert response.status_code == 200
        content = response.text
        assert 'name="fields[webhook_id]"' in content
        assert 'name="fields[webhook_token]"' in content
        assert 'name="fields[botname]"' in content
        assert 'type="password"' in content
        assert "Setup guide" in content

    async def test_unknown_service_returns_error(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/notifications/service-fields?service=<script>"
        )

        assert response.status_code == 200
        assert "Unknown notification service" in unquote(response.text)
        assert "<script>" not in unquote(response.text)

    async def test_manual_service_returns_url_field(
        self, async_client: AsyncClient
    ) -> None:
        response = await async_client.get(
            "/api/notifications/service-fields?service=__manual__"
        )

        assert response.status_code == 200
        assert 'name="urls"' in unquote(response.text)


class TestCreateConfig:
    async def test_create_service_config(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await async_client.post(
            "/api/notifications/", data=discord_form("create-discord")
        )

        assert response.status_code == 200
        assert response.headers["HX-Trigger"] == "notificationUpdate"

        result = await test_db.execute(
            select(NotificationConfig).where(
                NotificationConfig.name == "create-discord"
            )
        )
        config = result.scalar_one()
        assert config.provider == "apprise"
        assert config.enabled is True
        assert DISCORD_WEBHOOK_TOKEN not in config.provider_config

        stored = StoredAppriseConfig.decode(config.provider_config)
        assert stored.service == "discord"
        assert stored.fields == {"botname": "Borgitory"}
        assert set(stored.encrypted_fields) == {"webhook_id", "webhook_token"}

    async def test_create_manual_config(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        response = await async_client.post(
            "/api/notifications/",
            data={
                "name": "manual",
                "service": "__manual__",
                "urls": "json://localhost:8080\nntfys://ntfy.sh/borgitory-test",
            },
        )

        assert response.status_code == 200
        result = await test_db.execute(
            select(NotificationConfig).where(NotificationConfig.name == "manual")
        )
        stored = StoredAppriseConfig.decode(result.scalar_one().provider_config)
        assert stored.mode == "manual"
        urls = EncryptionService().decrypt_value(stored.encrypted_urls)
        assert urls.splitlines() == [
            "json://localhost:8080",
            "ntfys://ntfy.sh/borgitory-test",
        ]

    async def test_create_missing_required_field(
        self, async_client: AsyncClient
    ) -> None:
        form = discord_form("missing-token")
        del form["fields[webhook_token]"]

        response = await async_client.post("/api/notifications/", data=form)

        assert response.status_code == 400
        assert "Webhook Token" in unquote(response.text)

    async def test_create_invalid_manual_url(self, async_client: AsyncClient) -> None:
        response = await async_client.post(
            "/api/notifications/",
            data={"name": "bad", "service": "__manual__", "urls": "notaservice://x"},
        )

        assert response.status_code == 400
        assert "Invalid Apprise URL" in unquote(response.text)

    async def test_create_requires_service(self, async_client: AsyncClient) -> None:
        response = await async_client.post(
            "/api/notifications/", data={"name": "no-service"}
        )

        assert response.status_code == 400

    async def test_create_duplicate_name(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        await _add(test_db, create_notification_config("dupe"))

        response = await async_client.post(
            "/api/notifications/", data=discord_form("dupe")
        )

        assert response.status_code == 400
        assert "already exists" in unquote(response.text)


class TestListAndActions:
    async def test_list_shows_service_name(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        await _add(test_db, create_notification_config("listed"))

        response = await async_client.get("/api/notifications/html")

        assert response.status_code == 200
        assert "listed" in unquote(response.text)
        assert "Discord" in unquote(response.text)
        assert "Needs attention" not in unquote(response.text)

    async def test_list_flags_migration_errors(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        stored = StoredAppriseConfig(
            mode="service",
            service="pover",
            service_name="Pushover",
            migration_error="Could not convert this pushover notification",
        )
        await _add(
            test_db, create_notification_config("broken", enabled=False, stored=stored)
        )

        response = await async_client.get("/api/notifications/html")

        assert "Needs attention" in unquote(response.text)
        assert "Could not convert" in unquote(response.text)

    async def test_enable_and_disable(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        config = await _add(test_db, create_notification_config("toggle"))

        response = await async_client.post(f"/api/notifications/{config.id}/disable")
        assert response.status_code == 200
        assert response.headers["HX-Trigger"] == "notificationUpdate"
        assert (await _reload(test_db, config.id)).enabled is False

        response = await async_client.post(f"/api/notifications/{config.id}/enable")
        assert response.status_code == 200
        assert (await _reload(test_db, config.id)).enabled is True

    async def test_enable_blocked_until_reconfigured(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        stored = StoredAppriseConfig(
            mode="manual", service_name="Custom", migration_error="broken"
        )
        config = await _add(
            test_db, create_notification_config("broken", enabled=False, stored=stored)
        )

        response = await async_client.post(f"/api/notifications/{config.id}/enable")

        assert response.status_code == 400
        assert (await _reload(test_db, config.id)).enabled is False

    async def test_test_saved_config(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        config = await _add(test_db, create_notification_config("saved-test"))

        with patch.object(
            NotificationService,
            "send_test",
            AsyncMock(return_value=NotificationResult(success=True, message="ok")),
        ) as send_test:
            response = await async_client.post(f"/api/notifications/{config.id}/test")

        assert response.status_code == 200
        assert "sent successfully" in unquote(response.text)
        sent_config = send_test.call_args.args[0]
        assert sent_config.service == "discord"

    async def test_test_saved_config_failure(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        config = await _add(test_db, create_notification_config("saved-fail"))

        with patch.object(
            NotificationService,
            "send_test",
            AsyncMock(
                return_value=NotificationResult(
                    success=False, message="failed", error="Discord: HTTP 401"
                )
            ),
        ):
            response = await async_client.post(f"/api/notifications/{config.id}/test")

        assert response.status_code == 400
        assert "Discord: HTTP 401" in unquote(response.text)

    async def test_delete(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        config = await _add(test_db, create_notification_config("deleted"))

        response = await async_client.delete(f"/api/notifications/{config.id}")

        assert response.status_code == 200
        assert response.headers["HX-Trigger"] == "notificationUpdate"
        result = await test_db.execute(
            select(NotificationConfig).where(NotificationConfig.id == config.id)
        )
        assert result.scalar_one_or_none() is None

    async def test_add_form_lists_services(self, async_client: AsyncClient) -> None:
        response = await async_client.get("/api/notifications/form")

        assert response.status_code == 200
        assert 'optgroup label="Popular"' in unquote(response.text)
        assert 'value="discord"' in unquote(response.text)
        assert "Custom Apprise URL" in unquote(response.text)


class TestUnsavedFormTest:
    async def test_sends_test_for_unsaved_settings(
        self, async_client: AsyncClient
    ) -> None:
        with patch.object(
            NotificationService,
            "send_test",
            AsyncMock(return_value=NotificationResult(success=True, message="ok")),
        ) as send_test:
            response = await async_client.post(
                "/api/notifications/test", data=discord_form("unsaved")
            )

        assert response.status_code == 200
        assert "sent successfully" in unquote(response.text)
        assert send_test.call_args.args[0].service == "discord"

    async def test_requires_service(self, async_client: AsyncClient) -> None:
        response = await async_client.post(
            "/api/notifications/test", data={"name": "x"}
        )

        assert response.status_code == 400
        assert "Select a notification service" in unquote(response.text)

    async def test_reports_validation_errors(self, async_client: AsyncClient) -> None:
        form = discord_form("unsaved")
        del form["fields[webhook_id]"]

        response = await async_client.post("/api/notifications/test", data=form)

        assert response.status_code == 400
        assert "Webhook ID" in unquote(response.text)

    async def test_uses_stored_secrets_when_editing(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        config = await _add(test_db, create_notification_config("edit-test"))
        form = discord_form(
            "edit-test",
            **{"fields[webhook_token]": "", "config_id": str(config.id)},
        )

        with patch.object(
            NotificationService,
            "send_test",
            AsyncMock(return_value=NotificationResult(success=True, message="ok")),
        ) as send_test:
            response = await async_client.post("/api/notifications/test", data=form)

        assert response.status_code == 200
        sent_config = send_test.call_args.args[0]
        token = EncryptionService().decrypt_value(
            sent_config.encrypted_fields["webhook_token"]
        )
        assert token == DISCORD_WEBHOOK_TOKEN


class TestEditConfig:
    async def test_edit_form_never_contains_secrets(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        config = await _add(test_db, create_notification_config("secret-check"))

        form_response = await async_client.get(f"/api/notifications/{config.id}/edit")
        fields_response = await async_client.get(
            f"/api/notifications/service-fields?service=discord&config_id={config.id}"
        )

        assert form_response.status_code == 200
        assert "secret-check" in form_response.text
        assert 'value="discord"' in form_response.text
        for content in (form_response.text, fields_response.text):
            assert DISCORD_WEBHOOK_TOKEN not in content
            assert DISCORD_WEBHOOK_ID not in content
        assert "leave blank to keep" in fields_response.text
        assert 'value="Borgitory"' in fields_response.text

    async def test_edit_form_for_other_service_is_blank(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        config = await _add(test_db, create_notification_config("switch"))

        response = await async_client.get(
            f"/api/notifications/service-fields?service=tgram&config_id={config.id}"
        )

        assert "leave blank to keep" not in unquote(response.text)

    async def test_edit_form_for_manual_config_masks_urls(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        from borgitory.services.notifications.apprise_storage import (
            AppriseSubmission,
        )

        submission = AppriseSubmission(
            mode="manual", urls="pover://userkey1234@apptoken5678"
        )
        config = await _add(
            test_db, create_notification_config("manual-edit", submission=submission)
        )

        form_response = await async_client.get(f"/api/notifications/{config.id}/edit")
        fields_response = await async_client.get(
            f"/api/notifications/service-fields?service=__manual__&config_id={config.id}"
        )

        assert 'value="__manual__"' in form_response.text
        assert "Current URLs" in fields_response.text
        assert "userkey1234" not in fields_response.text
        assert "apptoken5678" not in fields_response.text

    async def test_update_keeps_blank_secrets(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        config = await _add(test_db, create_notification_config("update-me"))
        form = discord_form(
            "updated-name",
            **{
                "fields[webhook_id]": "",
                "fields[webhook_token]": "",
                "fields[botname]": "New Bot",
            },
        )

        response = await async_client.put(f"/api/notifications/{config.id}", data=form)

        assert response.status_code == 200
        assert response.headers["HX-Trigger"] == "notificationUpdate"
        updated = await _reload(test_db, config.id)
        assert updated.name == "updated-name"
        stored = StoredAppriseConfig.decode(updated.provider_config)
        assert stored.fields == {"botname": "New Bot"}
        encryption = EncryptionService()
        assert (
            encryption.decrypt_value(stored.encrypted_fields["webhook_token"])
            == DISCORD_WEBHOOK_TOKEN
        )
        url = encryption.decrypt_value(stored.encrypted_urls)
        assert url.startswith("discord://New%20Bot@")

    async def test_update_switching_service_requires_secrets(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        config = await _add(test_db, create_notification_config("switch-service"))

        response = await async_client.put(
            f"/api/notifications/{config.id}",
            data={"name": "switch-service", "service": "tgram"},
        )

        assert response.status_code == 400
        assert "Bot Token" in unquote(response.text)

    async def test_update_clears_migration_error(
        self, async_client: AsyncClient, test_db: AsyncSession
    ) -> None:
        stored = StoredAppriseConfig(
            mode="service",
            service="discord",
            service_name="Discord",
            migration_error="broken",
        )
        config = await _add(
            test_db, create_notification_config("fix-me", enabled=False, stored=stored)
        )

        response = await async_client.put(
            f"/api/notifications/{config.id}", data=discord_form("fix-me")
        )

        assert response.status_code == 200
        updated = StoredAppriseConfig.decode(
            (await _reload(test_db, config.id)).provider_config
        )
        assert updated.migration_error is None
        assert build_stored_config().service == updated.service
