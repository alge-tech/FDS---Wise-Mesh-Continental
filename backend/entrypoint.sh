#!/bin/sh
# Migrate as the owner role, seed an empty database (demo), then serve as the app role.
set -e
alembic upgrade head
if [ "${SEED_ON_START:-true}" = "true" ]; then
  python -m app.cli seed-if-empty
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' "$@"
