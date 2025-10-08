import os
from pathlib import Path

# Use app/data for both local and container environments
APP_DIR = Path(__file__).parent  # This is the app/ directory


def get_data_dir() -> str:
    """Get the data directory using synchronous path configuration."""
    # Import here to avoid circular imports
    from borgitory.services.path.path_configuration_service import (
        PathConfigurationService,
    )

    try:
        # Use path configuration service directly for sync access
        config = PathConfigurationService()
        return config.get_base_data_dir()
    except Exception:
        # Ultimate fallback
        return str(APP_DIR / "data")


# Static paths for configuration - these must be synchronous
DATA_DIR = get_data_dir()
DATABASE_PATH = os.path.join(DATA_DIR, "borgitory.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"


def get_secret_key() -> str:
    """Get SECRET_KEY from environment, raising error if not available."""
    secret_key = os.getenv("SECRET_KEY")
    if secret_key is None:
        raise RuntimeError(
            "SECRET_KEY not available. This should be set during application startup."
        )
    return secret_key
