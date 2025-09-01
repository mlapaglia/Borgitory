FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    rclone \
    borgbackup \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r borgitory && useradd -r -g borgitory -d /app -s /bin/bash borgitory

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# Generate self-signed SSL certificate
RUN mkdir -p /app/ssl && \
    openssl req -x509 -newkey rsa:4096 -keyout /app/ssl/key.pem -out /app/ssl/cert.pem \
    -days 3650 -nodes -subj "/C=US/ST=State/L=City/O=Borgitory/CN=localhost" && \
    chown -R borgitory:borgitory /app/ssl

USER borgitory

EXPOSE 8443

ENV SSL_CERT_FILE=/app/ssl/cert.pem
ENV SSL_KEY_FILE=/app/ssl/key.pem

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8443", "--ssl-keyfile", "/app/ssl/key.pem", "--ssl-certfile", "/app/ssl/cert.pem"]