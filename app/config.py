import os

DATABASE_URL = "sqlite:////app/data/borgitory.db"
DATA_DIR = "/app/data"


def get_secret_key():
    """Get SECRET_KEY from environment, raising error if not available."""
    secret_key = os.getenv("SECRET_KEY")
    if secret_key is None:
        raise RuntimeError(
            "SECRET_KEY not available. This should be set during application startup."
        )
    return secret_key
