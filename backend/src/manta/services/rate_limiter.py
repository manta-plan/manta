import threading
import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    """Allows at most `limit` hits per key in any sliding window of `window_seconds`.

    State lives in this process's memory: it resets on restart and isn't shared
    between workers, so with N workers the effective limit is up to N times `limit`.
    That's fine while manta runs as a single uvicorn process; move this to a shared
    store (e.g. Redis) before scaling out.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        # Sync FastAPI dependencies run in a thread pool, so hits can race.
        self._lock = threading.Lock()

    def hit(self, key: str) -> float | None:
        """Records a hit for `key` if it's within the limit and returns None, or
        records nothing and returns how many seconds until the next hit is allowed."""
        now = self._clock()
        with self._lock:
            self._forget_expired(now)
            hits = self._hits.setdefault(key, deque())
            if len(hits) >= self._limit:
                return max(hits[0] + self._window - now, 0.0)
            hits.append(now)
            return None

    def _forget_expired(self, now: float) -> None:
        # Drops every key's expired hits, and keys left with none, so memory stays
        # bounded by the clients seen within one window rather than growing forever.
        cutoff = now - self._window
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if not hits:
                del self._hits[key]
