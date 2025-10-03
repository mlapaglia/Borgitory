"""
Tests for HookService - Business logic for handling pre/post job hooks.
"""

import json
from typing import List, Dict

from borgitory.services.scheduling.hook_service import HookService


class MockFormData:
    """Mock form data for testing."""

    def __init__(self, data: Dict[str, List[str]]) -> None:
        self.data = data

    def getlist(self, key: str) -> List[str]:
        """Mock getlist method."""
        value = self.data.get(key, [])
        return value if isinstance(value, list) else [value] if value else []


class TestHookService:
    """Test suite for HookService."""

    def test_extract_hooks_from_form_empty(self) -> None:
        """Test extracting hooks from empty form data."""
        form_data = MockFormData({})
        hooks = HookService.extract_hooks_from_form(form_data, "pre")
        assert hooks == []

    def test_extract_hooks_from_form_single_hook(self) -> None:
        """Test extracting a single hook from form data."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Test Hook"],
                "pre_hook_command": ["echo 'test'"],
                "pre_hook_critical": ["true"],
                "pre_hook_run_on_failure": ["false"],
            }
        )

        hooks = HookService.extract_hooks_from_form(form_data, "pre")

        assert len(hooks) == 1
        hook = hooks[0]
        assert hook["name"] == "Test Hook"
        assert hook["command"] == "echo 'test'"
        assert hook["critical"] is True
        assert hook["run_on_job_failure"] is False

    def test_extract_hooks_from_form_multiple_hooks(self) -> None:
        """Test extracting multiple hooks from form data."""
        form_data = MockFormData(
            {
                "post_hook_name": ["Hook 1", "Hook 2"],
                "post_hook_command": ["command1", "command2"],
                "post_hook_critical": ["true", "false"],
                "post_hook_run_on_failure": ["false", "true"],
            }
        )

        hooks = HookService.extract_hooks_from_form(form_data, "post")

        assert len(hooks) == 2

        # First hook
        assert hooks[0]["name"] == "Hook 1"
        assert hooks[0]["command"] == "command1"
        assert hooks[0]["critical"] is True
        assert hooks[0]["run_on_job_failure"] is False

        # Second hook
        assert hooks[1]["name"] == "Hook 2"
        assert hooks[1]["command"] == "command2"
        assert hooks[1]["critical"] is False
        assert hooks[1]["run_on_job_failure"] is True

    def test_extract_hooks_from_form_empty_fields(self) -> None:
        """Test extracting hooks with some empty fields."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Valid Hook", ""],
                "pre_hook_command": ["valid command", ""],
                "pre_hook_critical": ["true"],
                "pre_hook_run_on_failure": ["false"],
            }
        )

        hooks = HookService.extract_hooks_from_form(form_data, "pre")

        assert len(hooks) == 2
        assert hooks[0]["name"] == "Valid Hook"
        assert hooks[0]["command"] == "valid command"
        assert hooks[1]["name"] == ""
        assert hooks[1]["command"] == ""

    def test_extract_hooks_from_form_missing_checkboxes(self) -> None:
        """Test extracting hooks when checkboxes are missing (unchecked)."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Hook 1", "Hook 2"],
                "pre_hook_command": ["command1", "command2"],
                "pre_hook_critical": ["true"],  # Only first hook has critical checked
                "pre_hook_run_on_failure": [],  # No hooks have run_on_failure checked
            }
        )

        hooks = HookService.extract_hooks_from_form(form_data, "pre")

        assert len(hooks) == 2
        assert hooks[0]["critical"] is True
        assert hooks[0]["run_on_job_failure"] is False
        assert hooks[1]["critical"] is False  # Missing checkbox = False
        assert hooks[1]["run_on_job_failure"] is False

    def test_convert_hook_fields_to_json_empty(self) -> None:
        """Test converting empty hooks to JSON."""
        form_data = MockFormData({})
        result = HookService.convert_hook_fields_to_json(form_data, "pre")
        assert result is None

    def test_convert_hook_fields_to_json_valid_hooks(self) -> None:
        """Test converting valid hooks to JSON."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Hook 1", "Hook 2"],
                "pre_hook_command": ["command1", "command2"],
                "pre_hook_critical": ["true", "false"],
                "pre_hook_run_on_failure": ["false", "true"],
            }
        )

        result = HookService.convert_hook_fields_to_json(form_data, "pre")

        assert result is not None
        hooks_data = json.loads(result)
        assert len(hooks_data) == 2

        assert hooks_data[0]["name"] == "Hook 1"
        assert hooks_data[0]["command"] == "command1"
        assert hooks_data[0]["critical"] is True
        assert hooks_data[0]["run_on_job_failure"] is False

        assert hooks_data[1]["name"] == "Hook 2"
        assert hooks_data[1]["command"] == "command2"
        assert hooks_data[1]["critical"] is False
        assert hooks_data[1]["run_on_job_failure"] is True

    def test_convert_hook_fields_to_json_filters_empty_hooks(self) -> None:
        """Test that empty hooks are filtered out when converting to JSON."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Valid Hook", "", "Another Valid"],
                "pre_hook_command": ["valid command", "", "another command"],
                "pre_hook_critical": ["true", "false", "true"],
                "pre_hook_run_on_failure": ["false", "true", "false"],
            }
        )

        result = HookService.convert_hook_fields_to_json(form_data, "pre")

        assert result is not None
        hooks_data = json.loads(result)
        assert len(hooks_data) == 2  # Empty hook filtered out
        assert hooks_data[0]["name"] == "Valid Hook"
        assert hooks_data[1]["name"] == "Another Valid"

    def test_validate_hooks_for_save_valid(self) -> None:
        """Test validation with valid hooks."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Test Hook"],
                "pre_hook_command": ["echo test"],
                "post_hook_name": ["Post Hook"],
                "post_hook_command": ["echo post"],
            }
        )

        is_valid, error = HookService.validate_hooks_for_save(form_data)

        assert is_valid is True
        assert error is None

    def test_validate_hooks_for_save_missing_pre_hook_name(self) -> None:
        """Test validation with missing pre-hook name."""
        form_data = MockFormData(
            {"pre_hook_name": [""], "pre_hook_command": ["echo test"]}
        )

        is_valid, error = HookService.validate_hooks_for_save(form_data)

        assert is_valid is False
        assert error is not None
        assert "Pre-hook #1: Hook name is required" in error

    def test_validate_hooks_for_save_missing_post_hook_command(self) -> None:
        """Test validation with missing post-hook command."""
        form_data = MockFormData(
            {"post_hook_name": ["Test Hook"], "post_hook_command": [""]}
        )

        is_valid, error = HookService.validate_hooks_for_save(form_data)

        assert is_valid is False
        assert error is not None
        assert "Post-hook #1: Hook command is required" in error

    def test_validate_hooks_for_save_multiple_errors(self) -> None:
        """Test validation with multiple errors."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["", "Valid Hook"],
                "pre_hook_command": ["echo test", ""],
                "post_hook_name": [""],
                "post_hook_command": ["echo post"],
            }
        )

        is_valid, error = HookService.validate_hooks_for_save(form_data)

        assert is_valid is False
        assert error is not None
        assert "Pre-hook #1: Hook name is required" in error
        assert "Pre-hook #2: Hook command is required" in error
        assert "Post-hook #1: Hook name is required" in error

    def test_validate_hooks_for_save_ignores_empty_hooks(self) -> None:
        """Test that completely empty hooks are ignored during validation."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Valid Hook", ""],
                "pre_hook_command": ["echo test", ""],
                "post_hook_name": [""],
                "post_hook_command": [""],
            }
        )

        is_valid, error = HookService.validate_hooks_for_save(form_data)

        assert is_valid is True
        assert error is None

    def test_convert_hook_fields_to_json_from_dict_format(self) -> None:
        """Test converting hooks from dictionary form data."""
        form_data = {
            "pre_hook_name": ["Hook 1", "Hook 2"],
            "pre_hook_command": ["command1", "command2"],
            "pre_hook_critical": ["true", "false"],
            "pre_hook_run_on_failure": ["false", "true"],
        }

        result = HookService.convert_hook_fields_to_json_from_dict(form_data, "pre")

        assert result is not None
        hooks_data = json.loads(result)
        assert len(hooks_data) == 2
        assert hooks_data[0]["name"] == "Hook 1"
        assert hooks_data[1]["name"] == "Hook 2"

    def test_convert_hook_fields_to_json_from_dict_single_values(self) -> None:
        """Test converting hooks from form data with single values (not lists)."""
        form_data = {
            "pre_hook_name": "Single Hook",
            "pre_hook_command": "echo single",
            "pre_hook_critical": "true",
            "pre_hook_run_on_failure": "false",
        }

        result = HookService.convert_hook_fields_to_json_from_dict(form_data, "pre")

        assert result is not None
        hooks_data = json.loads(result)
        assert len(hooks_data) == 1
        assert hooks_data[0]["name"] == "Single Hook"

    def test_parse_hooks_from_json_empty(self) -> None:
        """Test parsing hooks from empty JSON."""
        hooks = HookService.parse_hooks_from_json("")
        assert hooks == []

        hooks = HookService.parse_hooks_from_json("[]")
        assert hooks == []

    def test_parse_hooks_from_json_valid(self) -> None:
        """Test parsing hooks from valid JSON."""
        json_data = json.dumps(
            [
                {
                    "name": "Hook 1",
                    "command": "echo test",
                    "critical": True,
                    "run_on_job_failure": False,
                },
                {
                    "name": "Hook 2",
                    "command": "echo test2",
                    "critical": False,
                    "run_on_job_failure": True,
                },
            ]
        )

        hooks = HookService.parse_hooks_from_json(json_data)

        assert len(hooks) == 2
        assert hooks[0]["name"] == "Hook 1"
        assert hooks[0]["command"] == "echo test"
        assert hooks[0]["critical"] is True
        assert hooks[0]["run_on_job_failure"] is False

        assert hooks[1]["name"] == "Hook 2"
        assert hooks[1]["command"] == "echo test2"
        assert hooks[1]["critical"] is False
        assert hooks[1]["run_on_job_failure"] is True

    def test_parse_hooks_from_json_invalid(self) -> None:
        """Test parsing hooks from invalid JSON."""
        hooks = HookService.parse_hooks_from_json("invalid json")
        assert hooks == []

        hooks = HookService.parse_hooks_from_json('{"not": "a list"}')
        assert hooks == []

    def test_parse_hooks_from_json_missing_fields(self) -> None:
        """Test parsing hooks with missing fields uses defaults."""
        json_data = json.dumps(
            [
                {
                    "name": "Hook 1",
                    "command": "echo test",
                    # Missing critical and run_on_job_failure
                }
            ]
        )

        hooks = HookService.parse_hooks_from_json(json_data)

        assert len(hooks) == 1
        assert hooks[0]["name"] == "Hook 1"
        assert hooks[0]["command"] == "echo test"
        assert hooks[0]["critical"] is False  # Default
        assert hooks[0]["run_on_job_failure"] is False  # Default

    def test_count_hooks_from_json_empty(self) -> None:
        """Test counting hooks from empty JSON."""
        assert HookService.count_hooks_from_json(None) == 0
        assert HookService.count_hooks_from_json("") == 0
        assert HookService.count_hooks_from_json("[]") == 0

    def test_count_hooks_from_json_valid(self) -> None:
        """Test counting hooks from valid JSON."""
        json_data = json.dumps(
            [
                {"name": "Hook 1", "command": "echo 1"},
                {"name": "Hook 2", "command": "echo 2"},
            ]
        )

        count = HookService.count_hooks_from_json(json_data)
        assert count == 2

    def test_count_hooks_from_json_invalid(self) -> None:
        """Test counting hooks from invalid JSON."""
        assert HookService.count_hooks_from_json("invalid json") == 0
        assert HookService.count_hooks_from_json('{"not": "a list"}') == 0

    def test_validate_hook_data_valid(self) -> None:
        """Test validating valid hook data."""
        hook_data = {
            "name": "Test Hook",
            "command": "echo test",
            "critical": True,
            "run_on_job_failure": False,
        }

        is_valid, error = HookService.validate_hook_data(hook_data)

        assert is_valid is True
        assert error is None

    def test_validate_hook_data_missing_name(self) -> None:
        """Test validating hook data with missing name."""
        hook_data = {
            "command": "echo test",
            "critical": True,
            "run_on_job_failure": False,
        }

        is_valid, error = HookService.validate_hook_data(hook_data)

        assert is_valid is False
        assert error == "Hook name is required"

    def test_validate_hook_data_empty_name(self) -> None:
        """Test validating hook data with empty name."""
        hook_data = {
            "name": "   ",  # Whitespace only
            "command": "echo test",
            "critical": True,
            "run_on_job_failure": False,
        }

        is_valid, error = HookService.validate_hook_data(hook_data)

        assert is_valid is False
        assert error == "Hook name is required"

    def test_validate_hook_data_missing_command(self) -> None:
        """Test validating hook data with missing command."""
        hook_data = {"name": "Test Hook", "critical": True, "run_on_job_failure": False}

        is_valid, error = HookService.validate_hook_data(hook_data)

        assert is_valid is False
        assert error == "Hook command is required"

    def test_validate_hooks_json_empty(self) -> None:
        """Test validating empty hooks JSON."""
        is_valid, error = HookService.validate_hooks_json("")
        assert is_valid is True
        assert error is None

        is_valid, error = HookService.validate_hooks_json("   ")
        assert is_valid is True
        assert error is None

    def test_validate_hooks_json_valid(self) -> None:
        """Test validating valid hooks JSON."""
        json_data = json.dumps(
            [
                {
                    "name": "Hook 1",
                    "command": "echo test",
                    "critical": True,
                    "run_on_job_failure": False,
                }
            ]
        )

        is_valid, error = HookService.validate_hooks_json(json_data)

        assert is_valid is True
        assert error is None

    def test_validate_hooks_json_invalid_format(self) -> None:
        """Test validating invalid JSON format."""
        is_valid, error = HookService.validate_hooks_json("invalid json")

        assert is_valid is False
        assert error == "Invalid JSON format"

    def test_validate_hooks_json_not_list(self) -> None:
        """Test validating JSON that's not a list."""
        is_valid, error = HookService.validate_hooks_json('{"not": "a list"}')

        assert is_valid is False
        assert error == "Hooks must be a list"

    def test_validate_hooks_json_invalid_hook_data(self) -> None:
        """Test validating JSON with invalid hook data."""
        json_data = json.dumps(
            [
                {"name": "Valid Hook", "command": "echo test"},
                {
                    "name": "",  # Invalid: empty name
                    "command": "echo test",
                },
            ]
        )

        is_valid, error = HookService.validate_hooks_json(json_data)

        assert is_valid is False
        assert error is not None
        assert "Hook 2: Hook name is required" in error
