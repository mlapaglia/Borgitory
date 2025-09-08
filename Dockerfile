FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    rclone \
    borgbackup \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini
COPY manage_db.py ./manage_db.py
COPY start.sh /app/start.sh

# Create data directory in container (will be empty initially)
RUN mkdir -p /app/data

# Make script executable
RUN chmod +x /app/start.sh

EXPOSE 8000

CMD ["/app/start.sh"]