"""
Configuration for command runner services.

This module provides configuration classes for command execution services,
supporting environment-based configuration and dependency injection.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandRunnerConfig:
    """Configuration for command runner services."""

    timeout: int = 300
    max_retries: int = 3
    log_commands: bool = True
    buffer_size: int = 8192

    @classmethod
    def from_env(cls, prefix: str = "COMMAND") -> "CommandRunnerConfig":
        """
        Create configuration from environment variables.

        Args:
            prefix: Environment variable prefix (default: COMMAND)

        Returns:
            CommandRunnerConfig instance with values from environment

        Environment Variables:
            COMMAND_TIMEOUT: Command timeout in seconds (default: 300)
            COMMAND_MAX_RETRIES: Maximum retry attempts (default: 3)
            COMMAND_LOG_COMMANDS: Whether to log commands (default: true)
            COMMAND_BUFFER_SIZE: Buffer size for command output (default: 8192)
        """
        return cls(
            timeout=int(os.getenv(f"{prefix}_TIMEOUT", "300")),
            max_retries=int(os.getenv(f"{prefix}_MAX_RETRIES", "3")),
            log_commands=os.getenv(f"{prefix}_LOG_COMMANDS", "true").lower() == "true",
            buffer_size=int(os.getenv(f"{prefix}_BUFFER_SIZE", "8192")),
        )

    def with_timeout(self, timeout: int) -> "CommandRunnerConfig":
        """Create a new config with different timeout."""
        return CommandRunnerConfig(
            timeout=timeout,
            max_retries=self.max_retries,
            log_commands=self.log_commands,
            buffer_size=self.buffer_size,
        )

    def with_retries(self, max_retries: int) -> "CommandRunnerConfig":
        """Create a new config with different retry count."""
        return CommandRunnerConfig(
            timeout=self.timeout,
            max_retries=max_retries,
            log_commands=self.log_commands,
            buffer_size=self.buffer_size,
        )
