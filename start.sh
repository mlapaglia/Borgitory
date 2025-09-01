#!/bin/bash

# Generate SSL certificate if needed
python -c "from app.startup import ensure_certificates; ensure_certificates()"

# Start the application with HTTPS
echo "🔒 Starting Borgitory with HTTPS on port 8443"
exec uvicorn app.main:app --host 0.0.0.0 --port 8443 --ssl-keyfile /app/ssl/key.pem --ssl-certfile /app/ssl/cert.pem