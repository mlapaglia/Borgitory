ARG BORGBACKUP_VERSION=1.4.0-5
ARG RCLONE_VERSION=1.60.1+dfsg-4
ARG FUSE3_VERSION=3.17.2-3
ARG PYFUSE3_VERSION=3.4.0-3+b3
FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58 AS tailwind-builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY tailwind.config.js ./
COPY src/borgitory/templates/ ./src/borgitory/templates/
COPY src/borgitory/static/css/tailwind-input.css ./src/borgitory/static/css/
ARG TARGETARCH
ARG TAILWIND_VERSION=3.4.17
ARG TAILWIND_SHA256_X64=7d24f7fa191d2193b78cd5f5a42a6093e14409521908529f42d80b11fde1f1d4
ARG TAILWIND_SHA256_ARM64=69b1378b8133192d7d2feb12a116fa12d035594f58db3eff215879e4ad8cf39b
RUN set -e; \
    if [ "$TARGETARCH" = "arm64" ]; then ARCH=arm64; SHA="$TAILWIND_SHA256_ARM64"; \
    else ARCH=x64; SHA="$TAILWIND_SHA256_X64"; fi; \
    curl -sfLO "https://github.com/tailwindlabs/tailwindcss/releases/download/v${TAILWIND_VERSION}/tailwindcss-linux-${ARCH}" && \
    echo "${SHA}  tailwindcss-linux-${ARCH}" | sha256sum -c - && \
    chmod +x tailwindcss-linux-${ARCH} && \
    ./tailwindcss-linux-${ARCH} \
      -i src/borgitory/static/css/tailwind-input.css \
      -o src/borgitory/static/css/tailwind.css \
      --minify

FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58 AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    libfuse3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Runtime dependencies only, from the hash-locked requirements file
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

# The project itself (dependencies already installed above)
COPY pyproject.toml LICENSE README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps -e .

# Test/dev tooling layered on top; never copied into the production image
FROM builder AS builder-dev
COPY requirements-dev.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements-dev.txt

FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58 AS test

ARG BORGBACKUP_VERSION
ARG RCLONE_VERSION
ARG FUSE3_VERSION
ARG PYFUSE3_VERSION

WORKDIR /app

# libatomic1: Playwright's bundled Node driver (>= 1.65) links against it, so it must be
# present before `playwright install --with-deps` can run and install everything else.
RUN apt-get update && apt-get install -y --no-install-recommends \
    rclone=${RCLONE_VERSION} \
    borgbackup=${BORGBACKUP_VERSION} \
    fuse3=${FUSE3_VERSION} \
    python3-pyfuse3=${PYFUSE3_VERSION} \
    libatomic1 \
    openssh-client \
    openssh-server \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* \
    # sshd (for remote repository tests) needs its privilege separation directory
    && mkdir -p /run/sshd

COPY --from=builder-dev /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

COPY src/ ./src/
COPY --from=tailwind-builder /app/src/borgitory/static/css/tailwind.css ./src/borgitory/static/css/tailwind.css
COPY tests/ ./tests/
COPY lint.py ./

CMD ["pytest"]

# Local development image: test image (dev tooling incl. debugpy) + app entrypoint.
# Used by docker-compose.dev.yml. Must stay above the final (production) stage.
FROM test AS dev
ENV BORGITORY_RUNNING_IN_CONTAINER=true
RUN mkdir -p /app/data
COPY start.sh ./
RUN chmod +x start.sh
EXPOSE 8000 5678
ENTRYPOINT ["/app/start.sh"]

FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58

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
    openssh-client \
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

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)" || exit 1

ENTRYPOINT ["/app/start.sh"]
