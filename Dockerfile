ARG BORGBACKUP_VERSION=1.4.0-5
ARG RCLONE_VERSION=1.60.1+dfsg-4
ARG FUSE3_VERSION=3.17.2-3
ARG PYFUSE3_VERSION=3.4.0-3+b3
FROM python:3.14.3-slim-trixie@sha256:6a27522252aef8432841f224d9baaa6e9fce07b07584154fa0b9a96603af7456 AS tailwind-builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY tailwind.config.js ./
COPY src/borgitory/templates/ ./src/borgitory/templates/
COPY src/borgitory/static/css/tailwind-input.css ./src/borgitory/static/css/
ARG TARGETARCH
RUN ARCH=$([ "$TARGETARCH" = "arm64" ] && echo "arm64" || echo "x64") && \
    curl -sfLO "https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-${ARCH}" && \
    chmod +x tailwindcss-linux-${ARCH} && \
    ./tailwindcss-linux-${ARCH} \
      -i src/borgitory/static/css/tailwind-input.css \
      -o src/borgitory/static/css/tailwind.css \
      --minify

FROM python:3.14.3-slim-trixie@sha256:6a27522252aef8432841f224d9baaa6e9fce07b07584154fa0b9a96603af7456 AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    libfuse3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml LICENSE README.md MANIFEST.in ./

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -e .[dev]

COPY src/ ./src/

FROM python:3.14.3-slim-trixie@sha256:6a27522252aef8432841f224d9baaa6e9fce07b07584154fa0b9a96603af7456 AS test

ARG BORGBACKUP_VERSION
ARG RCLONE_VERSION
ARG FUSE3_VERSION
ARG PYFUSE3_VERSION

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    rclone=${RCLONE_VERSION} \
    borgbackup=${BORGBACKUP_VERSION} \
    fuse3=${FUSE3_VERSION} \
    python3-pyfuse3=${PYFUSE3_VERSION} \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY src/ ./src/
COPY --from=tailwind-builder /app/src/borgitory/static/css/tailwind.css ./src/borgitory/static/css/tailwind.css
COPY tests/ ./tests/
COPY lint.py ./

CMD ["pytest"]

FROM python:3.14.3-slim-trixie@sha256:6a27522252aef8432841f224d9baaa6e9fce07b07584154fa0b9a96603af7456

ARG BORGBACKUP_VERSION
ARG RCLONE_VERSION
ARG FUSE3_VERSION
ARG PYFUSE3_VERSION
ENV BORGITORY_RUNNING_IN_CONTAINER=true
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    rclone=${RCLONE_VERSION} \
    borgbackup=${BORGBACKUP_VERSION} \
    fuse3=${FUSE3_VERSION} \
    python3-pyfuse3=${PYFUSE3_VERSION} \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
    && mkdir -p /app/data

COPY --from=builder /opt/venv /opt/venv

COPY src/ ./src/
COPY --from=tailwind-builder /app/src/borgitory/static/css/tailwind.css ./src/borgitory/static/css/tailwind.css
COPY start.sh ./

RUN chmod +x start.sh

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

EXPOSE 8000

ENTRYPOINT ["/app/start.sh"]