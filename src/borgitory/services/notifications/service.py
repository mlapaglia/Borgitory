"""
Notification service backed by Apprise.

Builds, stores and sends notification configurations. All delivery goes through
Apprise, so any service Apprise supports can be used.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, FrozenSet, List, Optional

import apprise

from borgitory.services.encryption_service import EncryptionService
from borgitory.services.notifications.apprise_catalog import (
    AppriseCatalog,
    AppriseService,
)
from borgitory.services.notifications.apprise_storage import (
    APPRISE_PROVIDER,
    MANUAL_SERVICE_NAME,
    AppriseSubmission,
    StoredAppriseConfig,
)
from borgitory.services.notifications.apprise_url_builder import (
    UrlBuildError,
    build_url,
    mask_url,
    split_urls,
    validate_url,
)
from borgitory.services.notifications.types import (
    NotificationMessage,
    NotificationResult,
    NotificationType,
)

logger = logging.getLogger(__name__)

AppriseFactory = Callable[[apprise.AppriseAsset], apprise.Apprise]


def _default_apprise_factory(asset: apprise.AppriseAsset) -> apprise.Apprise:
    return apprise.Apprise(asset=asset)


@dataclass
class NotificationEditView:
    """What the edit form needs to know about a stored configuration (no secrets)"""

    mode: str
    service: Optional[AppriseService]
    service_name: str
    field_values: Dict[str, str] = field(default_factory=dict)
    stored_private_keys: FrozenSet[str] = frozenset()
    masked_urls: List[str] = field(default_factory=list)
    migration_error: Optional[str] = None


class NotificationService:
    """High-level service for building, storing and sending Apprise notifications"""

    def __init__(
        self,
        catalog: AppriseCatalog,
        encryption_service: Optional[EncryptionService] = None,
        apprise_factory: AppriseFactory = _default_apprise_factory,
    ) -> None:
        self._catalog = catalog
        self._encryption_service = encryption_service or EncryptionService()
        self._apprise_factory = apprise_factory

    @property
    def catalog(self) -> AppriseCatalog:
        return self._catalog

    def build_config(
        self,
        submission: AppriseSubmission,
        existing: Optional[StoredAppriseConfig] = None,
    ) -> StoredAppriseConfig:
        """
        Turn a form submission into a validated, encrypted configuration.

        Blank secret fields keep the previously stored value when editing the same
        service, so secrets never need to be sent back to the browser.

        Raises:
            ValueError: If the submission cannot produce a valid Apprise URL
        """
        if submission.mode == "manual":
            return self._build_manual_config(submission, existing)
        return self._build_service_config(submission, existing)

    def _build_manual_config(
        self,
        submission: AppriseSubmission,
        existing: Optional[StoredAppriseConfig],
    ) -> StoredAppriseConfig:
        urls = split_urls(submission.urls)
        if not urls:
            if existing and existing.mode == "manual" and existing.encrypted_urls:
                return StoredAppriseConfig(
                    mode="manual",
                    service_name=MANUAL_SERVICE_NAME,
                    encrypted_urls=existing.encrypted_urls,
                )
            raise ValueError("At least one Apprise URL is required")

        for url in urls:
            error = validate_url(url)
            if error:
                raise ValueError(f"Invalid Apprise URL: {error}")

        return StoredAppriseConfig(
            mode="manual",
            service_name=MANUAL_SERVICE_NAME,
            encrypted_urls=self._encryption_service.encrypt_value("\n".join(urls)),
        )

    def _build_service_config(
        self,
        submission: AppriseSubmission,
        existing: Optional[StoredAppriseConfig],
    ) -> StoredAppriseConfig:
        service = self._catalog.get(submission.service or "")
        if service is None:
            raise ValueError(f"Unknown notification service: {submission.service}")

        keep_existing_secrets = (
            existing is not None
            and existing.mode == "service"
            and existing.service == service.id
        )

        values: Dict[str, str] = {}
        for key, raw_value in submission.values.items():
            if service.get_field(key) is None:
                continue
            value = raw_value.strip()
            if value:
                values[key] = value

        for key in service.private_keys:
            if key not in values and keep_existing_secrets and existing is not None:
                ciphertext = existing.encrypted_fields.get(key)
                if ciphertext:
                    values[key] = self._encryption_service.decrypt_value(ciphertext)

        try:
            url = build_url(service, values)
        except UrlBuildError as e:
            raise ValueError(str(e)) from e

        error = validate_url(url)
        if error:
            raise ValueError(f"{service.name} rejected these settings: {error}")

        private_keys = service.private_keys
        return StoredAppriseConfig(
            mode="service",
            service=service.id,
            service_name=service.name,
            fields={k: v for k, v in values.items() if k not in private_keys},
            encrypted_fields={
                k: self._encryption_service.encrypt_value(v)
                for k, v in values.items()
                if k in private_keys
            },
            encrypted_urls=self._encryption_service.encrypt_value(url),
        )

    def prepare_config_for_storage(self, config: StoredAppriseConfig) -> str:
        return config.encode()

    def load_config_from_storage(
        self, provider: str, stored: str
    ) -> StoredAppriseConfig:
        """
        Load a stored configuration.

        Raises:
            ValueError: If the row is not an Apprise configuration
        """
        if provider != APPRISE_PROVIDER:
            raise ValueError(
                f"Notification provider '{provider}' is no longer supported; "
                "re-create this notification"
            )
        return StoredAppriseConfig.decode(stored)

    def get_edit_view(self, config: StoredAppriseConfig) -> NotificationEditView:
        service = self._catalog.get(config.service) if config.service else None
        masked_urls: List[str] = []
        if config.mode == "manual" and config.encrypted_urls:
            try:
                masked_urls = [mask_url(u) for u in self._decrypt_urls(config)]
            except Exception as e:
                logger.warning(f"Could not decrypt notification URLs: {e}")

        return NotificationEditView(
            mode=config.mode,
            service=service,
            service_name=config.service_name,
            field_values=dict(config.fields),
            stored_private_keys=frozenset(config.encrypted_fields.keys()),
            masked_urls=masked_urls,
            migration_error=config.migration_error,
        )

    def _decrypt_urls(self, config: StoredAppriseConfig) -> List[str]:
        if not config.encrypted_urls:
            return []
        return split_urls(self._encryption_service.decrypt_value(config.encrypted_urls))

    async def send_notification(
        self,
        config: StoredAppriseConfig,
        message: NotificationMessage,
    ) -> NotificationResult:
        """Send a message to every URL in the configuration"""
        if config.migration_error:
            return NotificationResult(
                success=False,
                message="Notification must be re-configured",
                error=config.migration_error,
            )

        try:
            urls = self._decrypt_urls(config)
        except Exception as e:
            logger.error(f"Failed to decrypt notification URLs: {e}")
            return NotificationResult(
                success=False,
                message="Failed to load notification settings",
                error=str(e),
            )

        if not urls:
            return NotificationResult(
                success=False,
                message="No notification URLs configured",
                error="No notification URLs configured",
            )

        return await self._send(urls, message)

    async def send_test(self, config: StoredAppriseConfig) -> NotificationResult:
        return await self.send_notification(
            config,
            NotificationMessage(
                title="Borgitory Test Notification",
                message="This is a test notification from Borgitory.",
                notification_type=NotificationType.INFO,
            ),
        )

    async def _send(
        self, urls: List[str], message: NotificationMessage
    ) -> NotificationResult:
        asset = apprise.AppriseAsset(
            app_id="Borgitory",
            app_desc="Borgitory",
            app_url="https://github.com/mlapaglia/Borgitory",
            secure_logging=True,
        )
        client = self._apprise_factory(asset)

        for url in urls:
            if not client.add(url):
                error = validate_url(url) or "Apprise does not recognize this URL"
                return NotificationResult(
                    success=False,
                    message="Stored notification URL is not valid",
                    error=f"{error}. Edit and re-save this notification.",
                )

        try:
            result = await client.async_notify(
                body=message.message,
                title=message.title,
                notify_type=message.notification_type.to_apprise_notify_type(),
                body_format=apprise.NotifyFormat.TEXT,
            )
        except Exception as e:
            logger.error(f"Apprise raised while sending notification: {e}")
            return NotificationResult(
                success=False, message="Failed to send notification", error=str(e)
            )

        try:
            return self._summarize(result)
        finally:
            result.close()

    def _summarize(self, result: apprise.AppriseResult) -> NotificationResult:
        details: List[str] = []
        failures: List[str] = []
        for service_result in result.results:
            if service_result.status == apprise.AppriseResultStatus.SUCCESS:
                details.append(f"{service_result.name}: sent")
                continue
            problems = [
                entry.message
                for entry in service_result.logs()
                if entry.level in ("WARNING", "ERROR", "CRITICAL")
            ]
            reason = problems[-1] if problems else service_result.status.name.lower()
            failures.append(f"{service_result.name}: {reason}")
            details.append(f"{service_result.name}: {reason}")

        if bool(result) and not failures:
            return NotificationResult(
                success=True, message="Notification sent successfully", details=details
            )

        return NotificationResult(
            success=False,
            message="Failed to send notification",
            error="; ".join(failures) or "Apprise reported a failure",
            details=details,
        )
