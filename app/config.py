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
BORG_DOCKER_IMAGE = os.getenv(
    "BORG_DOCKER_IMAGE", "ghcr.io/borgmatic-collective/borgmatic:latest"
)

# Docker volume mount paths (configurable via environment)
BORG_REPOS_HOST_PATH = "./borg-repos"
BACKUP_SOURCES_HOST_PATH = "./backup-sources"
BORG_REPOS_CONTAINER_PATH = "/repos"
BACKUP_SOURCES_CONTAINER_PATH = "/data"
