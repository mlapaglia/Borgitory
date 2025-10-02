"""
Hook Service - Business logic for handling pre/post job hooks.

This service encapsulates all hook-related operations including:
- Converting form data to hook objects
- Validating hooks
- Converting hooks to JSON format
- Extracting hooks from various data sources
"""

import json
from typing import List, Dict, Any, Optional


class HookService:
    """Service for handling pre/post job hook operations."""

    @staticmethod
    def extract_hooks_from_form(form_data: Any, hook_type: str) -> List[Dict[str, Any]]:
        """
        Extract hooks from form data and return as list of dicts.

        Args:
            form_data: Form data containing hook fields
            hook_type: Type of hook ("pre" or "post")

        Returns:
            List of hook dictionaries
        """
        hooks = []

        # Get all names and commands for this hook type
        hook_names = form_data.getlist(f"{hook_type}_hook_name")
        hook_commands = form_data.getlist(f"{hook_type}_hook_command")
        hook_critical = form_data.getlist(f"{hook_type}_hook_critical")
        hook_run_on_failure = form_data.getlist(f"{hook_type}_hook_run_on_failure")

        # Pair them up by position
        for i in range(min(len(hook_names), len(hook_commands))):
            name = str(hook_names[i]).strip() if hook_names[i] else ""
            command = str(hook_commands[i]).strip() if hook_commands[i] else ""

            # Handle checkboxes - they're only present if checked
            critical = len(hook_critical) > i and hook_critical[i] == "true"
            run_on_failure = (
                len(hook_run_on_failure) > i and hook_run_on_failure[i] == "true"
            )

            # Add all hooks, even if name or command is empty (for reordering)
            hooks.append(
                {
                    "name": name,
                    "command": command,
                    "critical": critical,
                    "run_on_job_failure": run_on_failure,
                }
            )

        return hooks

    @staticmethod
    def convert_hook_fields_to_json(form_data: Any, hook_type: str) -> Optional[str]:
        """
        Convert individual hook fields to JSON format using position-based form data.

        Args:
            form_data: Form data containing hook fields
            hook_type: Type of hook ("pre" or "post")

        Returns:
            JSON string of valid hooks or None if no valid hooks
        """
        hooks = HookService.extract_hooks_from_form(form_data, hook_type)

        # Filter out hooks that don't have both name and command for JSON output
        valid_hooks = [hook for hook in hooks if hook["name"] and hook["command"]]

        return json.dumps(valid_hooks) if valid_hooks else None

    @staticmethod
    def validate_hooks_for_save(form_data: Any) -> tuple[bool, Optional[str]]:
        """
        Validate that all hooks have both name and command filled out.

        Args:
            form_data: Form data containing hook fields

        Returns:
            Tuple of (is_valid, error_message)
        """
        errors = []

        # Check pre-hooks
        pre_hooks = HookService.extract_hooks_from_form(form_data, "pre")
        for i, hook in enumerate(pre_hooks):
            if not hook["name"].strip() and not hook["command"].strip():
                # Empty hook - skip (will be filtered out)
                continue
            elif not hook["name"].strip():
                errors.append(f"Pre-hook #{i + 1}: Hook name is required")
            elif not hook["command"].strip():
                errors.append(f"Pre-hook #{i + 1}: Hook command is required")

        # Check post-hooks
        post_hooks = HookService.extract_hooks_from_form(form_data, "post")
        for i, hook in enumerate(post_hooks):
            if not hook["name"].strip() and not hook["command"].strip():
                # Empty hook - skip (will be filtered out)
                continue
            elif not hook["name"].strip():
                errors.append(f"Post-hook #{i + 1}: Hook name is required")
            elif not hook["command"].strip():
                errors.append(f"Post-hook #{i + 1}: Hook command is required")

        if errors:
            return False, "; ".join(errors)
        return True, None

    @staticmethod
    def convert_hook_fields_to_json_from_dict(
        form_data: Dict[str, Any], hook_type: str
    ) -> Optional[str]:
        """
        Convert individual hook fields to JSON format using position-based form data from dict.

        Args:
            form_data: Dictionary containing hook form data
            hook_type: Type of hook ("pre" or "post")

        Returns:
            JSON string of hooks or None if no hooks
        """
        hooks = []

        # Get all hook field data for this hook type (position-based)
        hook_names = form_data.get(f"{hook_type}_hook_name", [])
        hook_commands = form_data.get(f"{hook_type}_hook_command", [])
        hook_critical = form_data.get(f"{hook_type}_hook_critical", [])
        hook_run_on_failure = form_data.get(f"{hook_type}_hook_run_on_failure", [])

        # Ensure they are lists (in case there's only one item)
        if not isinstance(hook_names, list):
            hook_names = [hook_names] if hook_names else []
        if not isinstance(hook_commands, list):
            hook_commands = [hook_commands] if hook_commands else []
        if not isinstance(hook_critical, list):
            hook_critical = [hook_critical] if hook_critical else []
        if not isinstance(hook_run_on_failure, list):
            hook_run_on_failure = [hook_run_on_failure] if hook_run_on_failure else []

        # Pair them up by position
        for i in range(min(len(hook_names), len(hook_commands))):
            name = str(hook_names[i]).strip() if hook_names[i] else ""
            command = str(hook_commands[i]).strip() if hook_commands[i] else ""

            # Handle checkboxes - they're only present if checked
            critical = len(hook_critical) > i and hook_critical[i] == "true"
            run_on_failure = (
                len(hook_run_on_failure) > i and hook_run_on_failure[i] == "true"
            )

            # Only add hooks that have both name and command
            if name and command:
                hooks.append(
                    {
                        "name": name,
                        "command": command,
                        "critical": critical,
                        "run_on_job_failure": run_on_failure,
                    }
                )

        return json.dumps(hooks) if hooks else None

    @staticmethod
    def parse_hooks_from_json(hooks_json: str) -> List[Dict[str, Any]]:
        """
        Parse hooks from JSON string into list of hook dictionaries.

        Args:
            hooks_json: JSON string containing hook data

        Returns:
            List of hook dictionaries
        """
        if not hooks_json or hooks_json.strip() == "[]":
            return []

        try:
            hooks_data = json.loads(hooks_json)
            if not isinstance(hooks_data, list):
                return []

            hooks = []
            for hook_data in hooks_data:
                if isinstance(hook_data, dict):
                    hooks.append(
                        {
                            "name": hook_data.get("name", ""),
                            "command": hook_data.get("command", ""),
                            "critical": bool(hook_data.get("critical", False)),
                            "run_on_job_failure": bool(
                                hook_data.get("run_on_job_failure", False)
                            ),
                        }
                    )
            return hooks
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def count_hooks_from_json(hooks_json: Optional[str]) -> int:
        """
        Count the number of hooks in a JSON string.

        Args:
            hooks_json: JSON string containing hook data

        Returns:
            Number of hooks
        """
        if not hooks_json:
            return 0

        try:
            hooks_data = json.loads(hooks_json)
            return len(hooks_data) if isinstance(hooks_data, list) else 0
        except (json.JSONDecodeError, TypeError):
            return 0

    @staticmethod
    def validate_hook_data(hook_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate a single hook data dictionary.

        Args:
            hook_data: Dictionary containing hook data

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(hook_data, dict):
            return False, "Hook data must be a dictionary"

        name = hook_data.get("name", "").strip()
        command = hook_data.get("command", "").strip()

        if not name:
            return False, "Hook name is required"

        if not command:
            return False, "Hook command is required"

        return True, None

    @staticmethod
    def validate_hooks_json(hooks_json: str) -> tuple[bool, Optional[str]]:
        """
        Validate hooks JSON string.

        Args:
            hooks_json: JSON string containing hook data

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not hooks_json or hooks_json.strip() == "":
            return True, None

        try:
            hooks_data = json.loads(hooks_json)

            if not isinstance(hooks_data, list):
                return False, "Hooks must be a list"

            for i, hook_data in enumerate(hooks_data):
                is_valid, error = HookService.validate_hook_data(hook_data)
                if not is_valid:
                    return False, f"Hook {i + 1}: {error}"

            return True, None

        except json.JSONDecodeError:
            return False, "Invalid JSON format"
        except Exception as e:
            return False, f"Validation error: {str(e)}"
