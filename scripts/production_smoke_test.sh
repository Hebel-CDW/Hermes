#!/usr/bin/env bash
# Production acceptance test for a RUNNING Hermes instance.
#
#   ./scripts/production_smoke_test.sh                       # http://127.0.0.1:8000
#   ./scripts/production_smoke_test.sh https://hermes.example.com
#   HERMES_REAL_DB=/path/to/real.db ./scripts/production_smoke_test.sh  # adds the real-data gate
#
# This is a thin wrapper, not a reimplementation: the actual checks already
# live in scripts/live_smoke.py (health, auth, RBAC, deterministic ranking,
# decisions, audit, LLM-assist fallback, real-data-governance labeling) and
# scripts/audit_real_db_leakage.py (real-DB leakage gate). Duplicating that
# logic here would just create a second place for it to drift out of sync.
#
# Exit code 0 only if every check passes. Prints PASS/FAIL per section plus
# one final verdict line.
set -uo pipefail
cd "$(dirname "$0")/.."

BASE="${1:-http://127.0.0.1:8000}"
FAIL=0

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }

say "== Deployment reachability =="
if curl -sf --max-time 5 "${BASE}/health" >/dev/null; then
    echo "PASS  ${BASE}/health reachable"
else
    echo "FAIL  ${BASE}/health unreachable — is the app running and BASE correct?"
    FAIL=1
fi

if curl -sf --max-time 5 "${BASE}/ready" >/dev/null; then
    echo "PASS  ${BASE}/ready (database open, trust policy passed, audit chain verified)"
else
    echo "FAIL  ${BASE}/ready failed — check: secrets set? database path writable? audit chain intact?"
    FAIL=1
fi

if [ "$FAIL" = "1" ]; then
    say "ABORT: deployment is not reachable/ready — skipping workflow checks that would need it."
    echo "VERDICT: FAIL"
    exit 1
fi

say "== Critical workflow, security boundary, audit, LLM-assist fallback, real-data labeling =="
echo "(delegating to scripts.live_smoke — see its own PASS/FAIL lines above)"
if .venv/bin/python -m scripts.live_smoke --base "${BASE}"; then
    echo "PASS  full workflow/security/audit/LLM-assist/governance-labeling suite"
else
    echo "FAIL  one or more live_smoke checks failed — see PASS/FAIL lines above for which"
    FAIL=1
fi

say "== Real-data leakage gate =="
if [ -n "${HERMES_REAL_DB:-}" ]; then
    if .venv/bin/python scripts/audit_real_db_leakage.py "${HERMES_REAL_DB}"; then
        echo "PASS  no identity/client-name leakage found in ${HERMES_REAL_DB}"
    else
        echo "FAIL  leakage found — do NOT enable any real-backed demo mode until resolved"
        FAIL=1
    fi
else
    echo "SKIP  HERMES_REAL_DB not set — only meaningful for a deployment serving the real database"
fi

say "== Verdict =="
if [ "$FAIL" = "0" ]; then
    echo "VERDICT: PASS"
    exit 0
else
    echo "VERDICT: FAIL — see FAIL lines above for exact, actionable causes"
    exit 1
fi
