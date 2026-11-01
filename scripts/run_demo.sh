#!/usr/bin/env bash
# One-command local demo for Hermes (synthetic data only).
#
#   scripts/run_demo.sh              build UI if stale, seed a FRESH demo DB, serve, self-check, open browser
#   scripts/run_demo.sh --no-check   skip the automatic end-to-end self-check
#   scripts/run_demo.sh --no-open    do not open the browser
#   PORT=8001 scripts/run_demo.sh    use another port
#   scripts/run_demo.sh --persist DIR   keep the demo database in DIR across restarts. It is seeded only
#                                       when DIR holds no database yet and is never reset automatically
#                                       (reset explicitly with scripts/reset_demo.sh). Skips the self-check,
#                                       because the self-check writes records.
#   scripts/run_demo.sh --url-file F    write the final URL to F once the server is ready
#
# Without --persist every run starts from a clean database in a temp directory, so the demo always
# looks the same and nothing from a previous rehearsal is left behind. Press Ctrl+C to stop.
set -euo pipefail

cd "$(dirname "$0")/.."
PORT_WAS_SET="${PORT:-}"
PORT="${PORT:-8000}"
CHECK=1
OPEN=1
PERSIST=""
URL_FILE=""
while [ $# -gt 0 ]; do
    case "$1" in
        --no-check) CHECK=0 ;;
        --no-open) OPEN=0 ;;
        --persist) [ $# -ge 2 ] || { echo "--persist needs a directory" >&2; exit 2; }; PERSIST="$2"; shift ;;
        --url-file) [ $# -ge 2 ] || { echo "--url-file needs a path" >&2; exit 2; }; URL_FILE="$2"; shift ;;
        -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

# Seed the synthetic demo organisation (36 people, 10 role scenarios, one open dispute) into a
# fresh database. seed() recreates the database from scratch and never rewrites the committed
# sample files under data/fixtures, so seeding is repeatable and leaves tracked files alone.
seed_db() {
    .venv/bin/python -m scripts.seed_demo_org --db "$1" >/dev/null
    # Opportunity Intelligence: synthetic capacity, Finance inputs, benchmarks and one uploaded SOW.
    .venv/bin/python -m scripts.seed_hoi_demo --db "$1" --ready-copy >/dev/null
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
port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
if port_busy "${PORT}"; then
    if [ -n "${PORT_WAS_SET:-}" ]; then
        echo "Port ${PORT} is already in use. Stop whatever is using it, or pick another with PORT=<other> $0" >&2
        exit 1
    fi
    # Default port is taken (another app, Docker, an old run): use the next free one.
    BUSY="${PORT}"
    while port_busy "${PORT}"; do PORT=$((PORT + 1)); done
    echo "Port ${BUSY} is in use by another program; using ${PORT} instead."
fi

say "1/4  Web app"
if [ ! -d web/node_modules ]; then (cd web && npm ci --silent); fi
if [ ! -f web/dist/index.html ] || [ -n "$(find web/src web/index.html web/package.json -newer web/dist/index.html -print -quit)" ]; then
    (cd web && npm run build --silent)
    echo "built web/dist"
else
    echo "web/dist is up to date"
fi

export HERMES_TEST_MODE=1
export PYTHONPATH="src:."
# Copilot: local Ollama. If it is not running the copilot answers from the data directly instead.
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:7b-instruct}"
if [ -n "$PERSIST" ]; then
    say "2/4  Persistent synthetic demo database"
    mkdir -p "$PERSIST"
    PERSIST="$(cd "$PERSIST" && pwd)"
    export HERMES_DB_PATH="${PERSIST}/demo.db"
    export HOI_STORAGE_DIR="${PERSIST}/hoi_store"
    CHECK=0
    if [ -f "${HERMES_DB_PATH}" ]; then
        echo "keeping existing demo database ${HERMES_DB_PATH} (not reset; see scripts/reset_demo.sh)"
    else
        # Seed beside the final name and move into place, so an interrupted seed never leaves a half-built database.
        rm -f "${HERMES_DB_PATH}.seeding" "${HERMES_DB_PATH}.seeding-wal" "${HERMES_DB_PATH}.seeding-shm"
        seed_db "${HERMES_DB_PATH}.seeding"
        mv "${HERMES_DB_PATH}.seeding" "${HERMES_DB_PATH}"
        rm -f "${HERMES_DB_PATH}.seeding-wal" "${HERMES_DB_PATH}.seeding-shm"
        [ -f "${HERMES_DB_PATH}.seeding.audit-anchor.json" ] && mv "${HERMES_DB_PATH}.seeding.audit-anchor.json" "${HERMES_DB_PATH}.audit-anchor.json"
        echo "seeded ${HERMES_DB_PATH}"
    fi
    # Marker read by scripts/reset_demo.sh: it only ever deletes inside a directory carrying this file.
    echo "Hermes synthetic demo data. Safe to reset with scripts/reset_demo.sh." > "${PERSIST}/.hermes-demo-home"
else
    say "2/4  Fresh synthetic demo database"
    WORK="$(mktemp -d "${TMPDIR:-/tmp}/hermes-demo.XXXXXX")"
    export HERMES_DB_PATH="${WORK}/demo.db"
    export HOI_STORAGE_DIR="${WORK}/hoi_store"
    seed_db "${HERMES_DB_PATH}"
    echo "seeded ${HERMES_DB_PATH}"
fi

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

# Load the copilot model into memory now so the first question in the room is not slow.
if curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    (curl -s -m 120 http://127.0.0.1:11434/api/generate -d "{\"model\":\"${OLLAMA_MODEL}\",\"prompt\":\"hi\",\"stream\":false,\"keep_alive\":\"60m\",\"options\":{\"num_ctx\":${OLLAMA_NUM_CTX:-8192}}}" >/dev/null 2>&1 &)
    echo "Copilot model ${OLLAMA_MODEL}: warming up"
else
    echo "Ollama is not running: the copilot will answer directly from the data instead."
fi

say "Hermes is ready:  http://127.0.0.1:${PORT}"
echo "Sign in with 'Continue as a manager'. Walkthrough: docs/DEMO_RUNBOOK.md"
[ -n "$URL_FILE" ] && echo "http://127.0.0.1:${PORT}" > "$URL_FILE"
[ "$OPEN" = "1" ] && command -v open >/dev/null 2>&1 && open "http://127.0.0.1:${PORT}" || true
wait "$SERVER"
