# Borgitory

A comprehensive web-based management interface for BorgBackup repositories with real-time monitoring, automated scheduling, and cloud synchronization capabilities.

## Features

### Core Functionality
- **Repository Management**: Add, configure, and manage multiple Borg repositories
- **Manual Backups**: Create backups on-demand with configurable compression and source paths
- **Real-time Progress**: Monitor backup progress with live updates via Server-Sent Events
- **Archive Browser**: List and explore backup archives with size and date information
- **Job History**: Track all backup operations with detailed logs and status

### Advanced Features
- **Automated Scheduling**: Set up cron-based backup schedules with APScheduler
- **Cloud Sync**: Synchronize repositories to S3-compatible storage using Rclone
- **User Authentication**: Secure username/password authentication
- **Docker Integration**: Manage Borg operations through isolated Docker containers
- **Mobile Responsive**: HTMX + Alpine.js + Tailwind CSS interface

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Access to Docker socket (`/var/run/docker.sock`)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Borgitory
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start with Docker Compose**
   ```bash
   docker-compose up -d
   ```

4. **Access the web interface**
   - Open http://localhost:8000 in your browser
   - Create your first admin account on initial setup

### Development Setup

1. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Rclone** (for cloud sync)
   ```bash
   # On Ubuntu/Debian
   curl https://rclone.org/install.sh | sudo bash
   
   # On macOS
   brew install rclone
   ```

3. **Run development server**
   ```bash
   python run.py
   ```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *required* | Encryption key for stored credentials |
| `DATABASE_URL` | `sqlite:///./data/borgitory.db` | SQLite database path |
| `BORG_DOCKER_IMAGE` | `ghcr.io/borgmatic-collective/borgmatic:latest` | Docker image for Borg/Borgmatic operations |

### BorgBackup Docker Image

The application uses the official **borgmatic-collective** Docker image which includes:
- **BorgBackup** - The core backup functionality
- **Borgmatic** - Configuration management and automation wrapper
- **Well-maintained** - Active community support and regular updates
- **Comprehensive** - Includes all necessary dependencies and tools

Alternative images can be configured via the `BORG_DOCKER_IMAGE` environment variable.

### Docker Volumes

The application requires these volume mounts:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock  # Docker API access
  - ./data:/app/data                           # Persistent data
  - /path/to/backup/sources:/data:ro           # Source data to backup
```

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

### 3. Cloud Sync

1. Configure S3 remote:
   - Access Key ID and Secret
   - Region and optional endpoint
2. Test connection
3. Set up automatic sync after backups or manual sync

## API Documentation

The application provides a RESTful API with automatic OpenAPI documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key Endpoints

- `POST /api/repositories/` - Create repository
- `POST /api/jobs/backup` - Start backup
- `GET /api/jobs/{id}/stream` - Stream job progress (SSE)
- `POST /api/schedules/` - Create backup schedule
- `POST /api/sync/` - Sync to cloud storage

## Architecture

### Backend Stack
- **FastAPI**: Modern Python web framework
- **SQLite**: Lightweight database for configuration
- **APScheduler**: Job scheduling and cron support
- **Docker SDK**: Container management
- **Passlib**: Password hashing and verification

### Frontend Stack
- **HTMX**: Dynamic HTML updates
- **Alpine.js**: Lightweight JavaScript reactivity
- **Tailwind CSS**: Utility-first styling
- **Server-Sent Events**: Real-time progress updates

### Security Features
- Username/password authentication with bcrypt hashing
- Secure session management
- Encrypted credential storage (Fernet)
- Docker container isolation
- No network access for Borg containers

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

# Run container
docker run -d \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v ./data:/app/data \
  -v /backup/sources:/data:ro \
  --name borgitory \
  borgitory
```

### Reverse Proxy Setup

Example Nginx configuration:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support for SSE
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_cache_bypass $http_upgrade;
    }
}
```

## Troubleshooting

### Common Issues

1. **Docker permission denied**
   - Ensure user is in `docker` group
   - Check Docker socket permissions

2. **Backup fails with "repository not found"**
   - Verify repository path is accessible from container
   - Check volume mounts in docker-compose.yml

3. **Login fails**
   - Check username and password are correct
   - Ensure database is properly initialized

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
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [BorgBackup](https://borgbackup.readthedocs.io/) - Deduplicating backup program
- [Rclone](https://rclone.org/) - Cloud storage sync tool
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [HTMX](https://htmx.org/) - High power tools for HTML
