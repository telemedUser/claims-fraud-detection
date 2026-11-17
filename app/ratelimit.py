"""Sliding-window rate limiter for policy lookup (requirement 7.9).

Each key (client IP, policy number) may make `limit` attempts in any `window` seconds. An attempt is
admitted only if every key it touches is under the limit, so a rejected attempt is not counted and
`Retry-After` is the time until the oldest counted attempt leaves the window.
"""
import math
import threading
import time
from collections import deque
from typing import Callable, Iterable

from app.settings import get_settings

DEFAULT_RATE = "5/minute"
_UNITS = {"second": 1, "sec": 1, "s": 1, "minute": 60, "min": 60, "m": 60, "hour": 3600, "h": 3600}


def parse_rate(spec: str | None) -> tuple[int, float]:
    """Parse '5/minute' (units: second, minute, hour) into (limit, window_seconds).
    Invalid values fall back to the default."""
    for candidate in (spec, DEFAULT_RATE):
        try:
            count, unit = (candidate or "").strip().lower().split("/", 1)
            limit, seconds = int(count), _UNITS[unit.strip()]
            if limit > 0:
                return limit, float(seconds)
        except (ValueError, KeyError):
            pass
    return 5, 60.0


class SlidingWindowLimiter:
    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._hits.get(key)
        if q is None:
            return deque()
        while q and q[0] <= now - self.window:
            q.popleft()
        if not q:
            del self._hits[key]
            return deque()
        return q

    def acquire(self, keys: Iterable[str]) -> float | None:
        """Record one attempt against all keys. Returns None if admitted, otherwise the seconds to wait."""
        keys = list(dict.fromkeys(keys))
        with self._lock:
            now = self._clock()
            wait = 0.0
            for k in keys:
                q = self._prune(k, now)
                if len(q) >= self.limit:
                    wait = max(wait, q[0] + self.window - now)
            if wait > 0:
                return wait
            for k in keys:
                self._hits.setdefault(k, deque()).append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def retry_after_seconds(wait: float) -> int:
    return max(1, math.ceil(wait))


_lookup_limiter: SlidingWindowLimiter | None = None


def lookup_limiter() -> SlidingWindowLimiter:
    global _lookup_limiter
    if _lookup_limiter is None:
        limit, window = parse_rate(get_settings().lookup_rate)
        _lookup_limiter = SlidingWindowLimiter(limit, window)
    return _lookup_limiter


def reset_lookup_limiter() -> None:
    """Drop all state and re-read LOOKUP_RATE on next use (used by tests)."""
    global _lookup_limiter
    _lookup_limiter = None
