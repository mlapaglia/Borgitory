"""
Tests for hook configuration parsing and validation.
"""

import pytest
from borgitory.services.hooks.hook_config import (
    HookConfig,
    HookConfigParser,
    validate_hooks_json,
)


class TestHookConfig:
    """Test HookConfig dataclass and validation."""

    def test_hook_config_creation_with_defaults(self) -> None:
        """Test creating a hook config with default values."""
        hook = HookConfig(name="Test Hook", command="echo 'hello'")

        assert hook.name == "Test Hook"
        assert hook.command == "echo 'hello'"
        assert hook.timeout == 300
        assert hook.shell == "/bin/bash"
        assert hook.working_directory is None
        assert hook.environment_vars == {}
        assert hook.continue_on_failure is True
        assert hook.log_output is True

    def test_hook_config_creation_with_custom_values(self) -> None:
        """Test creating a hook config with custom values."""
        hook = HookConfig(
            name="Custom Hook",
            command="ls -la",
            timeout=600,
            shell="/bin/sh",
            working_directory="/tmp",
            environment_vars={"VAR1": "value1"},
            continue_on_failure=False,
            log_output=False,
        )

        assert hook.name == "Custom Hook"
        assert hook.command == "ls -la"
        assert hook.timeout == 600
        assert hook.shell == "/bin/sh"
        assert hook.working_directory == "/tmp"
        assert hook.environment_vars == {"VAR1": "value1"}
        assert hook.continue_on_failure is False
        assert hook.log_output is False

    def test_hook_config_validation_empty_name(self) -> None:
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="Hook name cannot be empty"):
            HookConfig(name="", command="echo 'hello'")

    def test_hook_config_validation_empty_command(self) -> None:
        """Test that empty command raises ValueError."""
        with pytest.raises(ValueError, match="Hook command cannot be empty"):
            HookConfig(name="Test Hook", command="")

    def test_hook_config_validation_negative_timeout(self) -> None:
        """Test that negative timeout raises ValueError."""
        with pytest.raises(ValueError, match="Hook timeout must be positive"):
            HookConfig(name="Test Hook", command="echo 'hello'", timeout=-1)


class TestHookConfigParser:
    """Test HookConfigParser JSON parsing functionality."""

    def test_parse_empty_json(self) -> None:
        """Test parsing empty or None JSON returns empty list."""
        assert HookConfigParser.parse_hooks_json(None) == []
        assert HookConfigParser.parse_hooks_json("") == []
        assert HookConfigParser.parse_hooks_json("   ") == []

    def test_parse_valid_single_hook(self) -> None:
        """Test parsing a single valid hook."""
        json_str = '[{"name": "Test Hook", "command": "echo hello"}]'
        hooks = HookConfigParser.parse_hooks_json(json_str)

        assert len(hooks) == 1
        hook = hooks[0]
        assert hook.name == "Test Hook"
        assert hook.command == "echo hello"
        assert hook.timeout == 300  # default

    def test_parse_valid_multiple_hooks(self) -> None:
        """Test parsing multiple valid hooks."""
        json_str = """[
            {
                "name": "Pre Hook",
                "command": "echo starting",
                "timeout": 60
            },
            {
                "name": "Post Hook",
                "command": "echo finished",
                "shell": "/bin/sh",
                "continue_on_failure": false
            }
        ]"""

        hooks = HookConfigParser.parse_hooks_json(json_str)

        assert len(hooks) == 2

        pre_hook = hooks[0]
        assert pre_hook.name == "Pre Hook"
        assert pre_hook.command == "echo starting"
        assert pre_hook.timeout == 60
        assert pre_hook.shell == "/bin/bash"  # default

        post_hook = hooks[1]
        assert post_hook.name == "Post Hook"
        assert post_hook.command == "echo finished"
        assert post_hook.shell == "/bin/sh"
        assert post_hook.continue_on_failure is False

    def test_parse_hook_with_environment_vars(self) -> None:
        """Test parsing hook with environment variables."""
        json_str = """[{
            "name": "Env Hook",
            "command": "echo $TEST_VAR",
            "environment_vars": {
                "TEST_VAR": "test_value",
                "ANOTHER_VAR": "another_value"
            }
        }]"""

        hooks = HookConfigParser.parse_hooks_json(json_str)

        assert len(hooks) == 1
        hook = hooks[0]
        assert hook.name == "Env Hook"
        assert hook.environment_vars == {
            "TEST_VAR": "test_value",
            "ANOTHER_VAR": "another_value",
        }

    def test_parse_invalid_json(self) -> None:
        """Test that invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            HookConfigParser.parse_hooks_json('{"invalid": json}')

    def test_parse_non_array_json(self) -> None:
        """Test that non-array JSON raises ValueError."""
        with pytest.raises(ValueError, match="must be a JSON array"):
            HookConfigParser.parse_hooks_json('{"name": "hook"}')

    def test_parse_non_object_hook(self) -> None:
        """Test that non-object hook raises ValueError."""
        with pytest.raises(ValueError, match="Hook 0 must be a JSON object"):
            HookConfigParser.parse_hooks_json('["string_instead_of_object"]')

    def test_parse_missing_required_fields(self) -> None:
        """Test that missing required fields raises ValueError."""
        with pytest.raises(ValueError, match="Hook name cannot be empty"):
            HookConfigParser.parse_hooks_json('[{"command": "echo hello"}]')

        with pytest.raises(ValueError, match="Hook command cannot be empty"):
            HookConfigParser.parse_hooks_json('[{"name": "Test"}]')

    def test_parse_invalid_field_types(self) -> None:
        """Test that invalid field types raise ValueError."""
        # Invalid name type
        with pytest.raises(ValueError, match="Hook 0 name must be a string"):
            HookConfigParser.parse_hooks_json('[{"name": 123, "command": "echo"}]')

        # Invalid timeout type
        with pytest.raises(ValueError, match="Hook 0 timeout must be an integer"):
            HookConfigParser.parse_hooks_json(
                '[{"name": "test", "command": "echo", "timeout": "invalid"}]'
            )

    def test_hooks_to_json_empty_list(self) -> None:
        """Test converting empty list to JSON."""
        result = HookConfigParser.hooks_to_json([])
        assert result == "[]"

    def test_hooks_to_json_single_hook(self) -> None:
        """Test converting single hook to JSON."""
        hook = HookConfig(name="Test Hook", command="echo hello")
        result = HookConfigParser.hooks_to_json([hook])

        import json

        parsed = json.loads(result)

        assert len(parsed) == 1
        assert parsed[0]["name"] == "Test Hook"
        assert parsed[0]["command"] == "echo hello"
        assert parsed[0]["timeout"] == 300
        assert parsed[0]["shell"] == "/bin/bash"

    def test_hooks_to_json_with_optional_fields(self) -> None:
        """Test converting hook with optional fields to JSON."""
        hook = HookConfig(
            name="Complex Hook",
            command="ls -la",
            working_directory="/tmp",
            environment_vars={"VAR": "value"},
        )
        result = HookConfigParser.hooks_to_json([hook])

        import json

        parsed = json.loads(result)

        assert parsed[0]["working_directory"] == "/tmp"
        assert parsed[0]["environment_vars"] == {"VAR": "value"}


class TestValidateHooksJson:
    """Test the validate_hooks_json convenience function."""

    def test_validate_empty_json(self) -> None:
        """Test validating empty JSON returns True."""
        is_valid, error = validate_hooks_json(None)
        assert is_valid is True
        assert error is None

        is_valid, error = validate_hooks_json("")
        assert is_valid is True
        assert error is None

    def test_validate_valid_json(self) -> None:
        """Test validating valid JSON returns True."""
        json_str = '[{"name": "Test", "command": "echo hello"}]'
        is_valid, error = validate_hooks_json(json_str)

        assert is_valid is True
        assert error is None

    def test_validate_invalid_json(self) -> None:
        """Test validating invalid JSON returns False with error message."""
        json_str = '[{"name": "Test"}]'  # Missing command
        is_valid, error = validate_hooks_json(json_str)

        assert is_valid is False
        assert error is not None
        assert "Hook command cannot be empty" in error
