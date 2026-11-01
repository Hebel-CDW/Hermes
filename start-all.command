#!/bin/bash
# Hermes + Hermes Opportunity Intelligence — one-click demo launcher (macOS).
#
# Double-click in Finder, or run ./start-all.command. It checks the machine, starts Hermes through
# scripts/run_demo.sh (the single source of truth for building, seeding and serving), waits until the
# backend and the web app answer, then opens the browser. Ctrl+C stops it cleanly.
#
# It installs nothing. If something is missing it tells you the exact command to run (or run ./start.command
# once, which does the one-time setup). It keeps synthetic demo data in .demo-data/ across restarts and never
# resets it; to reset deliberately use scripts/reset_demo.sh.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT" || exit 1

RUN_DIR="$ROOT/.run"
LOCK="$RUN_DIR/lock"
URL_FILE="$RUN_DIR/url"
LOG="$RUN_DIR/start-all.log"
DATA_DIR="$ROOT/.demo-data"
mkdir -p "$RUN_DIR"

B=$'\033[1m'; R=$'\033[31m'; G=$'\033[32m'; D=$'\033[2m'; N=$'\033[0m'
step() { printf '\n%s%s%s\n' "$B" "$*" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$*"; }
fail() {
    printf '\n%s✗ %s%s\n' "$R" "$1" "$N" >&2
    shift
    for line in "$@"; do printf '    %s\n' "$line" >&2; done
    printf '\nPress Return to close this window...'; read -r _; exit 1
}

PID=""
OWN_LOCK=0
TAIL_PID=""
cleanup() {
    local code=$?
    trap - EXIT INT TERM
    [ -n "$TAIL_PID" ] && kill "$TAIL_PID" 2>/dev/null
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        printf '\n%sStopping Hermes...%s\n' "$B" "$N"
        kill "$PID" 2>/dev/null          # run_demo.sh stops only the server it started
        for _ in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.25; done
        kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null
        wait "$PID" 2>/dev/null
        printf 'Hermes stopped. Demo data in .demo-data/ is kept.\n'
    fi
    if [ "$OWN_LOCK" = "1" ]; then rm -f "$LOCK/pid" "$URL_FILE"; rmdir "$LOCK" 2>/dev/null; fi
    exit "$code"
}

printf '%sHermes · Workforce Intelligence%s  %s— demo launcher%s\n' "$B" "$N" "$D" "$N"

# ── Already running? (clicked twice) ────────────────────────────────────────────
if [ -d "$LOCK" ]; then
    OLD="$(cat "$LOCK/pid" 2>/dev/null || true)"
    if [ -n "$OLD" ] && kill -0 "$OLD" 2>/dev/null; then
        URL="$(cat "$URL_FILE" 2>/dev/null || true)"
        if [ -n "$URL" ] && curl -sf -m 3 "$URL/ready" >/dev/null 2>&1; then
            printf '\nHermes is already running at %s%s%s (started by another window).\n' "$B" "$URL" "$N"
            printf 'Opening it. To stop it, press Ctrl+C in the window that started it.\n'
            open "$URL" 2>/dev/null || true
            printf '\nPress Return to close this window...'; read -r _; exit 0
        fi
        fail "A Hermes launcher (pid $OLD) is still starting or not answering." \
             "Wait a few seconds and double-click again. If it never recovers, close its window (Ctrl+C) first."
    fi
    rm -f "$LOCK/pid" "$URL_FILE"; rmdir "$LOCK" 2>/dev/null   # stale lock from a crashed run
fi
mkdir "$LOCK" 2>/dev/null || fail "Another launcher just started. Double-click again in a few seconds."
echo $$ > "$LOCK/pid"; OWN_LOCK=1
trap cleanup EXIT INT TERM

# ── 1. Prerequisites ────────────────────────────────────────────────────────────
step "1/4  Checking this Mac"
command -v python3 >/dev/null 2>&1 || fail "Python 3 was not found." \
    "Install it from https://www.python.org/downloads/macos/ (or: brew install python3), then double-click again."
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' || fail "Python $(python3 -V 2>&1 | awk '{print $2}') is too old; Hermes needs 3.9 or newer." \
    "Install a newer Python from https://www.python.org/downloads/macos/."
command -v curl >/dev/null 2>&1 || fail "curl was not found (it ships with macOS; your PATH may be broken)."
command -v lsof >/dev/null 2>&1 || fail "lsof was not found (it ships with macOS; your PATH may be broken)."
ok "Python $(python3 -V 2>&1 | awk '{print $2}')"

[ -x .venv/bin/python ] || fail "The Python environment (.venv) does not exist yet." \
    "One-time setup, run either:  ./start.command   (installs inside this folder only, then starts Hermes)" \
    "or:  python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
if ! PYTHONPATH=src:. HERMES_TEST_MODE=1 .venv/bin/python -c 'import api.main' >"$RUN_DIR/import-check.log" 2>&1; then
    fail "The Python environment cannot load Hermes (missing packages?)." \
         "Run:  .venv/bin/pip install -e '.[dev]'" \
         "Details: $RUN_DIR/import-check.log"
fi
ok "Python environment loads the backend"

NEEDS_BUILD=0
if [ ! -f web/dist/index.html ] || [ -n "$(find web/src web/index.html web/package.json -newer web/dist/index.html -print -quit 2>/dev/null)" ]; then
    NEEDS_BUILD=1
fi
if [ "$NEEDS_BUILD" = "1" ]; then
    command -v npm >/dev/null 2>&1 || fail "The web app must be built, but Node.js (npm) was not found." \
        "Install the LTS version from https://nodejs.org/ (or: brew install node), then double-click again."
    [ -d web/node_modules ] || fail "The web app must be built, but its dependencies are not installed." \
        "Run once:  (cd web && npm ci)    or run ./start.command"
    ok "Web app will be built (sources changed since the last build)"
else
    ok "Web app build is up to date"
fi

# ── 2. Configuration (names only, never values) ─────────────────────────────────
step "2/4  Checking configuration"
if [ "$(printf '%s' "${HERMES_ENV:-}" | tr '[:upper:]' '[:lower:]')" = "production" ]; then
    fail "HERMES_ENV=production is set in this shell. The demo launcher only runs synthetic demo mode." \
         "Open a new Terminal window without it, or run: env -u HERMES_ENV ./start-all.command"
fi
if [ -n "${DATABASE_URL:-}" ]; then
    echo "  note: DATABASE_URL is set in this shell; ignoring it so the demo uses only its own local database."
    unset DATABASE_URL
fi
ok "Mode: synthetic demo (HERMES_TEST_MODE=1, local SQLite, no real integrations)"
ok "Demo data folder: .demo-data/ (kept across restarts)"

# ── 3. Start (run_demo.sh does build → seed-if-empty → serve) ───────────────────
step "3/4  Starting Hermes"
rm -f "$URL_FILE"; : > "$LOG"
"$ROOT/scripts/run_demo.sh" --persist "$DATA_DIR" --no-open --url-file "$URL_FILE" >"$LOG" 2>&1 &
PID=$!
echo "$PID" > "$LOCK/pid"
tail -n +1 -f "$LOG" 2>/dev/null | sed -u 's/^/  /' &
TAIL_PID=$!

URL=""
for _ in $(seq 1 480); do                       # up to ~4 minutes (first build can be slow)
    kill -0 "$PID" 2>/dev/null || break
    if [ -s "$URL_FILE" ]; then URL="$(cat "$URL_FILE")"; break; fi
    sleep 0.5
done
kill "$TAIL_PID" 2>/dev/null; TAIL_PID=""
if [ -z "$URL" ]; then
    fail "Hermes did not start." "Last log lines (full log: $LOG):" "$(tail -n 12 "$LOG" | sed 's/^/      /')"
fi

# ── 4. Verify backend + web app before opening anything ─────────────────────────
step "4/4  Verifying"
READY=""
for _ in $(seq 1 40); do
    READY="$(curl -sf -m 3 "$URL/ready" 2>/dev/null)" && break
    sleep 0.5
done
[ -n "$READY" ] || fail "Backend did not answer at $URL/ready." "See $LOG"
HEALTH="$(curl -sf -m 3 "$URL/health" 2>/dev/null || true)"
echo "$HEALTH" | grep -q '"status":"ok"' || fail "Backend health check failed at $URL/health." "See $LOG"
ok "Backend health: ok"
INDEX="$(curl -sf -m 5 "$URL/" 2>/dev/null || true)"
echo "$INDEX" | grep -q 'id="root"' || fail "The web app is not being served at $URL/." "Rebuild it:  (cd web && npm run build)"
ASSET="$(printf '%s' "$INDEX" | grep -o '/assets/[^"]*\.js' | head -1)"
if [ -n "$ASSET" ]; then
    curl -sf -m 5 -o /dev/null "$URL$ASSET" || fail "The web app's script $ASSET is missing."
fi
ok "Web app: served"
AUTH="$(printf '%s' "$READY" | sed -n 's/.*"auth_mode":"\([^"]*\)".*/\1/p')"
BUILT="$(date -r web/dist/index.html '+%Y-%m-%d %H:%M' 2>/dev/null || echo unknown)"

printf '\n'
printf '  %s┌──────────────────────────────────────────────────────────────┐%s\n' "$B" "$N"
printf '  %s│  HERMES · Workforce Intelligence + Opportunity Intelligence  │%s\n' "$B" "$N"
printf '  %s└──────────────────────────────────────────────────────────────┘%s\n' "$B" "$N"
printf '   Application   %s%s%s\n' "$B" "$URL" "$N"
printf '   Backend API   %s/api   (docs: %s/docs)\n' "$URL" "$URL"
printf '   Frontend      built web app served by the backend (build %s)\n' "$BUILT"
printf '   Health        %sok%s   (ready: %s, sign-in: %s)\n' "$G" "$N" "yes" "${AUTH:-development}"
printf '   Mode          SYNTHETIC DEMO DATA — no real employee, payroll or customer data\n'
printf '   Status        %sRUNNING%s   (pid %s)\n' "$G" "$N" "$PID"
printf '   Walkthrough   docs/DEMO_RUNBOOK.md   ·   reset: scripts/reset_demo.sh\n'
printf '\n   Keep this window open. Press %sCtrl+C%s to stop Hermes.\n\n' "$B" "$N"

open "$URL" 2>/dev/null || true
wait "$PID"
CODE=$?
printf '\n%sHermes stopped unexpectedly (exit %s).%s See %s\n' "$R" "$CODE" "$N" "$LOG"
tail -n 10 "$LOG" | sed 's/^/    /'
printf '\nPress Return to close this window...'; read -r _
