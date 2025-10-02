#!/bin/bash

echo "🚀 Starting Borgitory with HTTP on port 8000"

if [ "$BORGITORY_DEBUG" = "true" ]; then
    echo "🐛 Debug mode: Debugger listening on port 5678"
    python -m debugpy --listen 0.0.0.0:5678 --wait-for-client -m borgitory.cli serve --host 0.0.0.0 --port 8000
else
    exec borgitory serve --host 0.0.0.0 --port 8000
fi