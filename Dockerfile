FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    rclone \
    borgbackup \
    openssl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY start.sh /app/start.sh

# Make script executable and create ssl directory
RUN chmod +x /app/start.sh && \
    mkdir -p /app/ssl

EXPOSE 8443

ENV SSL_CERT_FILE=/app/ssl/cert.pem
ENV SSL_KEY_FILE=/app/ssl/key.pem

CMD ["/app/start.sh"]