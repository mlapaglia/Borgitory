# Borgitory

[![codecov](https://codecov.io/gh/mlapaglia/Borgitory/graph/badge.svg?token=3XFFTWSKTB)](https://codecov.io/gh/mlapaglia/Borgitory)
[![build](https://img.shields.io/github/actions/workflow/status/mlapaglia/borgitory/build.yml?logo=github)](https://github.com/mlapaglia/Borgitory/actions/workflows/release.yml)
[![sponsors](https://img.shields.io/github/sponsors/mlapaglia?logo=githubsponsors)](https://github.com/sponsors/mlapaglia)
[![docker pulls](https://img.shields.io/docker/pulls/mlapaglia/borgitory?logo=docker)](https://hub.docker.com/r/mlapaglia/borgitory)
[![pypi downloads](https://img.shields.io/pypi/dm/borgitory?style=flat&logo=pypi&logoColor=%23ffd343&label=PyPi%20Downloads&labelColor=%23ffd343&link=https%3A%2F%2Fpypi.org%2Fproject%2Fborgitory%2F)](https://pypi.org/project/borgitory/)
[![borgbackup version](https://img.shields.io/badge/dynamic/dockerfile?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmlapaglia%2FBorgitory%2Fcodecov-test-coverage-fix%2FDockerfile&query=ARG%20BORGBACKUP_VERSION%3D(.%2B)&label=borgbackup&prefix=v&style=flat&logo=docker&color=blue)](https://borgbackup.readthedocs.io/)
[![rclone version](https://img.shields.io/badge/dynamic/dockerfile?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmlapaglia%2FBorgitory%2Fcodecov-test-coverage-fix%2FDockerfile&query=ARG%20RCLONE_VERSION%3D(.%2B)&label=rclone&prefix=v&style=flat&logo=docker&color=green)](https://rclone.org/)
[![fuse3 version](https://img.shields.io/badge/dynamic/dockerfile?url=https%3A%2F%2Fraw.githubusercontent.com%2Fmlapaglia%2FBorgitory%2Fcodecov-test-coverage-fix%2FDockerfile&query=ARG%20FUSE3_VERSION%3D(.%2B)&label=fuse3&prefix=v&style=flat&logo=python&color=orange)](https://github.com/libfuse/libfuse)

<img alt="borgitory logo" src="./assets/logo.png" width="400">

A comprehensive web-based management interface for BorgBackup repositories with real-time monitoring, automated scheduling, and cloud synchronization capabilities.

## Features

### Core Functionality

- **Repository Management**: Add, configure, and manage multiple Borg repositories
- **Manual Backups**: Create backups on-demand with configurable compression and source paths
- **Real-time Progress**: Monitor backup progress with live updates
- **Archive Browser**: Interactive directory-based archive exploration with file downloads
- **Job History**: Track all backup operations with detailed logs and expandable task views

- **Automated Scheduling**: Set up cron-based backup schedules with integrated cleanup and notifications
- **Archive Pruning**: Configure automated pruning policies with simple or advanced retention strategies
- **Cloud Sync**: Synchronize repositories to S3-compatible storage using Rclone
- **Push Notifications**: Pushover integration for job completion alerts
- **User Authentication**: Secure username/password authentication
- **Template System**: Modern Jinja2-based UI with reusable components
- **Mobile Responsive**: HTMX + Alpine.js + Tailwind CSS interface

## Quick Start

### Prerequisites

- **Docker Installation (Recommended)**: Docker with Docker Compose for containerized deployment
- **PyPI Installation**: Python 3.11+ for direct installation from PyPI

### Installation

#### Option 1: PyPI Installation (New!)

Install Borgitory directly from PyPI:

```bash
# Install stable release from PyPI
pip install borgitory

# Or install pre-release from TestPyPI (for testing new features)
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ borgitory

# Start the server
borgitory serve

# Or run with custom settings
borgitory serve --host 0.0.0.0 --port 8000
```

**PyPI Installation Requirements:**

- Python 3.11 or higher
- BorgBackup installed and available in PATH
- Rclone (optional, for cloud sync features)

**Note**: Pre-release versions are published to [TestPyPI](https://test.pypi.org/project/borgitory/) for testing before stable release.

#### Option 2: Docker Installation

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
         - ./data:/app/data
         - /path/to/backup/sources:/mnt/backup/sources:ro
         - /path/to/borg/repos:/mnt/repos
       cap_add:
         - SYS_ADMIN
       devices:
         - /dev/fuse
       restart: unless-stopped
   ```

   ```bash
   docker-compose up -d
   ```

2. **Access the web interface**
   - Open <http://localhost:8000> in your browser
   - Create your first admin account on initial setup

**Docker Hub**: Available at [mlapaglia/borgitory](https://hub.docker.com/r/mlapaglia/borgitory)

### Docker Volumes

```yaml
volumes:
  - ./data:/app/data # Persistent application data (required)
  - /path/to/backup/sources:/mnt/backup/sources:ro # Source directories to backup (read-only)
  - /path/to/borg/repos:/mnt/repos # Borg repository storage (read-write)
  - /additional/source:/mnt/additional:ro # Additional source directories as needed
  - /another/repo/location:/mnt/alt-repos # Additional repository locations as needed
```

**Volume Strategy:**

- **Important**: All volumes must be mounted under `/mnt/` to be visible in the application
- Mount as many volumes as necessary to access all your backup sources and repository locations
- Source directories can be mounted read-only (`:ro`) for safety
- Repository directories need read-write access for Borg operations
- Each volume can be mapped to any convenient path under `/mnt/` inside the container
- Supports distributed setups where repositories and sources are in different locations

## Usage

### 1. Repository Setup

1. Navigate to the main dashboard
2. Add a new repository:
   - **Name**: Friendly identifier
   - **Path**: Repository location (local or remote)
   - **Passphrase**: Encryption password
3. The system will validate the repository connection

### 2. Creating Backups

**Manual Backup:**

1. Select repository from dropdown
2. Configure source path and compression
3. Click "Start Backup"
4. Monitor progress in real-time

**Scheduled Backup:**

1. Go to Schedules section
2. Create new schedule with cron expression
3. Enable/disable schedules as needed

### 3. Archive Pruning

1. Create pruning policies:
   - **Simple Strategy**: Keep archives within X days
   - **Advanced Strategy**: Granular retention (daily/weekly/monthly/yearly)
2. Configure options:
   - Show detailed prune lists
   - Display space savings statistics
   - Force prune execution
3. Attach policies to schedules or manual backups

### 4. Archive Browsing

**Exploring Archives:**

1. Click "View Contents" on any archive to open the browser
2. Navigate through directories by clicking folder names  
3. View file details including size and modification dates
4. Real-time directory exploration using FUSE-mounted archive filesystems

**Downloading Files:**

1. Click the download button (⬇) next to any file
2. Files stream directly from the mounted archive without temporary storage
3. Works efficiently with large files and slow connections
4. Multiple downloads can run simultaneously
5. Uses FUSE mounting for fast, direct file access

**Requirements:**

- Docker container must run with `--cap-add SYS_ADMIN` and `--device /dev/fuse`
- Without FUSE support, archive browsing will be disabled

### 5. Cloud Sync

1. Configure S3 remote:
   - Access Key ID and Secret
2. Test connection
3. Set up automatic sync after backups or manual sync

### 6. Push Notifications

1. Configure Pushover notifications:
   - User Key and API Token
2. Choose notification triggers:
   - Success, failure, or both
3. Attach to schedules for automated alerts

## API Documentation

The application provides a RESTful API with automatic OpenAPI documentation:

- **Swagger UI**: <http://localhost:8000/docs>
- **ReDoc**: <http://localhost:8000/redoc>

## Deployment

### Docker Compose (Recommended)

```bash
# Production deployment
docker-compose -f docker-compose.yml up -d
```

### Manual Docker

```bash
# Build image
docker build -t borgitory .

# Run container with FUSE support for archive browsing
docker run -d \
  -p 8000:8000 \
  -v ./data:/app/data \
  -v /path/to/backup/sources:/mnt/backup/sources:ro \
  -v /path/to/borg/repos:/mnt/repos \
  --cap-add SYS_ADMIN \
  --device /dev/fuse \
  --name borgitory \
  borgitory
```

**Required Docker Parameters:**

- `--cap-add SYS_ADMIN`: Required for FUSE filesystem mounting to enable archive browsing
- `--device /dev/fuse`: Provides access to FUSE device for archive file system mounting

**FUSE Requirements:**

- FUSE mounting enables the interactive archive browser feature
- Allows real-time exploration of backup archives without extraction
- Supports direct file downloads from mounted archive filesystems
- Without FUSE support, archive browsing will be disabled

## Project Dependencies

This project uses modern Python packaging standards with all dependencies defined in `pyproject.toml`:

> Install with `pip install -e .[dev]` to include development tools.

## Architecture

### Backend Stack

- **FastAPI**: Modern Python web framework with automatic OpenAPI docs
- **SQLite**: Lightweight database for configuration and job history
- **APScheduler**: Advanced job scheduling and cron support
- **Jinja2**: Powerful template engine for dynamic HTML generation
- **Passlib**: Secure password hashing and verification
- **Pushover**: Push notification service integration

### Frontend Stack

- **HTMX**: Dynamic HTML updates without JavaScript frameworks
- **Alpine.js**: Lightweight JavaScript reactivity
- **Tailwind CSS**: Utility-first styling with responsive design
- **Server-Sent Events**: Real-time progress updates and live job monitoring

### Job Management System

- **Real-time Monitoring**: Live job output streaming with expandable task details
- **Progress Tracking**: Detailed progress indicators for each job stage
- **Job History**: Persistent storage of job results with searchable history
- **Task Management**: Individual task tracking within jobs

### Security Features

- Username/password authentication with bcrypt hashing
- Secure session management
- Encrypted credential storage (Fernet)

## Troubleshooting

### Logs

```bash
# View application logs
docker-compose logs -f borgitory

# Check specific container logs
docker logs <container-id>
```

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Run lint (`python lint.py all`)
4. Run tests (`pytest`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open Pull Request

### Adding additional cloud destinations

- Refer to [CLOUD_PROVIDERS.md](https://github.com/mlapaglia/borgitory/blob/main/CLOUD_PROVIDERS.md) for adding additional cloud destinations.

### Development Setup

1. **Set up Python virtual environment**

   ```bash
   # Create virtual environment
   python -m venv .env_borg
   
   # Activate virtual environment
   # On Windows:
   .env_borg\Scripts\activate
   # On macOS/Linux:
   source .env_borg/bin/activate
   ```

2. **Install Python dependencies**

   ```bash
   # Install runtime dependencies only
   pip install -e .
   
   # Install with development dependencies (testing, linting, etc.)
   pip install -e .[dev]
   
   # Or install stable release from PyPI for testing
   pip install borgitory
   
   # Or install pre-release from TestPyPI for testing new features
   pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ borgitory
   ```

   > **Note**: This project uses modern Python packaging with `pyproject.toml` following PEP 518 standards and is available on PyPI. All dependencies and project metadata are defined in a single configuration file.

3. **Install Rclone** (for cloud sync)

   ```bash
   # On Ubuntu/Debian
   curl https://rclone.org/install.sh | sudo bash
   
   # On macOS
   brew install rclone
   ```

4. **Run development server**

   ```bash
   python run.py
   ```

5. **Run tests**

   ```bash
   pytest
   ```