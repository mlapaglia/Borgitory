import os

DATABASE_URL = "sqlite:////app/data/borgitory.db"
DATA_DIR = "/app/data"

# SECRET_KEY will be set during application startup
SECRET_KEY = os.getenv("SECRET_KEY")
if SECRET_KEY is None:
    raise RuntimeError("SECRET_KEY not available. This should be set during application startup.")
BORG_DOCKER_IMAGE = os.getenv(
    "BORG_DOCKER_IMAGE", "ghcr.io/borgmatic-collective/borgmatic:latest"
)

# Docker volume mount paths (configurable via environment)
BORG_REPOS_HOST_PATH = "./borg-repos"
BACKUP_SOURCES_HOST_PATH = "./backup-sources"
BORG_REPOS_CONTAINER_PATH = "/repos"
BACKUP_SOURCES_CONTAINER_PATH = "/data"
