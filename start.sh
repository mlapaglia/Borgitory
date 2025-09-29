#!/bin/bash

echo "🚀 Starting Borgitory with HTTP on port 8000"

# Enable debugging and reload in development mode
if [ "$BORGITORY_DEV_MODE" = "true" ]; then
    echo "🔄 Development mode: Auto-reload enabled"
    if [ "$BORGITORY_DEBUG" = "true" ]; then
        echo "🐛 Debug mode: Debugger listening on port 5678"
        python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m borgitory.cli serve --host 0.0.0.0 --port 8000 --reload
    else
        exec borgitory serve --host 0.0.0.0 --port 8000 --reload
    fi
else
    exec borgitory serve --host 0.0.0.0 --port 8000
fi