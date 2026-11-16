#!/bin/bash
set -euo pipefail

echo "🚀 Starting Borgitory with HTTP on port 8000"

if [ "${BORGITORY_DEBUG:-}" = "true" ]; then
    DEBUG_HOST="${BORGITORY_DEBUG_HOST:-127.0.0.1}"
    echo "🐛 Debug mode: debugger listening on ${DEBUG_HOST}:5678 (waiting for client)"
    exec python -m debugpy --listen "${DEBUG_HOST}:5678" --wait-for-client -m borgitory.cli serve --host 0.0.0.0 --port 8000
else
    exec borgitory serve --host 0.0.0.0 --port 8000
fi
