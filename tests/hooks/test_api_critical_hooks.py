"""
Tests for API endpoints handling critical and run_on_job_failure flags.
"""

import json
from typing import Dict, List, Any

from src.borgitory.api.schedules import (
    convert_hook_fields_to_json,
    _extract_hooks_from_form,
    _convert_hook_fields_to_json,
    _validate_hooks_for_save,
)


class MockFormData:
    """Mock FormData for testing."""

    def __init__(self, data: Dict[str, List[str]]) -> None:
        self.data = data

    def getlist(self, key: str) -> List[str]:
        """Mock getlist method."""
        return self.data.get(key, [])

    def get(self, key: str, default: Any = None) -> Any:
        """Mock get method."""
        values = self.data.get(key, [])
        return values[0] if values else default


class TestAPIHookCriticalFlags:
    """Test API functions for handling critical and run_on_job_failure flags."""

    def test_convert_hook_fields_to_json_with_critical_flags(self) -> None:
        """Test convert_hook_fields_to_json includes critical flags."""
        form_data = {
            "pre_hook_name": ["Critical Hook", "Normal Hook"],
            "pre_hook_command": ["critical command", "normal command"],
            "pre_hook_critical": ["true", "false"],
            "pre_hook_run_on_failure": ["false", "true"],
        }

        result = convert_hook_fields_to_json(form_data, "pre")

        assert result is not None
        hooks = json.loads(result)
        assert len(hooks) == 2

        # First hook - critical
        assert hooks[0]["name"] == "Critical Hook"
        assert hooks[0]["command"] == "critical command"
        assert hooks[0]["critical"] is True
        assert hooks[0]["run_on_job_failure"] is False

        # Second hook - run on failure
        assert hooks[1]["name"] == "Normal Hook"
        assert hooks[1]["command"] == "normal command"
        assert hooks[1]["critical"] is False
        assert hooks[1]["run_on_job_failure"] is True

    def test_convert_hook_fields_to_json_missing_critical_flags(self) -> None:
        """Test convert_hook_fields_to_json handles missing critical flags."""
        form_data = {
            "pre_hook_name": ["Test Hook"],
            "pre_hook_command": ["test command"],
            # Missing critical and run_on_job_failure
        }

        result = convert_hook_fields_to_json(form_data, "pre")

        assert result is not None
        hooks = json.loads(result)
        assert len(hooks) == 1

        # Should default to False
        assert hooks[0]["critical"] is False
        assert hooks[0]["run_on_job_failure"] is False

    def test_convert_hook_fields_to_json_partial_critical_flags(self) -> None:
        """Test convert_hook_fields_to_json handles partial critical flags."""
        form_data = {
            "pre_hook_name": ["Hook 1", "Hook 2", "Hook 3"],
            "pre_hook_command": ["cmd1", "cmd2", "cmd3"],
            "pre_hook_critical": ["true"],  # Only first hook has critical flag
            "pre_hook_run_on_failure": [
                "true",
                "true",
            ],  # Only first two have run_on_failure
        }

        result = convert_hook_fields_to_json(form_data, "pre")

        assert result is not None
        hooks = json.loads(result)
        assert len(hooks) == 3

        # First hook - has critical flag
        assert hooks[0]["critical"] is True
        assert hooks[0]["run_on_job_failure"] is True

        # Second hook - no critical flag, has run_on_failure
        assert hooks[1]["critical"] is False
        assert hooks[1]["run_on_job_failure"] is True

        # Third hook - no flags
        assert hooks[2]["critical"] is False
        assert hooks[2]["run_on_job_failure"] is False

    def test_convert_hook_fields_to_json_single_hook(self) -> None:
        """Test convert_hook_fields_to_json with single hook (not list)."""
        form_data = {
            "post_hook_name": "Single Hook",
            "post_hook_command": "single command",
            "post_hook_critical": "true",
            "post_hook_run_on_failure": "true",
        }

        result = convert_hook_fields_to_json(form_data, "post")

        assert result is not None
        hooks = json.loads(result)
        assert len(hooks) == 1

        assert hooks[0]["name"] == "Single Hook"
        assert hooks[0]["command"] == "single command"
        assert hooks[0]["critical"] is True
        assert hooks[0]["run_on_job_failure"] is True

    def test_convert_hook_fields_to_json_empty_hooks(self) -> None:
        """Test convert_hook_fields_to_json with empty hooks."""
        form_data = {
            "pre_hook_name": [""],
            "pre_hook_command": [""],
            "pre_hook_critical": ["true"],
        }

        result = convert_hook_fields_to_json(form_data, "pre")

        # Should return None for empty hooks
        assert result is None

    def test_extract_hooks_from_form_with_critical_flags(self) -> None:
        """Test _extract_hooks_from_form includes critical flags."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Critical Hook", "Normal Hook"],
                "pre_hook_command": ["critical command", "normal command"],
                "pre_hook_critical": ["true"],  # Only first hook
                "pre_hook_run_on_failure": ["false", "true"],  # Both hooks
            }
        )

        hooks = _extract_hooks_from_form(form_data, "pre")

        assert len(hooks) == 2

        # First hook
        assert hooks[0]["name"] == "Critical Hook"
        assert hooks[0]["command"] == "critical command"
        assert hooks[0]["critical"] is True
        assert hooks[0]["run_on_job_failure"] is False

        # Second hook
        assert hooks[1]["name"] == "Normal Hook"
        assert hooks[1]["command"] == "normal command"
        assert hooks[1]["critical"] is False  # No critical flag for this hook
        assert hooks[1]["run_on_job_failure"] is True

    def test_extract_hooks_from_form_empty_hooks(self) -> None:
        """Test _extract_hooks_from_form with empty hooks."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["", "Valid Hook"],
                "pre_hook_command": ["", "valid command"],
                "pre_hook_critical": ["true", "false"],
            }
        )

        hooks = _extract_hooks_from_form(form_data, "pre")

        assert len(hooks) == 2

        # First hook - empty
        assert hooks[0]["name"] == ""
        assert hooks[0]["command"] == ""
        assert hooks[0]["critical"] is True

        # Second hook - valid
        assert hooks[1]["name"] == "Valid Hook"
        assert hooks[1]["command"] == "valid command"
        assert hooks[1]["critical"] is False

    def test_convert_hook_fields_to_json_private_function(self) -> None:
        """Test _convert_hook_fields_to_json (private function) with critical flags."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Test Hook"],
                "pre_hook_command": ["test command"],
                "pre_hook_critical": ["true"],
                "pre_hook_run_on_failure": ["false"],
            }
        )

        result = _convert_hook_fields_to_json(form_data, "pre")

        assert result is not None
        hooks = json.loads(result)
        assert len(hooks) == 1

        assert hooks[0]["name"] == "Test Hook"
        assert hooks[0]["critical"] is True
        assert hooks[0]["run_on_job_failure"] is False

    def test_validate_hooks_for_save_with_critical_hooks(self) -> None:
        """Test _validate_hooks_for_save with critical hooks."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Critical Hook", ""],
                "pre_hook_command": ["critical command", ""],
                "pre_hook_critical": ["true", "false"],
                "post_hook_name": ["Post Hook"],
                "post_hook_command": ["post command"],
                "post_hook_run_on_failure": ["true"],
            }
        )

        is_valid, error_msg = _validate_hooks_for_save(form_data)

        # Should be valid - empty hooks are filtered out
        assert is_valid is True
        assert error_msg is None

    def test_validate_hooks_for_save_critical_hook_missing_command(self) -> None:
        """Test _validate_hooks_for_save with critical hook missing command."""
        form_data = MockFormData(
            {
                "pre_hook_name": ["Critical Hook"],
                "pre_hook_command": [""],  # Missing command
                "pre_hook_critical": ["true"],
            }
        )

        is_valid, error_msg = _validate_hooks_for_save(form_data)

        assert is_valid is False
        assert "Hook command is required" in error_msg

    def test_validate_hooks_for_save_critical_hook_missing_name(self) -> None:
        """Test _validate_hooks_for_save with critical hook missing name."""
        form_data = MockFormData(
            {
                "pre_hook_name": [""],  # Missing name
                "pre_hook_command": ["critical command"],
                "pre_hook_critical": ["true"],
            }
        )

        is_valid, error_msg = _validate_hooks_for_save(form_data)

        assert is_valid is False
        assert "Hook name is required" in error_msg

    def test_hook_checkbox_handling_true_values(self) -> None:
        """Test that checkbox values are correctly interpreted."""
        # Test various ways checkboxes might be submitted
        test_cases = [
            (["true"], True),
            (["on"], False),  # Should be "true", not "on"
            (["1"], False),  # Should be "true", not "1"
            ([], False),  # No checkbox submitted
        ]

        for checkbox_value, expected_result in test_cases:
            form_data = {
                "pre_hook_name": ["Test Hook"],
                "pre_hook_command": ["test command"],
                "pre_hook_critical": checkbox_value,
            }

            result = convert_hook_fields_to_json(form_data, "pre")
            hooks = json.loads(result) if result else []

            if hooks:
                assert hooks[0]["critical"] is expected_result, (
                    f"Failed for checkbox value: {checkbox_value}"
                )

    def test_post_hook_run_on_job_failure_flag(self) -> None:
        """Test post-hook run_on_job_failure flag handling."""
        form_data = {
            "post_hook_name": ["Cleanup Hook", "Notification Hook"],
            "post_hook_command": ["cleanup", "notify"],
            "post_hook_critical": ["false", "false"],
            "post_hook_run_on_failure": ["true", "false"],
        }

        result = convert_hook_fields_to_json(form_data, "post")

        assert result is not None
        hooks = json.loads(result)
        assert len(hooks) == 2

        # First hook - runs on failure
        assert hooks[0]["name"] == "Cleanup Hook"
        assert hooks[0]["run_on_job_failure"] is True
        assert hooks[0]["critical"] is False

        # Second hook - doesn't run on failure
        assert hooks[1]["name"] == "Notification Hook"
        assert hooks[1]["run_on_job_failure"] is False
        assert hooks[1]["critical"] is False

    def test_mixed_critical_and_run_on_failure_flags(self) -> None:
        """Test hooks with mixed critical and run_on_job_failure flags."""
        form_data = {
            "pre_hook_name": ["Critical Pre", "Normal Pre"],
            "pre_hook_command": ["critical pre", "normal pre"],
            "pre_hook_critical": ["true", "false"],
            "post_hook_name": ["Failure Cleanup", "Success Only"],
            "post_hook_command": ["cleanup", "success"],
            "post_hook_critical": ["false", "false"],
            "post_hook_run_on_failure": ["true", "false"],
        }

        # Test pre-hooks
        pre_result = convert_hook_fields_to_json(form_data, "pre")
        pre_hooks = json.loads(pre_result)

        assert pre_hooks[0]["critical"] is True
        assert pre_hooks[0]["run_on_job_failure"] is False  # Default for pre-hooks
        assert pre_hooks[1]["critical"] is False
        assert pre_hooks[1]["run_on_job_failure"] is False

        # Test post-hooks
        post_result = convert_hook_fields_to_json(form_data, "post")
        post_hooks = json.loads(post_result)

        assert post_hooks[0]["critical"] is False
        assert post_hooks[0]["run_on_job_failure"] is True
        assert post_hooks[1]["critical"] is False
        assert post_hooks[1]["run_on_job_failure"] is False
