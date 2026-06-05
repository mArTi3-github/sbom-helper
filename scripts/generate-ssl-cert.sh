#!/usr/bin/env bash
set -euo pipefail

SSL_DIR="/app/ssl"
mkdir -p "$SSL_DIR"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$SSL_DIR/server.key" \
  -out "$SSL_DIR/server.crt" \
  -days 365 \
  -subj "/CN=localhost" \
  -addext "subjectAltName=IP:127.0.0.1,DNS:localhost"

chmod 600 "$SSL_DIR/server.key"
chmod 644 "$SSL_DIR/server.crt"

echo "SSL certificate generated in $SSL_DIR"
