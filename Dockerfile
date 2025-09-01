FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    rclone \
    borgbackup \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r borgitory && useradd -r -g borgitory -d /app -s /bin/bash borgitory

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Ensure static directory exists (even if empty)
RUN mkdir -p /app/app/static

# Create data directory and set permissions
RUN mkdir -p /app/data && chown -R borgitory:borgitory /app

# Create directories that will be mounted and ensure proper permissions
RUN mkdir -p /repos /data && chown -R borgitory:borgitory /repos /data

# Switch to non-root user
USER borgitory

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:///./data/borgitory.db
ENV DATA_DIR=/app/data

# Run the application (reload is disabled by default)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]