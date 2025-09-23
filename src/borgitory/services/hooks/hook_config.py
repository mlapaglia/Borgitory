"""
Hook configuration types and validation.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HookConfig:
    """Configuration for a single hook command."""

    name: str
    command: str
    timeout: int = 300  # 5 minutes default
    shell: str = "/bin/bash"
    working_directory: Optional[str] = None
    environment_vars: Dict[str, str] = field(default_factory=dict)
    continue_on_failure: bool = True
    log_output: bool = True
    critical: bool = False
    run_on_job_failure: bool = False

    def __post_init__(self) -> None:
        """Validate hook configuration after initialization."""
        if not self.name.strip():
            raise ValueError("Hook name cannot be empty")
        if not self.command.strip():
            raise ValueError("Hook command cannot be empty")
        if self.timeout <= 0:
            raise ValueError("Hook timeout must be positive")


class HookConfigParser:
    """Parser for hook configuration JSON data."""

    @staticmethod
    def parse_hooks_json(hooks_json: Optional[str]) -> List[HookConfig]:
        """
        Parse JSON string into list of HookConfig objects.

        Args:
            hooks_json: JSON string containing hook configurations

        Returns:
            List of validated HookConfig objects

        Raises:
            ValueError: If JSON is invalid or hook configs are malformed
        """
        if not hooks_json or not hooks_json.strip():
            return []

        try:
            hooks_data = json.loads(hooks_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in hooks configuration: {e}")

        if not isinstance(hooks_data, list):
            raise ValueError("Hooks configuration must be a JSON array")

        hooks = []
        for i, hook_data in enumerate(hooks_data):
            if not isinstance(hook_data, dict):
                raise ValueError(f"Hook {i} must be a JSON object")

            try:
                # Extract required fields
                name = hook_data.get("name", "")
                command = hook_data.get("command", "")

                # Extract optional fields with defaults
                timeout = hook_data.get("timeout", 300)
                shell = hook_data.get("shell", "/bin/bash")
                working_directory = hook_data.get("working_directory")
                environment_vars = hook_data.get("environment_vars", {})
                continue_on_failure = hook_data.get("continue_on_failure", True)
                log_output = hook_data.get("log_output", True)
                critical = hook_data.get("critical", False)
                run_on_job_failure = hook_data.get("run_on_job_failure", False)

                # Validate types
                if not isinstance(name, str):
                    raise ValueError(f"Hook {i} name must be a string")
                if not isinstance(command, str):
                    raise ValueError(f"Hook {i} command must be a string")
                if not isinstance(timeout, int):
                    raise ValueError(f"Hook {i} timeout must be an integer")
                if not isinstance(shell, str):
                    raise ValueError(f"Hook {i} shell must be a string")
                if working_directory is not None and not isinstance(
                    working_directory, str
                ):
                    raise ValueError(
                        f"Hook {i} working_directory must be a string or null"
                    )
                if not isinstance(environment_vars, dict):
                    raise ValueError(f"Hook {i} environment_vars must be an object")
                if not isinstance(continue_on_failure, bool):
                    raise ValueError(f"Hook {i} continue_on_failure must be a boolean")
                if not isinstance(log_output, bool):
                    raise ValueError(f"Hook {i} log_output must be a boolean")
                if not isinstance(critical, bool):
                    raise ValueError(f"Hook {i} critical must be a boolean")
                if not isinstance(run_on_job_failure, bool):
                    raise ValueError(f"Hook {i} run_on_job_failure must be a boolean")

                hook = HookConfig(
                    name=name,
                    command=command,
                    timeout=timeout,
                    shell=shell,
                    working_directory=working_directory,
                    environment_vars=environment_vars,
                    continue_on_failure=continue_on_failure,
                    log_output=log_output,
                    critical=critical,
                    run_on_job_failure=run_on_job_failure,
                )
                hooks.append(hook)

            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid configuration for hook {i}: {e}")

        return hooks

    @staticmethod
    def hooks_to_json(hooks: List[HookConfig]) -> str:
        """
        Convert list of HookConfig objects to JSON string.

        Args:
            hooks: List of HookConfig objects

        Returns:
            JSON string representation
        """
        if not hooks:
            return "[]"

        hooks_data = []
        for hook in hooks:
            hook_dict = {
                "name": hook.name,
                "command": hook.command,
                "timeout": hook.timeout,
                "shell": hook.shell,
                "continue_on_failure": hook.continue_on_failure,
                "log_output": hook.log_output,
                "critical": hook.critical,
                "run_on_job_failure": hook.run_on_job_failure,
            }

            if hook.working_directory:
                hook_dict["working_directory"] = hook.working_directory

            if hook.environment_vars:
                hook_dict["environment_vars"] = hook.environment_vars

            hooks_data.append(hook_dict)

        return json.dumps(hooks_data, indent=2)


def validate_hooks_json(hooks_json: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Validate hooks JSON configuration.

    Args:
        hooks_json: JSON string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not hooks_json or not hooks_json.strip():
        return True, None

    try:
        HookConfigParser.parse_hooks_json(hooks_json)
        return True, None
    except ValueError as e:
        return False, str(e)
