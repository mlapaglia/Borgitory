FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Rclone
RUN curl -O https://downloads.rclone.org/rclone-current-linux-amd64.zip \
    && unzip rclone-current-linux-amd64.zip \
    && cd rclone-*-linux-amd64 \
    && cp rclone /usr/bin/ \
    && chown root:root /usr/bin/rclone \
    && chmod 755 /usr/bin/rclone \
    && cd .. \
    && rm -rf rclone-*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV DATABASE_URL=sqlite:///./data/borgitory.db
ENV DATA_DIR=/app/data

# Run the application (reload is disabled by default)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]