"""Rate limiters: in-memory (single process) and PostgreSQL-backed (shared across replicas)."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from shared.db import HermesDB


class RateLimiter:
    """Simple in-memory sliding-window limiter. Correct only within one process."""

    def __init__(self, max_calls: int, window_seconds: float) -> None:
        self.max_calls = max_calls
        self.window = window_seconds
        self._hits: Dict[str, list] = defaultdict(list)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self.window
            self._hits[key] = [t for t in bucket if t >= cutoff]
            if len(self._hits[key]) >= self.max_calls:
                return False
            self._hits[key].append(now)
            return True


class PersistentRateLimiter:
    """Sliding-window limiter shared across every Hermes replica reading the
    same PostgreSQL database — same ``allow(key)`` contract as ``RateLimiter``,
    plus the database to check it against.

    SQLite deployments are always single-process here, so that path is
    unchanged: it delegates to the original in-memory ``RateLimiter`` (zero
    behavior change). Only PostgreSQL deployments use ``rate_limit_hits`` —
    confirmed necessary via a real two-instance test during the PostgreSQL
    migration spike, where the same principal got a full, separate 10-call
    budget on each of two replicas sharing one database. A per-key PostgreSQL
    advisory lock (``pg_advisory_xact_lock``) serializes concurrent callers
    for the SAME key only, so different principals/limiters never block each
    other — the same reasoning as ``append_audit``'s table lock, scoped
    tighter since unrelated keys must stay independent.
    """

    def __init__(self, max_calls: int, window_seconds: float, name: str) -> None:
        self.max_calls = max_calls
        self.window = window_seconds
        self.name = name
        self._memory = RateLimiter(max_calls, window_seconds)

    def allow(self, key: str, db: Optional["HermesDB"] = None) -> bool:
        # db=None (e.g. /api/requests/parse, which deliberately never opens
        # the database — Phase 16's "LLM parsing never touches the DB"
        # guarantee) falls back to the in-memory bucket, same as SQLite.
        if db is None or db.dialect != "postgres":
            return self._memory.allow(key)
        with db.session() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(?))", (f"{self.name}:{key}",))
            conn.execute(
                "DELETE FROM rate_limit_hits WHERE limiter_name=? AND key=? "
                "AND hit_at < clock_timestamp() - (? || ' seconds')::interval",
                (self.name, key, self.window),
            )
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM rate_limit_hits WHERE limiter_name=? AND key=?",
                (self.name, key),
            ).fetchone()["n"]
            if count >= self.max_calls:
                return False
            conn.execute(
                "INSERT INTO rate_limit_hits (limiter_name, key) VALUES (?, ?)",
                (self.name, key),
            )
            return True
