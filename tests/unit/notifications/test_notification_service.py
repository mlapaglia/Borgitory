"""
Tests for the Apprise-backed NotificationService.

Apprise itself is replaced with a fake so no notifications are sent.
"""

from typing import List, Optional
from unittest.mock import AsyncMock, Mock

import apprise
import pytest

from borgitory.services.encryption_service import EncryptionService
from borgitory.services.notifications.apprise_catalog import get_apprise_catalog
from borgitory.services.notifications.apprise_storage import (
    AppriseSubmission,
    StoredAppriseConfig,
)
from borgitory.services.notifications.service import NotificationService
from borgitory.services.notifications.types import (
    NotificationMessage,
    NotificationType,
)
from tests.fixtures.notification_fixtures import (
    DISCORD_WEBHOOK_TOKEN,
    build_stored_config,
    discord_values,
)


def fake_service_result(
    name: str,
    success: bool,
    logs: Optional[List[apprise.NotifyLogEntry]] = None,
) -> Mock:
    result = Mock()
    result.name = name
    result.status = (
        apprise.AppriseResultStatus.SUCCESS
        if success
        else apprise.AppriseResultStatus.FAILURE
    )
    result.logs.return_value = logs or []
    return result


def fake_apprise(success: bool, results: List[Mock], add: bool = True) -> Mock:
    client = Mock()
    client.add.return_value = add
    notify_result = Mock()
    notify_result.__bool__ = Mock(return_value=success)
    notify_result.results = results
    client.async_notify = AsyncMock(return_value=notify_result)
    return client


def make_service(client: Mock) -> NotificationService:
    return NotificationService(
        catalog=get_apprise_catalog(), apprise_factory=lambda asset: client
    )


MESSAGE = NotificationMessage(
    title="Backup done",
    message="All good",
    notification_type=NotificationType.ERROR,
)


class TestSendNotification:
    async def test_success(self) -> None:
        client = fake_apprise(True, [fake_service_result("Discord", True)])

        result = await make_service(client).send_notification(
            build_stored_config(), MESSAGE
        )

        assert result.success is True
        assert result.details == ["Discord: sent"]
        client.add.assert_called_once()
        assert client.add.call_args.args[0].startswith("discord://Borgitory@")
        kwargs = client.async_notify.call_args.kwargs
        assert kwargs["title"] == "Backup done"
        assert kwargs["body"] == "All good"
        assert kwargs["notify_type"] == apprise.NotifyType.FAILURE
        assert kwargs["body_format"] == apprise.NotifyFormat.TEXT
        client.async_notify.return_value.close.assert_called_once()

    async def test_failure_reports_apprise_logs(self) -> None:
        logs = [
            apprise.NotifyLogEntry("DEBUG", "debug noise"),
            apprise.NotifyLogEntry("WARNING", "Failed to send: HTTP 401"),
        ]
        client = fake_apprise(False, [fake_service_result("Discord", False, logs)])

        result = await make_service(client).send_notification(
            build_stored_config(), MESSAGE
        )

        assert result.success is False
        assert result.error == "Discord: Failed to send: HTTP 401"
        client.async_notify.return_value.close.assert_called_once()

    async def test_failure_without_logs_uses_status(self) -> None:
        client = fake_apprise(False, [fake_service_result("Discord", False)])

        result = await make_service(client).send_notification(
            build_stored_config(), MESSAGE
        )

        assert result.error == "Discord: failure"

    async def test_unloadable_url(self) -> None:
        client = fake_apprise(True, [], add=False)

        result = await make_service(client).send_notification(
            build_stored_config(), MESSAGE
        )

        assert result.success is False
        assert "re-save" in (result.error or "")
        client.async_notify.assert_not_called()

    async def test_apprise_exception(self) -> None:
        client = fake_apprise(True, [])
        client.async_notify.side_effect = RuntimeError("boom")

        result = await make_service(client).send_notification(
            build_stored_config(), MESSAGE
        )

        assert result.success is False
        assert result.error == "boom"

    async def test_migration_error_is_not_sent(self) -> None:
        client = fake_apprise(True, [])
        config = StoredAppriseConfig(
            mode="manual", service_name="Custom", migration_error="needs work"
        )

        result = await make_service(client).send_notification(config, MESSAGE)

        assert result.success is False
        assert result.error == "needs work"
        client.add.assert_not_called()

    async def test_send_test_uses_info_type(self) -> None:
        client = fake_apprise(True, [fake_service_result("Discord", True)])

        result = await make_service(client).send_test(build_stored_config())

        assert result.success is True
        kwargs = client.async_notify.call_args.kwargs
        assert kwargs["notify_type"] == apprise.NotifyType.INFO

    async def test_manual_config_sends_every_url(self) -> None:
        client = fake_apprise(True, [])
        config = build_stored_config(
            AppriseSubmission(mode="manual", urls="json://a.local\njson://b.local")
        )

        await make_service(client).send_notification(config, MESSAGE)

        added = [call.args[0] for call in client.add.call_args_list]
        assert added == ["json://a.local", "json://b.local"]


class TestBuildConfig:
    def test_unknown_service(self) -> None:
        service = make_service(Mock())

        with pytest.raises(ValueError, match="Unknown notification service"):
            service.build_config(AppriseSubmission(mode="service", service="nope"))

    def test_ignores_unknown_fields(self) -> None:
        values = discord_values()
        values["not_a_field"] = "x"

        config = make_service(Mock()).build_config(
            AppriseSubmission(mode="service", service="discord", values=values)
        )

        assert "not_a_field" not in config.fields

    def test_rejected_by_apprise(self) -> None:
        with pytest.raises(ValueError, match="rejected"):
            make_service(Mock()).build_config(
                AppriseSubmission(
                    mode="service",
                    service="tgram",
                    values={"bot_token": "not-a-bot-token"},
                )
            )

    def test_merge_keeps_secrets_for_same_service(self) -> None:
        service = make_service(Mock())
        existing = build_stored_config()

        updated = service.build_config(
            AppriseSubmission(
                mode="service",
                service="discord",
                values=discord_values() | {"webhook_token": ""},
            ),
            existing,
        )

        token = EncryptionService().decrypt_value(
            updated.encrypted_fields["webhook_token"]
        )
        assert token == DISCORD_WEBHOOK_TOKEN

    def test_merge_does_not_cross_services(self) -> None:
        service = make_service(Mock())
        existing = build_stored_config()

        with pytest.raises(ValueError, match="Bot Token"):
            service.build_config(
                AppriseSubmission(mode="service", service="tgram", values={}),
                existing,
            )

    def test_manual_blank_keeps_existing_urls(self) -> None:
        service = make_service(Mock())
        existing = build_stored_config(
            AppriseSubmission(mode="manual", urls="json://a.local")
        )

        updated = service.build_config(
            AppriseSubmission(mode="manual", urls="  "), existing
        )

        assert updated.encrypted_urls == existing.encrypted_urls

    def test_manual_requires_urls(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            make_service(Mock()).build_config(AppriseSubmission(mode="manual", urls=""))


class TestStorage:
    def test_round_trip(self) -> None:
        service = make_service(Mock())
        config = build_stored_config()

        loaded = service.load_config_from_storage(
            "apprise", service.prepare_config_for_storage(config)
        )

        assert loaded == config

    def test_legacy_provider_rejected(self) -> None:
        with pytest.raises(ValueError, match="no longer supported"):
            make_service(Mock()).load_config_from_storage("pushover", "{}")

    def test_invalid_json_rejected(self) -> None:
        with pytest.raises(ValueError):
            StoredAppriseConfig.decode("{not json")

    def test_edit_view_has_no_secrets(self) -> None:
        view = make_service(Mock()).get_edit_view(build_stored_config())

        assert DISCORD_WEBHOOK_TOKEN not in str(view.field_values)
        assert view.stored_private_keys == {"webhook_id", "webhook_token"}


class TestNotificationType:
    @pytest.mark.parametrize(
        "notification_type,expected",
        [
            (NotificationType.SUCCESS, apprise.NotifyType.SUCCESS),
            (NotificationType.WARNING, apprise.NotifyType.WARNING),
            (NotificationType.ERROR, apprise.NotifyType.FAILURE),
            (NotificationType.FAILURE, apprise.NotifyType.FAILURE),
            (NotificationType.INFO, apprise.NotifyType.INFO),
        ],
    )
    def test_mapping(
        self, notification_type: NotificationType, expected: apprise.NotifyType
    ) -> None:
        assert notification_type.to_apprise_notify_type() == expected
