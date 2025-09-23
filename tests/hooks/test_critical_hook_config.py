"""
Tests for HookConfig dataclass and HookConfigParser with critical flags.
"""

import json
import pytest

from src.borgitory.services.hooks.hook_config import HookConfig, HookConfigParser


class TestHookConfig:
    """Test HookConfig dataclass functionality."""

    def test_hook_config_creation_with_defaults(self) -> None:
        """Test creating HookConfig with default values."""
        hook = HookConfig(name="test", command="echo test")

        assert hook.name == "test"
        assert hook.command == "echo test"
        assert hook.timeout == 300
        assert hook.shell == "/bin/bash"
        assert hook.working_directory is None
        assert hook.environment_vars == {}
        assert hook.continue_on_failure is True
        assert hook.log_output is True
        assert hook.critical is False  # NEW: Default critical flag
        assert hook.run_on_job_failure is False  # NEW: Default run_on_job_failure flag

    def test_hook_config_creation_with_critical_flags(self) -> None:
        """Test creating HookConfig with critical flags set."""
        hook = HookConfig(
            name="critical test",
            command="critical command",
            critical=True,
            run_on_job_failure=True,
        )

        assert hook.name == "critical test"
        assert hook.command == "critical command"
        assert hook.critical is True
        assert hook.run_on_job_failure is True

    def test_hook_config_validation_empty_name(self) -> None:
        """Test HookConfig validation fails with empty name."""
        with pytest.raises(ValueError, match="Hook name cannot be empty"):
            HookConfig(name="", command="echo test")

    def test_hook_config_validation_empty_command(self) -> None:
        """Test HookConfig validation fails with empty command."""
        with pytest.raises(ValueError, match="Hook command cannot be empty"):
            HookConfig(name="test", command="")

    def test_hook_config_validation_negative_timeout(self) -> None:
        """Test HookConfig validation fails with negative timeout."""
        with pytest.raises(ValueError, match="Hook timeout must be positive"):
            HookConfig(name="test", command="echo test", timeout=-1)


class TestHookConfigParser:
    """Test HookConfigParser functionality with critical flags."""

    def test_parse_empty_json(self) -> None:
        """Test parsing empty JSON returns empty list."""
        result = HookConfigParser.parse_hooks_json("")
        assert result == []

        result = HookConfigParser.parse_hooks_json("[]")
        assert result == []

    def test_parse_basic_hooks_json(self) -> None:
        """Test parsing basic hooks JSON without critical flags."""
        hooks_json = """[
            {
                "name": "test hook",
                "command": "echo test"
            }
        ]"""

        hooks = HookConfigParser.parse_hooks_json(hooks_json)

        assert len(hooks) == 1
        assert hooks[0].name == "test hook"
        assert hooks[0].command == "echo test"
        assert hooks[0].critical is False  # Should default to False
        assert hooks[0].run_on_job_failure is False  # Should default to False

    def test_parse_hooks_json_with_critical_flags(self) -> None:
        """Test parsing hooks JSON with critical and run_on_job_failure flags."""
        hooks_json = """[
            {
                "name": "critical hook",
                "command": "critical command",
                "critical": true,
                "run_on_job_failure": false
            },
            {
                "name": "failure hook",
                "command": "failure command",
                "critical": false,
                "run_on_job_failure": true
            }
        ]"""

        hooks = HookConfigParser.parse_hooks_json(hooks_json)

        assert len(hooks) == 2

        # First hook - critical
        assert hooks[0].name == "critical hook"
        assert hooks[0].command == "critical command"
        assert hooks[0].critical is True
        assert hooks[0].run_on_job_failure is False

        # Second hook - run on failure
        assert hooks[1].name == "failure hook"
        assert hooks[1].command == "failure command"
        assert hooks[1].critical is False
        assert hooks[1].run_on_job_failure is True

    def test_parse_hooks_json_with_all_fields(self) -> None:
        """Test parsing hooks JSON with all possible fields."""
        hooks_json = """[
            {
                "name": "complex hook",
                "command": "complex command",
                "timeout": 600,
                "shell": "/bin/zsh",
                "working_directory": "/tmp",
                "environment_vars": {"VAR1": "value1"},
                "continue_on_failure": false,
                "log_output": false,
                "critical": true,
                "run_on_job_failure": true
            }
        ]"""

        hooks = HookConfigParser.parse_hooks_json(hooks_json)

        assert len(hooks) == 1
        hook = hooks[0]

        assert hook.name == "complex hook"
        assert hook.command == "complex command"
        assert hook.timeout == 600
        assert hook.shell == "/bin/zsh"
        assert hook.working_directory == "/tmp"
        assert hook.environment_vars == {"VAR1": "value1"}
        assert hook.continue_on_failure is False
        assert hook.log_output is False
        assert hook.critical is True
        assert hook.run_on_job_failure is True

    def test_parse_invalid_json(self) -> None:
        """Test parsing invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            HookConfigParser.parse_hooks_json("invalid json")

    def test_parse_non_array_json(self) -> None:
        """Test parsing non-array JSON raises ValueError."""
        with pytest.raises(ValueError, match="must be a JSON array"):
            HookConfigParser.parse_hooks_json('{"not": "array"}')

    def test_parse_invalid_hook_object(self) -> None:
        """Test parsing invalid hook object raises ValueError."""
        with pytest.raises(ValueError, match="must be a JSON object"):
            HookConfigParser.parse_hooks_json('["not object"]')

    def test_parse_hook_invalid_critical_type(self) -> None:
        """Test parsing hook with invalid critical type raises ValueError."""
        hooks_json = """[
            {
                "name": "test",
                "command": "test",
                "critical": "not boolean"
            }
        ]"""

        with pytest.raises(ValueError, match="critical must be a boolean"):
            HookConfigParser.parse_hooks_json(hooks_json)

    def test_parse_hook_invalid_run_on_job_failure_type(self) -> None:
        """Test parsing hook with invalid run_on_job_failure type raises ValueError."""
        hooks_json = """[
            {
                "name": "test",
                "command": "test",
                "run_on_job_failure": "not boolean"
            }
        ]"""

        with pytest.raises(ValueError, match="run_on_job_failure must be a boolean"):
            HookConfigParser.parse_hooks_json(hooks_json)

    def test_hooks_to_json_with_critical_flags(self) -> None:
        """Test converting hooks to JSON includes critical flags."""
        hooks = [
            HookConfig(
                name="critical hook",
                command="critical command",
                critical=True,
                run_on_job_failure=False,
            ),
            HookConfig(
                name="failure hook",
                command="failure command",
                critical=False,
                run_on_job_failure=True,
            ),
        ]

        json_str = HookConfigParser.hooks_to_json(hooks)
        parsed_data = json.loads(json_str)

        assert len(parsed_data) == 2

        # First hook
        assert parsed_data[0]["name"] == "critical hook"
        assert parsed_data[0]["command"] == "critical command"
        assert parsed_data[0]["critical"] is True
        assert parsed_data[0]["run_on_job_failure"] is False

        # Second hook
        assert parsed_data[1]["name"] == "failure hook"
        assert parsed_data[1]["command"] == "failure command"
        assert parsed_data[1]["critical"] is False
        assert parsed_data[1]["run_on_job_failure"] is True

    def test_hooks_to_json_empty_list(self) -> None:
        """Test converting empty hooks list to JSON."""
        result = HookConfigParser.hooks_to_json([])
        assert result == "[]"

    def test_roundtrip_json_conversion(self) -> None:
        """Test that JSON conversion is bidirectional with critical flags."""
        original_hooks = [
            HookConfig(
                name="test hook",
                command="test command",
                critical=True,
                run_on_job_failure=True,
                timeout=123,
                shell="/bin/custom",
            )
        ]

        # Convert to JSON and back
        json_str = HookConfigParser.hooks_to_json(original_hooks)
        parsed_hooks = HookConfigParser.parse_hooks_json(json_str)

        assert len(parsed_hooks) == 1
        hook = parsed_hooks[0]

        assert hook.name == original_hooks[0].name
        assert hook.command == original_hooks[0].command
        assert hook.critical == original_hooks[0].critical
        assert hook.run_on_job_failure == original_hooks[0].run_on_job_failure
        assert hook.timeout == original_hooks[0].timeout
        assert hook.shell == original_hooks[0].shell
