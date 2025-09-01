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

# Create data directory and ensure proper permissions for the borgitory user
RUN mkdir -p /app/data /repos /data && \
    chown -R borgitory:borgitory /app /repos /data

# Switch to non-root user
USER borgitory

# Create the database directory with proper permissions (as the borgitory user)
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:////app/data/borgitory.db
ENV DATA_DIR=/app/data

# Run the application (reload is disabled by default)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]