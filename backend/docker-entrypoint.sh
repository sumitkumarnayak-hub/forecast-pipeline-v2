#!/bin/sh
set -e

PORT="${PORT:-7860}"

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips="*"
