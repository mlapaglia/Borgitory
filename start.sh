#!/bin/bash

ensure_writable_dir() {
    mkdir -p "$1" 2>/dev/null && [ -w "$1" ]
}

echo "Starting Borgitory with HTTP on port 8000"

if [ -z "${HOME}" ]; then
    echo "ERROR: HOME is not set. Set HOME to a writable directory for Borg runtime files."
    exit 1
fi

if ! ensure_writable_dir "${HOME}"; then
    echo "ERROR: HOME=${HOME} is not writable. Set HOME to a writable directory."
    exit 1
fi

if [ -z "${BORG_BASE_DIR}" ]; then
    export BORG_BASE_DIR="/cache/borg"
fi

if ! ensure_writable_dir "${BORG_BASE_DIR}"; then
    echo "ERROR: BORG_BASE_DIR=${BORG_BASE_DIR} is not writable. Set BORG_BASE_DIR to a writable directory."
    exit 1
fi

if [ "$BORGITORY_DEBUG" = "true" ]; then
    echo "Debug mode: Debugger listening on port 5678"
    python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m borgitory.cli serve --host 0.0.0.0 --port 8000
else
    exec borgitory serve --host 0.0.0.0 --port 8000
fi