"""
Notification providers package.

This package contains all notification provider implementations.
Providers are automatically registered when imported.
"""

# Import all providers to ensure they are registered
from . import pushover_provider
from . import discord_provider
from . import telegram_provider

__all__ = [
    "pushover_provider",
    "discord_provider",
    "telegram_provider",
]
