import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/borgitory.db")
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
BORG_DOCKER_IMAGE = os.getenv("BORG_DOCKER_IMAGE", "ghcr.io/borgmatic-collective/borgmatic:latest")

DATA_DIR.mkdir(exist_ok=True)