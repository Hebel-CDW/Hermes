#!/bin/sh
# Container entrypoint: optionally seed the synthetic demo database, then serve.
set -e

if [ "${HERMES_DEMO_SEED:-0}" = "1" ] && [ ! -f "${HERMES_DB_PATH}" ]; then
    echo "Seeding synthetic demo database at ${HERMES_DB_PATH}"
    python -m scripts.ingest_fixtures >/dev/null
fi

exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers --no-server-header
