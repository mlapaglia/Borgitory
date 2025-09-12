FROM python:3.13-slim AS builder

WORKDIR /app

# Install build dependencies for pyfuse3 compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    libfuse3-dev \
    libfuse3-3 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && \
    pip install --no-cache-dir .

FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    rclone \
    borgbackup \
    fuse3 \
    python3-pyfuse3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
    && mkdir -p /app/data

COPY --from=builder /opt/venv /opt/venv

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini start.sh ./

RUN chmod +x start.sh

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8000

ENTRYPOINT ["/app/start.sh"]