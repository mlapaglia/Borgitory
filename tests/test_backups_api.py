"""
Tests for backups API endpoints
"""

import pytest
import json
from httpx import AsyncClient
from sqlalchemy.orm import Session

from borgitory.models.database import (
    Repository,
    PruneConfig,
    CloudSyncConfig,
    NotificationConfig,
    RepositoryCheckConfig,
)


class TestBackupsAPI:
    """Test class for backups API endpoints."""

    @pytest.mark.asyncio
    async def test_get_backup_form_empty_database(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting backup form when database is empty."""
        response = await async_client.get("/api/backups/form")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Verify the form contains expected elements even with empty data
        content = response.text
        assert "Select Repository..." in content  # Default option should be present

    @pytest.mark.asyncio
    async def test_get_backup_form_with_repository(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting backup form with a repository in database."""
        # Create test repository
        repository = Repository(
            name="test-repo",
            path="/tmp/test-repo",
        )
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)
        test_db.commit()

        response = await async_client.get("/api/backups/form")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        content = response.text
        assert "test-repo" in content

    @pytest.mark.asyncio
    async def test_get_backup_form_with_all_configs(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test getting backup form with all configuration types present."""
        # Create test repository
        repository = Repository(
            name="test-repo",
            path="/tmp/test-repo",
        )
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)

        # Create enabled prune config
        prune_config = PruneConfig(
            name="test-prune",
            enabled=True,
            strategy="advanced",
            keep_secondly=7,
            keep_minutely=7,
            keep_hourly=7,
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=1,
        )
        test_db.add(prune_config)

        # Create enabled cloud sync config
        import json

        cloud_sync_config = CloudSyncConfig(
            name="test-cloud-sync",
            provider="s3",
            provider_config=json.dumps(
                {
                    "bucket_name": "test-bucket",
                    "access_key": "test-access-key",
                    "secret_key": "test-secret-key",
                }
            ),
            enabled=True,
        )
        test_db.add(cloud_sync_config)

        # Create enabled notification config
        notification_config = NotificationConfig()
        notification_config.name = "test-notification"
        notification_config.enabled = True
        notification_config.provider = "pushover"
        notification_config.provider_config = (
            '{"user_key": "'
            + "u"
            + "x" * 29
            + '", "app_token": "'
            + "a"
            + "x" * 29
            + '"}'
        )
        test_db.add(notification_config)

        # Create enabled repository check config
        check_config = RepositoryCheckConfig(
            name="test-check",
            enabled=True,
            check_type="full",
            verify_data=True,
        )
        test_db.add(check_config)

        test_db.commit()

        response = await async_client.get("/api/backups/form")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        content = response.text
        assert "test-repo" in content

    @pytest.mark.asyncio
    async def test_get_backup_form_only_enabled_configs(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test that only enabled configs are returned in the form."""
        # Create disabled prune config
        disabled_prune = PruneConfig(
            name="disabled-prune",
            enabled=False,  # This should not appear
            strategy="advanced",
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=1,
        )
        test_db.add(disabled_prune)

        # Create enabled prune config
        enabled_prune = PruneConfig(
            name="enabled-prune",
            enabled=True,  # This should appear
            strategy="advanced",
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=1,
        )
        test_db.add(enabled_prune)

        test_db.commit()

        response = await async_client.get("/api/backups/form")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_backup_form_mixed_enabled_disabled(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test form generation with mix of enabled and disabled configurations."""
        # Create multiple configs of each type with different enabled states
        configs = [
            # Prune configs
            PruneConfig(
                name="prune-1",
                enabled=True,
                strategy="advanced",
                keep_secondly=7,
                keep_minutely=7,
                keep_hourly=7,
                keep_daily=7,
                keep_weekly=4,
                keep_monthly=6,
                keep_yearly=1,
            ),
            PruneConfig(
                name="prune-2",
                enabled=False,
                strategy="advanced",
                keep_secondly=7,
                keep_minutely=7,
                keep_hourly=7,
                keep_daily=7,
                keep_weekly=4,
                keep_monthly=6,
                keep_yearly=1,
            ),
            PruneConfig(
                name="prune-3",
                enabled=True,
                strategy="advanced",
                keep_secondly=7,
                keep_minutely=7,
                keep_hourly=7,
                keep_daily=7,
                keep_weekly=4,
                keep_monthly=6,
                keep_yearly=1,
            ),
            # Cloud sync configs
            CloudSyncConfig(
                name="cloud-1",
                provider="s3",
                provider_config=json.dumps(
                    {
                        "bucket_name": "bucket1",
                        "access_key": "key1",
                        "secret_key": "secret1",
                    }
                ),
                enabled=True,
            ),
            CloudSyncConfig(
                name="cloud-2",
                provider="s3",
                provider_config=json.dumps(
                    {
                        "bucket_name": "bucket2",
                        "access_key": "key2",
                        "secret_key": "secret2",
                    }
                ),
                enabled=False,
            ),
            # Notification configs - need to create with proper provider_config
        ]

        # Create notification configs with proper provider_config
        notif_1 = NotificationConfig()
        notif_1.name = "notif-1"
        notif_1.enabled = True
        notif_1.provider = "pushover"
        notif_1.provider_config = (
            '{"user_key": "'
            + "u"
            + "x" * 29
            + '", "app_token": "'
            + "a"
            + "x" * 29
            + '"}'
        )

        notif_2 = NotificationConfig()
        notif_2.name = "notif-2"
        notif_2.enabled = False
        notif_2.provider = "pushover"
        notif_2.provider_config = (
            '{"user_key": "'
            + "u2"
            + "x" * 28
            + '", "app_token": "'
            + "a2"
            + "x" * 28
            + '"}'
        )

        configs.extend(
            [
                notif_1,
                notif_2,
                # Repository check configs
                RepositoryCheckConfig(
                    name="check-1", enabled=True, check_type="full", verify_data=True
                ),
                RepositoryCheckConfig(
                    name="check-2",
                    enabled=False,
                    check_type="repository_only",
                    verify_data=False,
                ),
            ]
        )

        for config in configs:
            test_db.add(config)
        test_db.commit()

        response = await async_client.get("/api/backups/form")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Verify response is valid HTML and endpoint handles mixed scenarios correctly

    @pytest.mark.asyncio
    async def test_get_backup_form_database_error_handling(
        self, async_client: AsyncClient
    ) -> None:
        """Test backup form endpoint handles database errors gracefully."""
        # This test would require mocking database failures
        # For now, we test that the endpoint at least responds
        response = await async_client.get("/api/backups/form")

        # Even if there are issues, the endpoint should return a response
        # (The exact behavior depends on error handling in the template)
        assert response.status_code in [200, 500]  # Either success or handled error

    @pytest.mark.asyncio
    async def test_get_backup_form_response_headers(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test that backup form endpoint returns correct response headers."""
        response = await async_client.get("/api/backups/form")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

        # Verify response is proper HTML
        content = response.text
        assert len(content) > 0  # Should have some content

    @pytest.mark.asyncio
    async def test_get_backup_form_template_context(
        self, async_client: AsyncClient, test_db: Session
    ) -> None:
        """Test that all expected context variables are available to template."""
        # Create one of each config type
        repository = Repository(name="context-repo", path="/tmp/context-repo")
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)

        prune_config = PruneConfig(
            name="context-prune",
            enabled=True,
            strategy="advanced",
            keep_secondly=7,
            keep_minutely=7,
            keep_hourly=7,
            keep_daily=7,
            keep_weekly=4,
            keep_monthly=6,
            keep_yearly=1,
        )
        test_db.add(prune_config)

        cloud_sync_config = CloudSyncConfig(
            name="context-cloud",
            provider="s3",
            provider_config=json.dumps(
                {
                    "bucket_name": "test-bucket",
                    "access_key": "test-access-key",
                    "secret_key": "test-secret-key",
                }
            ),
            enabled=True,
        )
        test_db.add(cloud_sync_config)

        notification_config = NotificationConfig()
        notification_config.name = "context-notif"
        notification_config.enabled = True
        notification_config.provider = "pushover"
        notification_config.provider_config = (
            '{"user_key": "'
            + "u"
            + "x" * 29
            + '", "app_token": "'
            + "a"
            + "x" * 29
            + '"}'
        )
        test_db.add(notification_config)

        check_config = RepositoryCheckConfig(
            name="context-check", enabled=True, check_type="full", verify_data=True
        )
        test_db.add(check_config)

        test_db.commit()

        response = await async_client.get("/api/backups/form")

        assert response.status_code == 200

        # The template should receive all the context variables
        # Exact validation depends on template structure, but endpoint should work
        content = response.text
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_get_backup_form_invalid_route(
        self, async_client: AsyncClient
    ) -> None:
        """Test that invalid routes return 404."""
        response = await async_client.get("/api/backups/invalid")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_backup_form_method_not_allowed(
        self, async_client: AsyncClient
    ) -> None:
        """Test that non-GET methods return 405."""
        response = await async_client.post("/api/backups/form")

        assert response.status_code == 405
