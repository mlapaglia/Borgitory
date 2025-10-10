"""
Tests for TaskDefinitionBuilder - Centralized task definition creation
"""

from typing import Any
import pytest
from unittest.mock import MagicMock
from sqlalchemy.ext.asyncio import AsyncSession
from borgitory.protocols.job_protocols import TaskDefinition
from borgitory.services.task_definition_builder import TaskDefinitionBuilder
from borgitory.models.database import (
    PruneConfig,
    RepositoryCheckConfig,
    NotificationConfig,
)
from borgitory.models.schemas import PruneRequest, CheckRequest
from borgitory.services.jobs.job_models import TaskTypeEnum


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock database session"""
    return MagicMock(spec=AsyncSession)


@pytest.fixture
def task_builder() -> TaskDefinitionBuilder:
    """TaskDefinitionBuilder instance with mock database"""
    return TaskDefinitionBuilder()


@pytest.fixture
def mock_prune_config() -> MagicMock:
    """Mock cleanup configuration"""
    config = MagicMock(spec=PruneConfig)
    config.id = 1
    config.strategy = "simple"
    config.keep_within_days = 30
    config.show_list = True
    config.show_stats = True
    config.save_space = False
    return config


@pytest.fixture
def mock_advanced_prune_config() -> MagicMock:
    """Mock advanced cleanup configuration"""
    config = MagicMock(spec=PruneConfig)
    config.id = 2
    config.strategy = "advanced"
    config.keep_secondly = None
    config.keep_minutely = None
    config.keep_hourly = None
    config.keep_daily = 7
    config.keep_weekly = 4
    config.keep_monthly = 6
    config.keep_yearly = 1
    config.show_list = True
    config.show_stats = False
    config.save_space = True
    return config


@pytest.fixture
def mock_check_config() -> MagicMock:
    """Mock repository check configuration"""
    config = MagicMock(spec=RepositoryCheckConfig)
    config.id = 1
    config.name = "Full Check"
    config.check_type = "full"
    config.verify_data = True
    config.repair_mode = False
    config.save_space = True
    config.max_duration = 3600
    config.archive_prefix = "test-"
    config.archive_glob = "*"
    config.first_n_archives = 5
    config.last_n_archives = None
    return config


@pytest.fixture
def mock_notification_config() -> MagicMock:
    """Mock notification configuration"""
    config = MagicMock(spec=NotificationConfig)
    config.id = 1
    config.name = "test-pushover"
    config.provider = "pushover"
    config.provider_config = (
        '{"user_key": "encrypted_user", "app_token": "encrypted_token"}'
    )
    config.enabled = True
    return config


class TestTaskDefinitionBuilder:
    """Test the TaskDefinitionBuilder class"""

    def test_build_backup_task_defaults(
        self, task_builder: TaskDefinitionBuilder
    ) -> None:
        """Test building backup task with default parameters"""
        task = task_builder.build_backup_task("test-repo")

        expected = TaskDefinition(
            type=TaskTypeEnum.BACKUP,
            name="Backup test-repo",
            parameters={
                "source_path": "/data",
                "compression": "zstd",
                "dry_run": False,
                "ignore_lock": False,
            },
        )

        assert task == expected

    def test_build_backup_task_custom_params(
        self, task_builder: TaskDefinitionBuilder
    ) -> None:
        """Test building backup task with custom parameters"""
        task = task_builder.build_backup_task(
            "custom-repo", source_path="/custom/path", compression="lz4", dry_run=True
        )

        expected = TaskDefinition(
            type=TaskTypeEnum.BACKUP,
            name="Backup custom-repo",
            parameters={
                "source_path": "/custom/path",
                "compression": "lz4",
                "dry_run": True,
                "ignore_lock": False,
            },
        )

        assert task == expected

    async def test_build_prune_task_from_config_simple_strategy(
        self,
        task_builder: TaskDefinitionBuilder,
        mock_db: AsyncSession,
        mock_prune_config: MagicMock,
    ) -> None:
        """Test building prune task from simple strategy config"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prune_config
        mock_db.execute.return_value = mock_result  # type: ignore[attr-defined]

        task = await task_builder.build_prune_task_from_config(mock_db, 1, "test-repo")

        expected = TaskDefinition(
            type=TaskTypeEnum.PRUNE,
            name="Prune test-repo",
            parameters={
                "dry_run": False,
                "show_list": True,
                "show_stats": True,
                "save_space": False,
                "keep_within": "30d",
            },
        )

        assert task == expected

    async def test_build_prune_task_from_config_advanced_strategy(
        self,
        task_builder: TaskDefinitionBuilder,
        mock_db: AsyncSession,
        mock_advanced_prune_config: MagicMock,
    ) -> None:
        """Test building prune task from advanced strategy config"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_advanced_prune_config
        mock_db.execute.return_value = mock_result  # type: ignore[attr-defined]

        task = await task_builder.build_prune_task_from_config(mock_db, 2, "test-repo")

        expected = TaskDefinition(
            type=TaskTypeEnum.PRUNE,
            name="Prune test-repo",
            parameters={
                "dry_run": False,
                "show_list": True,
                "show_stats": False,
                "save_space": True,
                "keep_secondly": None,
                "keep_minutely": None,
                "keep_hourly": None,
                "keep_daily": 7,
                "keep_weekly": 4,
                "keep_monthly": 6,
                "keep_yearly": 1,
            },
        )

        assert task == expected

    async def test_build_prune_task_from_config_not_found(
        self, task_builder: TaskDefinitionBuilder, mock_db: AsyncSession
    ) -> None:
        """Test building prune task when config not found"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result  # type: ignore[attr-defined]

        task = await task_builder.build_prune_task_from_config(
            mock_db, 999, "test-repo"
        )

        assert task is None

    def test_build_prune_task_from_request_simple(
        self, task_builder: TaskDefinitionBuilder
    ) -> None:
        """Test building prune task from simple strategy request"""
        prune_request = MagicMock(spec=PruneRequest)
        prune_request.strategy = "simple"
        prune_request.keep_within_days = 7
        prune_request.dry_run = True
        prune_request.save_space = True
        prune_request.force_prune = True

        task = task_builder.build_prune_task_from_request(prune_request, "test-repo")

        expected = TaskDefinition(
            type=TaskTypeEnum.PRUNE,
            name="Prune test-repo",
            parameters={
                "dry_run": True,
                "show_list": True,
                "show_stats": True,
                "save_space": True,
                "force_prune": True,
                "keep_within": "7d",
            },
        )

        assert task == expected

    def test_build_prune_task_from_request_advanced(
        self, task_builder: TaskDefinitionBuilder
    ) -> None:
        """Test building prune task from advanced strategy request"""
        prune_request = MagicMock(spec=PruneRequest)
        prune_request.strategy = "advanced"
        prune_request.keep_secondly = None
        prune_request.keep_minutely = None
        prune_request.keep_hourly = None
        prune_request.keep_daily = 14
        prune_request.keep_weekly = 8
        prune_request.keep_monthly = 12
        prune_request.keep_yearly = 2
        prune_request.dry_run = False

        task = task_builder.build_prune_task_from_request(prune_request, "test-repo")

        expected = TaskDefinition(
            type=TaskTypeEnum.PRUNE,
            name="Prune test-repo",
            parameters={
                "dry_run": False,
                "show_list": True,
                "show_stats": True,
                "save_space": True,
                "force_prune": False,
                "keep_secondly": None,
                "keep_minutely": None,
                "keep_hourly": None,
                "keep_daily": 14,
                "keep_weekly": 8,
                "keep_monthly": 12,
                "keep_yearly": 2,
            },
        )

        assert task == expected

    async def test_build_check_task_from_config(
        self,
        task_builder: TaskDefinitionBuilder,
        mock_db: AsyncSession,
        mock_check_config: MagicMock,
    ) -> None:
        """Test building check task from borgitory.configuration"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_check_config
        mock_db.execute.return_value = mock_result  # type: ignore[attr-defined]

        task = await task_builder.build_check_task_from_config(mock_db, 1, "test-repo")

        expected = TaskDefinition(
            type=TaskTypeEnum.CHECK,
            name="Check test-repo (Full Check)",
            parameters={
                "check_type": "full",
                "verify_data": True,
                "repair_mode": False,
                "save_space": True,
                "max_duration": 3600,
                "archive_prefix": "test-",
                "archive_glob": "*",
                "first_n_archives": 5,
                "last_n_archives": None,
            },
        )

        assert task == expected

    async def test_build_check_task_from_config_not_found(
        self, task_builder: TaskDefinitionBuilder, mock_db: AsyncSession
    ) -> None:
        """Test building check task when config not found"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result  # type: ignore[attr-defined]

        task = await task_builder.build_check_task_from_config(
            mock_db, 999, "test-repo"
        )

        assert task is None

    def test_build_check_task_from_request(
        self, task_builder: TaskDefinitionBuilder
    ) -> None:
        """Test building check task from request"""
        check_request = MagicMock(spec=CheckRequest)
        check_request.check_type = "repository_only"
        check_request.verify_data = False
        check_request.repair_mode = True
        check_request.save_space = False
        check_request.max_duration = 1800
        check_request.archive_prefix = "backup-"
        check_request.archive_glob = "backup-*"
        check_request.first_n_archives = 10
        check_request.last_n_archives = None

        task = task_builder.build_check_task_from_request(check_request, "test-repo")

        expected = TaskDefinition(
            type=TaskTypeEnum.CHECK,
            name="Check test-repo",
            parameters={
                "check_type": "repository_only",
                "verify_data": False,
                "repair_mode": True,
                "save_space": False,
                "max_duration": 1800,
                "archive_prefix": "backup-",
                "archive_glob": "backup-*",
                "first_n_archives": 10,
                "last_n_archives": None,
            },
        )

        assert task == expected

    def test_build_cloud_sync_task_with_repo_name(
        self, task_builder: TaskDefinitionBuilder
    ) -> None:
        """Test building cloud sync task with repository name"""
        task = task_builder.build_cloud_sync_task("test-repo")

        expected = TaskDefinition(
            type=TaskTypeEnum.CLOUD_SYNC,
            name="Sync test-repo to Cloud",
            parameters={"cloud_sync_config_id": None},
        )

        assert task == expected

    def test_build_cloud_sync_task_without_repo_name(
        self, task_builder: TaskDefinitionBuilder
    ) -> None:
        """Test building cloud sync task without repository name"""
        task = task_builder.build_cloud_sync_task()

        expected = TaskDefinition(
            type=TaskTypeEnum.CLOUD_SYNC,
            name="Sync to Cloud",
            parameters={"cloud_sync_config_id": None},
        )

        assert task == expected

    def test_build_cloud_sync_task_with_config_id(
        self, task_builder: TaskDefinitionBuilder
    ) -> None:
        """Test building cloud sync task with config ID"""
        task = task_builder.build_cloud_sync_task("test-repo", cloud_sync_config_id=123)

        expected = TaskDefinition(
            type=TaskTypeEnum.CLOUD_SYNC,
            name="Sync test-repo to Cloud",
            parameters={"cloud_sync_config_id": 123},
        )

        assert task == expected

    async def test_build_notification_task(
        self,
        task_builder: TaskDefinitionBuilder,
        mock_db: AsyncSession,
        mock_notification_config: MagicMock,
    ) -> None:
        """Test building notification task"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_notification_config
        mock_db.execute.return_value = mock_result  # type: ignore[attr-defined]

        task = await task_builder.build_notification_task(mock_db, 1, "test-repo")

        expected = TaskDefinition(
            type=TaskTypeEnum.NOTIFICATION,
            name="Send notification for test-repo",
            parameters={"provider": "pushover", "config_id": 1},
        )

        assert task == expected

    async def test_build_notification_task_not_found(
        self, task_builder: TaskDefinitionBuilder, mock_db: AsyncSession
    ) -> None:
        """Test building notification task when config not found"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result  # type: ignore[attr-defined]

        task = await task_builder.build_notification_task(mock_db, 999, "test-repo")

        assert task is None

    async def test_build_task_list_comprehensive(
        self,
        task_builder: TaskDefinitionBuilder,
        mock_db: AsyncSession,
        mock_prune_config: MagicMock,
        mock_check_config: MagicMock,
        mock_notification_config: MagicMock,
    ) -> None:
        """Test building comprehensive task list with all task types"""

        # Setup mock execute to return different configs based on the call
        def mock_execute_side_effect(*args: Any, **kwargs: Any) -> MagicMock:
            mock_result = MagicMock()
            # Check which config is being requested by inspecting the statement
            # This is a simplified approach - in real tests you might want more sophisticated matching
            # For now, we'll just return configs in order
            if not hasattr(mock_execute_side_effect, "call_count"):
                mock_execute_side_effect.call_count = 0  # type: ignore[attr-defined]

            call_order = [
                mock_prune_config,
                mock_check_config,
                mock_notification_config,
            ]
            if mock_execute_side_effect.call_count < len(call_order):  # type: ignore[attr-defined]
                mock_result.scalar_one_or_none.return_value = call_order[
                    mock_execute_side_effect.call_count  # type: ignore[attr-defined]
                ]
                mock_execute_side_effect.call_count += 1  # type: ignore[attr-defined]
            else:
                mock_result.scalar_one_or_none.return_value = None

            return mock_result

        mock_db.execute.side_effect = mock_execute_side_effect  # type: ignore[attr-defined]

        tasks = await task_builder.build_task_list(
            mock_db,
            repository_name="test-repo",
            include_backup=True,
            backup_params={"source_path": "/custom", "compression": "lz4"},
            prune_config_id=1,
            check_config_id=1,
            include_cloud_sync=True,
            notification_config_id=1,
        )

        assert len(tasks) == 5  # backup + prune + check + cloud_sync + notification

        # Verify task types
        task_types = [task.type for task in tasks]
        assert TaskTypeEnum.BACKUP in task_types
        assert TaskTypeEnum.PRUNE in task_types
        assert TaskTypeEnum.CHECK in task_types
        assert TaskTypeEnum.CLOUD_SYNC in task_types
        assert TaskTypeEnum.NOTIFICATION in task_types

        # Verify backup task uses custom params
        backup_task = next(task for task in tasks if task.type == TaskTypeEnum.BACKUP)
        assert backup_task.parameters["source_path"] == "/custom"
        assert backup_task.parameters["compression"] == "lz4"

    async def test_build_task_list_minimal(
        self, task_builder: TaskDefinitionBuilder, mock_db: AsyncSession
    ) -> None:
        """Test building minimal task list with only backup"""
        tasks = await task_builder.build_task_list(
            mock_db, repository_name="test-repo", include_backup=True
        )

        assert len(tasks) == 1
        assert tasks[0].type == TaskTypeEnum.BACKUP
        assert tasks[0].name == "Backup test-repo"

    async def test_build_task_list_no_backup(
        self,
        task_builder: TaskDefinitionBuilder,
        mock_db: AsyncSession,
        mock_prune_config: MagicMock,
    ) -> None:
        """Test building task list without backup task"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_prune_config
        mock_db.execute.return_value = mock_result  # type: ignore[attr-defined]

        tasks = await task_builder.build_task_list(
            mock_db,
            repository_name="test-repo",
            include_backup=False,
            prune_config_id=1,
            include_cloud_sync=True,
        )

        assert len(tasks) == 2  # prune + cloud_sync
        task_types = [task.type for task in tasks]
        assert TaskTypeEnum.BACKUP not in task_types
        assert TaskTypeEnum.PRUNE in task_types
        assert TaskTypeEnum.CLOUD_SYNC in task_types

    async def test_build_task_list_prune_request_over_config(
        self, task_builder: TaskDefinitionBuilder, mock_db: AsyncSession
    ) -> None:
        """Test that prune request takes precedence over config when both provided"""
        prune_request = MagicMock(spec=PruneRequest)
        prune_request.strategy = "simple"
        prune_request.keep_within_days = 14
        prune_request.dry_run = True

        tasks = await task_builder.build_task_list(
            mock_db,
            repository_name="test-repo",
            include_backup=False,
            prune_config_id=1,  # This should be ignored
            prune_request=prune_request,  # This should be used
        )

        assert len(tasks) == 1
        prune_task = tasks[0]
        assert prune_task.type == TaskTypeEnum.PRUNE
        assert prune_task.parameters["dry_run"] is True
        assert prune_task.parameters["keep_within"] == "14d"

    async def test_build_task_list_check_request_over_config(
        self, task_builder: TaskDefinitionBuilder, mock_db: AsyncSession
    ) -> None:
        """Test that check request takes precedence over config when both provided"""
        check_request = MagicMock(spec=CheckRequest)
        check_request.check_type = "archives_only"
        check_request.verify_data = True

        tasks = await task_builder.build_task_list(
            mock_db,
            repository_name="test-repo",
            include_backup=False,
            check_config_id=1,  # This should be ignored
            check_request=check_request,  # This should be used
        )

        assert len(tasks) == 1
        check_task = tasks[0]
        assert check_task.type == TaskTypeEnum.CHECK
        assert check_task.parameters["check_type"] == "archives_only"
        assert check_task.parameters["verify_data"] is True
