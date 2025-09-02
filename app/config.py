import os
from pathlib import Path

DATABASE_URL = "sqlite:////app/data/borgitory.db";
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
DATA_DIR = "/app/data";
BORG_DOCKER_IMAGE = os.getenv("BORG_DOCKER_IMAGE", "ghcr.io/borgmatic-collective/borgmatic:latest")

# Docker volume mount paths (configurable via environment)
BORG_REPOS_HOST_PATH = "./borg-repos"
BACKUP_SOURCES_HOST_PATH = "./backup-sources"
BORG_REPOS_CONTAINER_PATH = "/repos"
BACKUP_SOURCES_CONTAINER_PATH = "/data"

# Note: DATA_DIR creation is handled in database.py init_db() to avoid permission issues