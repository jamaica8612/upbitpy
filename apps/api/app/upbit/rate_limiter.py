"""Centralized async rate limiter for Upbit API groups.

Token-bucket per group. Also honors the `Remaining-Req` response header and
reacts to HTTP 429/418 with exponential backoff handled by the client.
"""
from __future__ import annotations

import asyncio
import time

from app.config import RateLimitPolicy


class TokenBucket:
    def __init__(self, policy: RateLimitPolicy) -> None:
        self.rate = policy.requests_per_second
        self.capacity = max(policy.burst, 1)
        self.tokens = float(self.capacity)
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()
        # When Upbit tells us to slow down (429/418), block until this time.
        self.blocked_until: float = 0.0

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                if now < self.blocked_until:
                    wait = self.blocked_until - now
                else:
                    self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                    self.updated = now
                    if self.tokens >= 1:
                        self.tokens -= 1
                        return
                    wait = (1 - self.tokens) / self.rate
            await asyncio.sleep(wait)

    def block_for(self, seconds: float) -> None:
        self.blocked_until = max(self.blocked_until, time.monotonic() + seconds)

    def feed_remaining(self, remaining_sec: int | None) -> None:
        """Adapt to the Remaining-Req header: if the per-second budget is
        nearly exhausted, drain the local bucket so we naturally pause."""
        if remaining_sec is not None and remaining_sec <= 1:
            self.tokens = min(self.tokens, 0.0)


class RateLimiterRegistry:
    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}

    def register(self, group: str, policy: RateLimitPolicy) -> None:
        self._buckets[group] = TokenBucket(policy)

    def bucket(self, group: str) -> TokenBucket:
        if group not in self._buckets:
            raise KeyError(f"rate limit group not registered: {group}")
        return self._buckets[group]


def parse_remaining_req(header_value: str | None) -> int | None:
    """Parse Upbit's `Remaining-Req: group=default; min=1799; sec=29` header."""
    if not header_value:
        return None
    try:
        parts = dict(
            kv.strip().split("=", 1) for kv in header_value.split(";") if "=" in kv
        )
        return int(parts.get("sec", "")) if parts.get("sec") else None
    except (ValueError, AttributeError):
        return None
