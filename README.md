
# Borgitory
[![codecov](https://codecov.io/gh/mlapaglia/Borgitory/graph/badge.svg?token=3XFFTWSKTB)](https://codecov.io/gh/mlapaglia/Borgitory)
[![build](https://img.shields.io/github/actions/workflow/status/mlapaglia/borgitory/build.yml?logo=github)](https://github.com/mlapaglia/Borgitory/actions/workflows/release.yml)
[![sponsors](https://img.shields.io/github/sponsors/mlapaglia?logo=githubsponsors)](https://github.com/sponsors/mlapaglia)
[![docker pulls](https://img.shields.io/docker/pulls/mlapaglia/borgitory?logo=docker&label=pulls)](https://hub.docker.com/r/mlapaglia/borgitory)
[![pypi downloads](https://img.shields.io/pypi/dm/borgitory?style=flat&logo=pypi&logoColor=%23ffd343&label=downloads&labelColor=%23ffd343&link=https%3A%2F%2Fpypi.org%2Fproject%2Fborgitory%2F)](https://pypi.org/project/borgitory/)
[![Read the Docs](https://img.shields.io/readthedocs/borgitory?logo=readthedocs)](https://borgitory.com)

[![borgbackup version](https://img.shields.io/badge/dynamic/regex?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmlapaglia%2FBorgitory%2Frefs%2Fheads%2Fmain%2FDockerfile&search=ARG%20BORGBACKUP_VERSION%3D(.%2B)&replace=%241&logo=borgbackup&label=BorgBackup)](https://borgbackup.readthedocs.io/)
[![rclone version](https://img.shields.io/badge/dynamic/regex?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmlapaglia%2FBorgitory%2Frefs%2Fheads%2Fmain%2FDockerfile&search=ARG%20RCLONE_VERSION%3D(.%2B)&replace=%241&logo=rclone&label=Rclone)](https://rclone.org/)
[![fuse3 version](https://img.shields.io/badge/dynamic/regex?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmlapaglia%2FBorgitory%2Frefs%2Fheads%2Fmain%2FDockerfile&search=ARG%20FUSE3_VERSION%3D(.%2B)&replace=%241&logo=python&label=pfuse3)](https://github.com/libfuse/libfuse)

<img alt="borgitory logo" src="./assets/logo.png" width="400">

Borgitory is a comprehensive web-based management interface for BorgBackup repositories that provides real-time monitoring, automated scheduling, and cloud synchronization capabilities. It offers complete backup lifecycle management including on-demand backups, automated pruning policies, interactive archive browsing with file downloads, and cloud sync to S3-compatible storage via Rclone. The FastAPI powered system features a modern responsive web interface built with HTMX, and Tailwind CSS.

## Quick Start

- full documentation is available at <https://borgitory.com>

### Prerequisites

- **Docker Installation (Recommended)**: Docker with Docker Compose for containerized deployment
- **PyPI Installation**: Python 3.11+ for direct installation from PyPI

### Installation

#### Option 1: Docker Installation (Recommended)

1. **Pull and run the Docker image**

   ```bash
   # Using Docker directly
   docker run -d \
     -p 8000:8000 \
     -v ./data:/app/data \
     -v /path/to/backup/sources:/mnt/backup/sources:ro \
     -v /path/to/borg/repos:/mnt/repos \
     --cap-add SYS_ADMIN \
     --device /dev/fuse \
     --name borgitory \
     mlapaglia/borgitory:latest
   ```

   **Or using Docker Compose** (create a `docker-compose.yml`):

   ```yaml
   version: '3.8'
   services:
     borgitory:
       image: mlapaglia/borgitory:latest
       ports:
         - "8000:8000"
       volumes:
         - ./data:/app/data # database and encryption key location
         - /path/to/backup/sources:/mnt/sources:ro
         - /path/to/any/backup/repos:/mnt/repos:ro
       cap_add:
         - SYS_ADMIN # optional, needed to mount borg archives and browse them
       devices:
         - /dev/fuse # borg uses FUSE to mount archives
       restart: unless-stopped
   ```

   **Important**: All volumes must be mounted under `/mnt/` to be visible in the application

   ```bash
   docker-compose up -d
   ```

2. **Access the web interface**
   - Open <http://localhost:8000> in your browser
   - Create your first admin account on initial setup

<img width="1237" height="729" alt="image" src="https://github.com/user-attachments/assets/078ce596-3ba2-4b6f-ba3f-c2d8b95e02db" />

#### Option 2: PyPI Installation

Install Borgitory directly from PyPI:

```bash
# Install stable release from PyPI
pip install borgitory

# Start the server
borgitory serve

# Or run with custom settings
borgitory serve --host 0.0.0.0 --port 8000
```

**PyPI Installation Requirements:**

- Python 3.11 or higher
- BorgBackup installed and available in PATH
- Rclone (optional, for cloud sync features)
- FUSE (optional, for browsing archives)
- Functionality on Windows is currently limited
