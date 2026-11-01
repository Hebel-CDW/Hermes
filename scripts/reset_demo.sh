#!/usr/bin/env bash
# DEMO-ONLY, EXPLICIT reset of the persistent synthetic demo data used by start-all.command.
#
#   scripts/reset_demo.sh            ask, then delete the demo database and re-seed on the next start
#   scripts/reset_demo.sh --yes      same without asking
#
# What it deletes: only the files inside .demo-data/ that Hermes itself created
# (demo.db and its -wal/-shm/audit-anchor files, and hoi_store/), and only when
# .demo-data/ carries the marker file written by run_demo.sh --persist.
# What it never touches: any other path, any other database, tracked files, or a running server
# (it refuses to run while the demo is up: stop it with Ctrl+C in the start-all window first).
# Nothing in start-all.command calls this script; a restart never resets anything.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR=".demo-data"
YES=0
[ "${1:-}" = "--yes" ] && YES=1

if [ ! -d "$DIR" ]; then echo "Nothing to reset: $DIR does not exist."; exit 0; fi
if [ -L "$DIR" ]; then
    echo "Refusing: $DIR is a symbolic link; resetting it could delete files elsewhere." >&2
    exit 1
fi
if [ ! -f "$DIR/.hermes-demo-home" ]; then
    echo "Refusing: $DIR has no .hermes-demo-home marker, so it is not demo data created by Hermes." >&2
    exit 1
fi
PIDFILE=".run/lock/pid"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
    echo "Refusing: the demo is running (pid $(cat "$PIDFILE")). Stop it with Ctrl+C in its window, then retry." >&2
    exit 1
fi
# Also refuse if any process has the demo database open (e.g. run_demo.sh --persist started without the launcher).
if [ -f "$DIR/demo.db" ] && [ -n "$(lsof -t "$DIR/demo.db" 2>/dev/null)" ]; then
    echo "Refusing: a running process has $DIR/demo.db open. Stop it first." >&2
    exit 1
fi
if [ "$YES" != "1" ]; then
    printf 'Delete the synthetic demo data in %s/ ? It is re-seeded on the next start. [y/N] ' "$DIR"
    read -r ans
    case "$ans" in y|Y|yes|YES) ;; *) echo "Cancelled."; exit 0 ;; esac
fi
for f in demo.db demo.db-wal demo.db-shm demo.db.audit-anchor.json; do rm -f "${DIR:?}/$f"; done
rm -rf "${DIR:?}/hoi_store"
echo "Demo data reset. It will be re-seeded the next time start-all.command runs."
