#!/bin/bash
# Hermes — one-click Mac launcher.
#
# Double-click this file in Finder (or run it: ./start.command). It installs everything
# the project needs inside this folder only (a Python venv and node_modules — nothing is
# installed system-wide) and then starts the local demo via scripts/run_demo.sh.
#
# Requires Python 3.9+ and Node.js (with npm) already on the Mac. If either is missing,
# this prints where to get it and stops rather than guessing.
set -euo pipefail

# Always run from the folder this script lives in, no matter where it was double-clicked.
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\n\033[31m%s\033[0m\n' "$*" >&2; printf '\nPress Return to close this window...'; read -r _; exit 1; }

say "Hermes — checking prerequisites"

if ! command -v python3 >/dev/null 2>&1; then
    fail "Python 3 was not found. Install it from https://www.python.org/downloads/macos/ (or 'brew install python3'), then double-click start.command again."
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)'; then
    fail "Python $(python3 -V 2>&1 | awk '{print $2}') was found, but Hermes needs 3.9 or newer. Install a newer Python from https://www.python.org/downloads/macos/, then try again."
fi
if ! command -v npm >/dev/null 2>&1; then
    fail "Node.js (with npm) was not found. Install the LTS version from https://nodejs.org/ (or 'brew install node'), then double-click start.command again."
fi
echo "Python: $(python3 -V 2>&1)   Node: $(node -v 2>&1)   npm: $(npm -v 2>&1)"

say "1/2  Python dependencies"
if [ ! -x .venv/bin/python ]; then
    echo "Creating .venv ..."
    python3 -m venv .venv
fi
# -q keeps this quiet on repeat runs; it still self-heals if pyproject.toml changed.
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -e ".[dev]"
echo "Python dependencies ready."

say "2/2  Web app dependencies"
if [ ! -d web/node_modules ]; then
    (cd web && npm ci --silent)
    echo "Node dependencies installed."
else
    echo "web/node_modules already present."
fi

# scripts/run_demo.sh takes it from here: builds the UI if stale, seeds a fresh synthetic
# demo database, starts the server, runs its own 55-point self-check, and opens the browser.
# This window stays open while Hermes runs; close it (or Ctrl+C) to stop the server.
exec scripts/run_demo.sh
