#!/usr/bin/env sh
# entrypoint.sh — run Alembic migrations then start gunicorn
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting application server..."
exec gunicorn app.main:app \
  -w "${GUNICORN_WORKERS:-4}" \
  -k uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-8000}" \
  --worker-tmp-dir /dev/shm \
  --no-control-socket \
  --access-logfile - \
  --error-logfile -
