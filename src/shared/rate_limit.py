"""Simple in-memory token bucket rate limiter."""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Dict, Tuple


class RateLimiter:
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
