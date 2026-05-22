#!/bin/bash

ensure_writable_dir() {
    mkdir -p "$1" 2>/dev/null && [ -w "$1" ]
}

echo "🚀 Starting Borgitory with HTTP on port 8000"

export HOME="${HOME:-/tmp}"
if ! ensure_writable_dir "${HOME}"; then
    if [ "${HOME}" != "/tmp" ]; then
        echo "⚠️  Unable to use HOME=${HOME}, falling back to /tmp"
    fi
    export HOME="/tmp"
    if ! ensure_writable_dir "${HOME}"; then
        echo "❌ Unable to create writable HOME directory at /tmp"
        exit 1
    fi
fi

if [ -z "${BORG_BASE_DIR}" ]; then
    if ensure_writable_dir /cache/borg; then
        export BORG_BASE_DIR="/cache/borg"
    else
        echo "⚠️  Unable to use writable /cache/borg, falling back to /tmp/borg for Borg state"
        export BORG_BASE_DIR="/tmp/borg"
        if ! ensure_writable_dir "${BORG_BASE_DIR}"; then
            echo "❌ Unable to create writable Borg base directory at ${BORG_BASE_DIR}"
            exit 1
        fi
    fi
fi

if [ "$BORGITORY_DEBUG" = "true" ]; then
    echo "🐛 Debug mode: Debugger listening on port 5678"
    python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m borgitory.cli serve --host 0.0.0.0 --port 8000
else
    exec borgitory serve --host 0.0.0.0 --port 8000
fi