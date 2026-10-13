"""In-memory token-bucket rate limiting for the engine API.

Buckets are keyed per client and route class. Limits are enforced before the
request reaches route handlers; exceeded buckets return 429 with Retry-After.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    capacity: int
    refill_per_minute: float
    tokens: float
    updated: float = field(default_factory=time.monotonic)

    def take(self, now: float) -> bool:
        elapsed = max(0.0, now - self.updated)
        self.tokens = min(
            float(self.capacity), self.tokens + elapsed * self.refill_per_minute / 60.0
        )
        self.updated = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    def retry_after_seconds(self, now: float) -> int:
        deficit = 1.0 - self.tokens
        return max(1, int(deficit * 60.0 / self.refill_per_minute) + (1 if deficit > 0 else 0))


class RateLimiter:
    def __init__(
        self,
        *,
        ingest_per_minute: int,
        classify_per_minute: int,
        enabled: bool = True,
        max_buckets: int = 10_000,
    ) -> None:
        self.limits = {"ingest": ingest_per_minute, "classify": classify_per_minute}
        self.enabled = enabled
        self.max_buckets = max_buckets
        self._buckets: dict[tuple[str, str], TokenBucket] = {}

    def route_class(self, path: str, method: str = "POST") -> str | None:
        if method.upper() != "POST":
            return None
        if (
            path.endswith("/events")
            or path.endswith("/events/batch")
            or "/events:" in path
            or path.endswith("/webhook")
            or "/webhooks/" in path
        ):
            return "ingest"
        if "/classify" in path or path.endswith("/runs"):
            return "classify"
        return None

    def _evict_stale(self, now: float) -> None:
        if len(self._buckets) < self.max_buckets:
            return
        cutoff = now - 3600.0
        stale_keys = [k for k, b in self._buckets.items() if b.updated < cutoff]
        for k in stale_keys:
            self._buckets.pop(k, None)
        if len(self._buckets) >= self.max_buckets:
            oldest_key = min(self._buckets, key=lambda k: self._buckets[k].updated)
            self._buckets.pop(oldest_key, None)

    def check(
        self,
        key: str,
        path: str,
        *,
        method: str = "POST",
        now: float | None = None,
    ) -> tuple[bool, int, int, int]:
        """Return (allowed, retry_after_seconds, limit, remaining)."""
        route_class = self.route_class(path, method=method)
        if not self.enabled or route_class is None:
            return True, 0, 0, 0
        moment = time.monotonic() if now is None else now
        capacity = self.limits[route_class]
        bucket = self._buckets.get((key, route_class))
        if bucket is None or bucket.capacity != capacity:
            self._evict_stale(moment)
            bucket = TokenBucket(
                capacity=capacity,
                refill_per_minute=capacity,
                tokens=float(capacity),
                updated=moment,
            )
            self._buckets[(key, route_class)] = bucket
        allowed = bucket.take(moment)
        return (
            allowed,
            bucket.retry_after_seconds(moment) if not allowed else 0,
            capacity,
            int(bucket.tokens),
        )
