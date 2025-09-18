import os
from pathlib import Path

# Use app/data for both local and container environments
APP_DIR = Path(__file__).parent  # This is the app/ directory
DATA_DIR = str("data")
DATABASE_PATH = str("data/borgitory.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


def get_secret_key() -> str:
    """Get SECRET_KEY from environment, raising error if not available."""
    secret_key = os.getenv("SECRET_KEY")
    if secret_key is None:
        raise RuntimeError(
            "SECRET_KEY not available. This should be set during application startup."
        )
    return secret_key
