#!/bin/sh
set -eu

HOST="${UVICORN_HOST:-0.0.0.0}"
PORT_VALUE="${PORT:-${UVICORN_PORT:-8000}}"
WORKERS="${UVICORN_WORKERS:-1}"

exec uvicorn app.main:app \
  --host "$HOST" \
  --port "$PORT_VALUE" \
  --workers "$WORKERS"
