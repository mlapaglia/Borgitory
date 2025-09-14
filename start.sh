#!/bin/bash

echo "🔄 Running database migrations..."
alembic upgrade head

if [ $? -ne 0 ]; then
    echo "❌ Database migration failed!"
    exit 1
fi

echo "✅ Database migrations completed"
echo "🚀 Starting Borgitory with HTTP on port 8000"
exec uvicorn main:app --host 0.0.0.0 --port 8000