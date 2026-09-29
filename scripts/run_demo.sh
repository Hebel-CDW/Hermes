#!/usr/bin/env bash
# One-command local demo for Hermes (synthetic data only).
#
#   scripts/run_demo.sh              build UI if stale, seed a FRESH demo DB, serve, self-check, open browser
#   scripts/run_demo.sh --no-check   skip the automatic end-to-end self-check
#   scripts/run_demo.sh --no-open    do not open the browser
#   PORT=8001 scripts/run_demo.sh    use another port
#
# Every run starts from a clean database in a temp directory, so the demo always looks the
# same and nothing from a previous rehearsal is left behind. Press Ctrl+C to stop.
set -euo pipefail

cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
CHECK=1
OPEN=1
for arg in "$@"; do
    case "$arg" in
        --no-check) CHECK=0 ;;
        --no-open) OPEN=0 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 2 ;;
    esac
done

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# Seed the synthetic demo database WITHOUT refreshing the committed sample files under
# data/fixtures (`python -m scripts.ingest_fixtures` always rewrites them, which would dirty
# tracked files on every run). ingest() recreates the database from scratch, so seeding is
# repeatable.
seed_db() {
    .venv/bin/python -c '
import sys
from pathlib import Path
from scripts.ingest_fixtures import ingest
ingest(Path("data/fixtures/pilot_population.json"), Path(sys.argv[1]), write_samples=False)
' "$1" >/dev/null
}

SERVER=""
WORK=""
cleanup() {
    [ -n "$SERVER" ] && kill "$SERVER" 2>/dev/null || true
    # Remove only the scratch directory this run created.
    [ -n "$WORK" ] && [ -d "$WORK" ] && rm -rf "$WORK" || true
}
trap cleanup EXIT INT TERM

if [ ! -x .venv/bin/python ]; then
    echo "Missing .venv. Run once:  python3 -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'" >&2
    exit 1
fi
if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
    echo "Something is already serving on port ${PORT}. Stop it, or use PORT=<other> $0" >&2
    exit 1
fi

say "1/4  Web app"
if [ ! -d web/node_modules ]; then (cd web && npm ci --silent); fi
if [ ! -f web/dist/index.html ] || [ -n "$(find web/src web/index.html web/package.json -newer web/dist/index.html -print -quit)" ]; then
    (cd web && npm run build --silent)
    echo "built web/dist"
else
    echo "web/dist is up to date"
fi

say "2/4  Fresh synthetic demo database"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/hermes-demo.XXXXXX")"
export HERMES_TEST_MODE=1
export HERMES_DB_PATH="${WORK}/demo.db"
export PYTHONPATH="src:."
seed_db "${HERMES_DB_PATH}"
echo "seeded ${HERMES_DB_PATH}"

say "3/4  Starting Hermes on http://127.0.0.1:${PORT}"
.venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port "${PORT}" --log-level warning &
SERVER=$!
for _ in $(seq 1 40); do
    curl -sf "http://127.0.0.1:${PORT}/ready" >/dev/null 2>&1 && break
    kill -0 "$SERVER" 2>/dev/null || { echo "server failed to start" >&2; exit 1; }
    sleep 0.5
done
curl -sf "http://127.0.0.1:${PORT}/ready" >/dev/null || { echo "server never became ready" >&2; exit 1; }

if [ "$CHECK" = "1" ]; then
    say "4/4  Automatic end-to-end self-check"
    if .venv/bin/python -m scripts.live_smoke --base "http://127.0.0.1:${PORT}" | tail -3; then :; else
        echo "SELF-CHECK FAILED - do not demo until this is resolved" >&2
        exit 1
    fi
    # The self-check writes a request, decision and contest; restart clean so the demo starts empty.
    kill "$SERVER" 2>/dev/null || true
    wait "$SERVER" 2>/dev/null || true
    rm -f "${HERMES_DB_PATH}" "${HERMES_DB_PATH}-shm" "${HERMES_DB_PATH}-wal" "${HERMES_DB_PATH}.audit-anchor.json"
    seed_db "${HERMES_DB_PATH}"
    .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port "${PORT}" --log-level warning &
    SERVER=$!
    for _ in $(seq 1 40); do curl -sf "http://127.0.0.1:${PORT}/ready" >/dev/null 2>&1 && break; sleep 0.5; done
    echo "database reset to a clean demo state"
else
    say "4/4  Self-check skipped"
fi

say "Hermes is ready:  http://127.0.0.1:${PORT}"
echo "Sign in with 'Continue as a manager'. Walkthrough: docs/DEMO_RUNBOOK.md"
[ "$OPEN" = "1" ] && command -v open >/dev/null 2>&1 && open "http://127.0.0.1:${PORT}" || true
wait "$SERVER"
