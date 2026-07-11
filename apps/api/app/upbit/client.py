"""Async Upbit public Quotation API client.

Only public endpoints are used (no auth). All requests go through the
central rate limiter; 429/418 handling and exponential backoff included.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from app.config import Settings, settings as default_settings
from app.upbit.rate_limiter import RateLimiterRegistry, parse_remaining_req

logger = logging.getLogger(__name__)

# timeframe key -> (upbit path suffix, minutes per candle); "1d" is special.
TIMEFRAMES: dict[str, int | None] = {
    "1m": 1, "3m": 3, "5m": 5, "10m": 10, "15m": 15,
    "30m": 30, "60m": 60, "240m": 240, "1d": None,
}

MAX_CANDLES_PER_REQUEST = 200

GROUP_MARKET = "quotation-market"
GROUP_CANDLE = "quotation-candle"


class UpbitError(Exception):
    pass


class UpbitClient:
    def __init__(self, cfg: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        self.cfg = cfg or default_settings
        self._client = client
        self._owns_client = client is None
        self.limiter = RateLimiterRegistry()
        self.limiter.register(GROUP_MARKET, self.cfg.rate_limit_quotation_market)
        self.limiter.register(GROUP_CANDLE, self.cfg.rate_limit_quotation_candle)

    async def __aenter__(self) -> "UpbitClient":
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.cfg.upbit_base_url,
                timeout=self.cfg.http_timeout_seconds,
            )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def _get(self, group: str, path: str, params: dict[str, Any] | None = None) -> Any:
        assert self._client is not None, "use `async with UpbitClient()`"
        bucket = self.limiter.bucket(group)
        last_error: Exception | None = None
        for attempt in range(self.cfg.max_retries + 1):
            await bucket.acquire()
            try:
                resp = await self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                last_error = exc
                await self._sleep_backoff(attempt)
                continue

            bucket.feed_remaining(parse_remaining_req(resp.headers.get("Remaining-Req")))

            if resp.status_code == 429:
                # Too many requests: stop the group immediately, back off, retry.
                bucket.block_for(min(2 ** attempt, self.cfg.backoff_max_seconds))
                last_error = UpbitError("HTTP 429 Too Many Requests")
                continue
            if resp.status_code == 418:
                # IP temporarily banned: honor a long block.
                retry_after = float(resp.headers.get("Retry-After", "60"))
                bucket.block_for(retry_after)
                last_error = UpbitError(f"HTTP 418, blocked for {retry_after}s")
                continue
            if resp.status_code >= 500:
                last_error = UpbitError(f"HTTP {resp.status_code}")
                await self._sleep_backoff(attempt)
                continue
            if resp.status_code >= 400:
                raise UpbitError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        raise UpbitError(f"request failed after retries: {last_error}")

    async def _sleep_backoff(self, attempt: int) -> None:
        delay = min(self.cfg.backoff_base_seconds * (2 ** attempt), self.cfg.backoff_max_seconds)
        await asyncio.sleep(delay)

    # ---- endpoints -------------------------------------------------------

    async def get_markets(self, is_details: bool = True) -> list[dict[str, Any]]:
        return await self._get(GROUP_MARKET, "/v1/market/all", {"is_details": str(is_details).lower()})

    async def get_candles(
        self,
        market: str,
        timeframe: str,
        to_utc: datetime | None = None,
        count: int = MAX_CANDLES_PER_REQUEST,
    ) -> list[dict[str, Any]]:
        """One page of candles, newest first (Upbit native order)."""
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        unit = TIMEFRAMES[timeframe]
        path = "/v1/candles/days" if unit is None else f"/v1/candles/minutes/{unit}"
        params: dict[str, Any] = {"market": market, "count": min(count, MAX_CANDLES_PER_REQUEST)}
        if to_utc is not None:
            params["to"] = to_utc.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return await self._get(GROUP_CANDLE, path, params)

    async def get_candles_range(
        self,
        market: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        progress: Callable[[int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all candles in [start_utc, end_utc] with automatic pagination.

        Returned newest-first raw Upbit dicts; normalization happens in the
        data layer. `progress` receives the cumulative candle count.
        """
        out: list[dict[str, Any]] = []
        # Upbit `to` is exclusive of the given time's candle in practice for
        # minute candles; request slightly past the end to be safe, then trim.
        cursor = end_utc + timedelta(seconds=1)
        while True:
            if cancelled and cancelled():
                break
            page = await self.get_candles(market, timeframe, to_utc=cursor)
            if not page:
                break
            out.extend(page)
            if progress:
                progress(len(out))
            oldest = min(
                datetime.fromisoformat(c["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
                for c in page
            )
            if oldest <= start_utc or len(page) < MAX_CANDLES_PER_REQUEST:
                break
            cursor = oldest
        # Trim outside the requested window.
        def ts(c: dict[str, Any]) -> datetime:
            return datetime.fromisoformat(c["candle_date_time_utc"]).replace(tzinfo=timezone.utc)
        return [c for c in out if start_utc <= ts(c) <= end_utc]
