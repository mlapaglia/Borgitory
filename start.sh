#!/bin/bash

# Start the application with HTTP
echo "🚀 Starting Borgitory with HTTP on port 8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000