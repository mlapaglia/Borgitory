"""Configuration classes for Borgitory services."""

# Re-export everything from the main config module to maintain compatibility
from borgitory.config_module import *  # noqa: F403, F401
from .command_runner_config import CommandRunnerConfig

__all__ = ["CommandRunnerConfig", "DATABASE_URL", "get_secret_key", "DATA_DIR"]
