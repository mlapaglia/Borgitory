#!/bin/bash

echo "🚀 Starting Borgitory with HTTP on port 8000"

export HOME="${HOME:-/tmp}"
mkdir -p "${HOME}"

if [ -z "${BORG_BASE_DIR}" ]; then
    if mkdir -p /cache/borg 2>/dev/null; then
        export BORG_BASE_DIR="/cache/borg"
    else
        export BORG_BASE_DIR="/tmp/borg"
        mkdir -p "${BORG_BASE_DIR}"
    fi
fi

if [ "$BORGITORY_DEBUG" = "true" ]; then
    echo "🐛 Debug mode: Debugger listening on port 5678"
    python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m borgitory.cli serve --host 0.0.0.0 --port 8000
else
    exec borgitory serve --host 0.0.0.0 --port 8000
fi