"""
Tests for hook integration with TaskDefinitionBuilder.
"""

from unittest.mock import Mock
from sqlalchemy.orm import Session

from borgitory.services.task_definition_builder import TaskDefinitionBuilder


class TestTaskDefinitionBuilderHookIntegration:
    """Test hook integration with TaskDefinitionBuilder."""

    def test_build_hook_task(self) -> None:
        """Test building a single hook task definition."""
        mock_db = Mock(spec=Session)
        builder = TaskDefinitionBuilder(mock_db)

        task = builder.build_hook_task(
            hook_name="Test Hook",
            hook_command="echo 'hello'",
            hook_type="pre",
            repository_name="test-repo",
        )

        assert task["type"] == "hook"
        assert task["name"] == "Pre-job hook: Test Hook (test-repo)"
        assert task["hook_name"] == "Test Hook"
        assert task["hook_command"] == "echo 'hello'"
        assert task["hook_type"] == "pre"

    def test_build_hook_task_without_repository_name(self) -> None:
        """Test building hook task without repository name."""
        mock_db = Mock(spec=Session)
        builder = TaskDefinitionBuilder(mock_db)

        task = builder.build_hook_task(
            hook_name="Simple Hook", hook_command="ls -la", hook_type="post"
        )

        assert task["name"] == "Post-job hook: Simple Hook"

    def test_build_hooks_from_json_empty(self) -> None:
        """Test building hooks from empty JSON."""
        mock_db = Mock(spec=Session)
        builder = TaskDefinitionBuilder(mock_db)

        tasks = builder.build_hooks_from_json(None, "pre")
        assert tasks == []

        tasks = builder.build_hooks_from_json("", "post")
        assert tasks == []

    def test_build_hooks_from_json_valid(self) -> None:
        """Test building hooks from valid JSON."""
        mock_db = Mock(spec=Session)
        builder = TaskDefinitionBuilder(mock_db)

        hooks_json = """[
            {
                "name": "Pre Hook 1",
                "command": "echo starting"
            },
            {
                "name": "Pre Hook 2", 
                "command": "mkdir -p /tmp/backup"
            }
        ]"""

        tasks = builder.build_hooks_from_json(hooks_json, "pre", "test-repo")

        assert len(tasks) == 2

        assert tasks[0]["type"] == "hook"
        assert tasks[0]["hook_name"] == "Pre Hook 1"
        assert tasks[0]["hook_command"] == "echo starting"
        assert tasks[0]["hook_type"] == "pre"

        assert tasks[1]["type"] == "hook"
        assert tasks[1]["hook_name"] == "Pre Hook 2"
        assert tasks[1]["hook_command"] == "mkdir -p /tmp/backup"
        assert tasks[1]["hook_type"] == "pre"

    def test_build_hooks_from_json_invalid(self, caplog) -> None:
        """Test building hooks from invalid JSON logs error and returns empty list."""
        mock_db = Mock(spec=Session)
        builder = TaskDefinitionBuilder(mock_db)

        invalid_json = '[{"name": "Test", "invalid": "json"}]'  # Missing command

        with caplog.at_level("ERROR"):
            tasks = builder.build_hooks_from_json(invalid_json, "pre", "test-repo")

        assert tasks == []
        assert "Failed to parse pre-job hooks" in caplog.text

    def test_build_task_list_with_hooks(self) -> None:
        """Test building complete task list with pre and post hooks."""
        mock_db = Mock(spec=Session)
        builder = TaskDefinitionBuilder(mock_db)

        pre_hooks = '[{"name": "Pre Hook", "command": "echo starting"}]'
        post_hooks = '[{"name": "Post Hook", "command": "echo finished"}]'

        tasks = builder.build_task_list(
            repository_name="test-repo",
            include_backup=True,
            backup_params={
                "source_path": "/data",
                "compression": "zstd",
                "dry_run": False,
                "ignore_lock": False,
            },
            pre_job_hooks=pre_hooks,
            post_job_hooks=post_hooks,
        )

        # Should have: pre-hook, backup, post-hook
        assert len(tasks) >= 3

        # First task should be pre-hook
        assert tasks[0]["type"] == "hook"
        assert tasks[0]["hook_type"] == "pre"
        assert tasks[0]["hook_name"] == "Pre Hook"

        # Last task should be post-hook
        assert tasks[-1]["type"] == "hook"
        assert tasks[-1]["hook_type"] == "post"
        assert tasks[-1]["hook_name"] == "Post Hook"

        # Should have backup task somewhere in the middle
        backup_tasks = [task for task in tasks if task["type"] == "backup"]
        assert len(backup_tasks) == 1

    def test_build_task_list_with_hooks_and_other_tasks(self) -> None:
        """Test building task list with hooks and other task types."""
        mock_db = Mock(spec=Session)
        builder = TaskDefinitionBuilder(mock_db)

        # Mock cleanup config
        mock_cleanup_config = Mock()
        mock_cleanup_config.strategy = "simple"
        mock_cleanup_config.keep_within_days = 30
        mock_cleanup_config.show_list = True
        mock_cleanup_config.show_stats = True
        mock_cleanup_config.save_space = False

        mock_db.query.return_value.filter.return_value.first.return_value = (
            mock_cleanup_config
        )

        pre_hooks = '[{"name": "Setup", "command": "echo setup"}]'
        post_hooks = '[{"name": "Cleanup", "command": "echo cleanup"}]'

        tasks = builder.build_task_list(
            repository_name="test-repo",
            include_backup=True,
            cleanup_config_id=1,
            include_cloud_sync=True,
            cloud_sync_config_id=1,
            pre_job_hooks=pre_hooks,
            post_job_hooks=post_hooks,
        )

        # Extract task types in order
        task_types = [task["type"] for task in tasks]

        # Should start with pre-hook and end with post-hook
        assert task_types[0] == "hook"
        assert task_types[-1] == "hook"

        # Should contain all expected task types
        assert "backup" in task_types
        assert "prune" in task_types
        assert "cloud_sync" in task_types

        # Verify hooks are correctly positioned
        pre_hook_task = tasks[0]
        assert pre_hook_task["hook_type"] == "pre"
        assert pre_hook_task["hook_name"] == "Setup"

        post_hook_task = tasks[-1]
        assert post_hook_task["hook_type"] == "post"
        assert post_hook_task["hook_name"] == "Cleanup"
