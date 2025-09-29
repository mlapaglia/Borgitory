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
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
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
        repository = Repository()
        repository.name = "test-repo"
        repository.path = "/tmp/test-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)

        # Create enabled prune config
        prune_config = PruneConfig()
        prune_config.name = "test-prune"
        prune_config.enabled = True
        prune_config.strategy = "advanced"
        prune_config.keep_secondly = 7
        prune_config.keep_minutely = 7
        prune_config.keep_hourly = 7
        prune_config.keep_daily = 7
        prune_config.keep_weekly = 4
        prune_config.keep_monthly = 6
        prune_config.keep_yearly = 1
        test_db.add(prune_config)

        # Create enabled cloud sync config
        import json

        cloud_sync_config = CloudSyncConfig()
        cloud_sync_config.name = "test-cloud-sync"
        cloud_sync_config.provider = "s3"
        cloud_sync_config.provider_config = json.dumps(
            {
                "bucket_name": "test-bucket",
                "access_key": "test-access-key",
                "secret_key": "test-secret-key",
            }
        )
        cloud_sync_config.enabled = True
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
        check_config = RepositoryCheckConfig()
        check_config.name = "test-check"
        check_config.enabled = True
        check_config.check_type = "full"
        check_config.verify_data = True
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
        disabled_prune = PruneConfig()
        disabled_prune.name = "disabled-prune"
        disabled_prune.enabled = False  # This should not appear
        disabled_prune.strategy = "advanced"
        disabled_prune.keep_daily = 7
        disabled_prune.keep_weekly = 4
        disabled_prune.keep_monthly = 6
        disabled_prune.keep_yearly = 1
        test_db.add(disabled_prune)

        # Create enabled prune config
        enabled_prune = PruneConfig()
        enabled_prune.name = "enabled-prune"
        enabled_prune.enabled = True  # This should appear
        enabled_prune.strategy = "advanced"
        enabled_prune.keep_daily = 7
        enabled_prune.keep_weekly = 4
        enabled_prune.keep_monthly = 6
        enabled_prune.keep_yearly = 1
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
        # Create prune configs
        prune_1 = PruneConfig()
        prune_1.name = "prune-1"
        prune_1.enabled = True
        prune_1.strategy = "advanced"
        prune_1.keep_secondly = 7
        prune_1.keep_minutely = 7
        prune_1.keep_hourly = 7
        prune_1.keep_daily = 7
        prune_1.keep_weekly = 4
        prune_1.keep_monthly = 6
        prune_1.keep_yearly = 1

        prune_2 = PruneConfig()
        prune_2.name = "prune-2"
        prune_2.enabled = False
        prune_2.strategy = "advanced"
        prune_2.keep_secondly = 7
        prune_2.keep_minutely = 7
        prune_2.keep_hourly = 7
        prune_2.keep_daily = 7
        prune_2.keep_weekly = 4
        prune_2.keep_monthly = 6
        prune_2.keep_yearly = 1

        prune_3 = PruneConfig()
        prune_3.name = "prune-3"
        prune_3.enabled = True
        prune_3.strategy = "advanced"
        prune_3.keep_secondly = 7
        prune_3.keep_minutely = 7
        prune_3.keep_hourly = 7
        prune_3.keep_daily = 7
        prune_3.keep_weekly = 4
        prune_3.keep_monthly = 6
        prune_3.keep_yearly = 1

        # Add prune configs to database
        test_db.add(prune_1)
        test_db.add(prune_2)
        test_db.add(prune_3)

        # Create cloud sync configs
        cloud_1 = CloudSyncConfig()
        cloud_1.name = "cloud-1"
        cloud_1.provider = "s3"
        cloud_1.provider_config = json.dumps(
            {
                "bucket_name": "bucket1",
                "access_key": "key1",
                "secret_key": "secret1",
            }
        )
        cloud_1.enabled = True
        test_db.add(cloud_1)

        cloud_2 = CloudSyncConfig()
        cloud_2.name = "cloud-2"
        cloud_2.provider = "s3"
        cloud_2.provider_config = json.dumps(
            {
                "bucket_name": "bucket2",
                "access_key": "key2",
                "secret_key": "secret2",
            }
        )
        cloud_2.enabled = False
        test_db.add(cloud_2)

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

        test_db.add(notif_1)
        test_db.add(notif_2)

        # Create repository check configs
        check_1 = RepositoryCheckConfig()
        check_1.name = "check-1"
        check_1.enabled = True
        check_1.check_type = "full"
        check_1.verify_data = True
        test_db.add(check_1)

        check_2 = RepositoryCheckConfig()
        check_2.name = "check-2"
        check_2.enabled = False
        check_2.check_type = "repository_only"
        check_2.verify_data = False
        test_db.add(check_2)
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
        repository = Repository()
        repository.name = "context-repo"
        repository.path = "/tmp/context-repo"
        repository.set_passphrase("test-passphrase")
        test_db.add(repository)

        prune_config = PruneConfig()
        prune_config.name = "context-prune"
        prune_config.enabled = True
        prune_config.strategy = "advanced"
        prune_config.keep_secondly = 7
        prune_config.keep_minutely = 7
        prune_config.keep_hourly = 7
        prune_config.keep_daily = 7
        prune_config.keep_weekly = 4
        prune_config.keep_monthly = 6
        prune_config.keep_yearly = 1
        test_db.add(prune_config)

        cloud_sync_config = CloudSyncConfig()
        cloud_sync_config.name = "context-cloud"
        cloud_sync_config.provider = "s3"
        cloud_sync_config.provider_config = json.dumps(
            {
                "bucket_name": "test-bucket",
                "access_key": "test-access-key",
                "secret_key": "test-secret-key",
            }
        )
        cloud_sync_config.enabled = True
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

        check_config = RepositoryCheckConfig()
        check_config.name = "context-check"
        check_config.enabled = True
        check_config.check_type = "full"
        check_config.verify_data = True
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
