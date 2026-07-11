"""Upbit client tests with a mocked HTTP transport (no real API calls)."""
from datetime import datetime, timezone

import httpx
import pytest

from app.config import RateLimitPolicy, Settings
from app.upbit.client import UpbitClient


def fast_settings(**kw) -> Settings:
    return Settings(
        rate_limit_quotation_market=RateLimitPolicy(requests_per_second=10_000, burst=100),
        rate_limit_quotation_candle=RateLimitPolicy(requests_per_second=10_000, burst=100),
        backoff_base_seconds=0.001,
        backoff_max_seconds=0.01,
        **kw,
    )


def candle(ts: str, price: float = 100.0) -> dict:
    return {
        "market": "KRW-BTC", "candle_date_time_utc": ts,
        "opening_price": price, "high_price": price, "low_price": price,
        "trade_price": price, "candle_acc_trade_volume": 1.0,
        "candle_acc_trade_price": price,
    }


@pytest.mark.asyncio
async def test_pagination_fetches_multiple_pages():
    """3 hours of 1m candles = 180 candles = 1 page; force 2 pages with 400."""
    start = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 1, 1, 6, 39, tzinfo=timezone.utc)  # 400 minutes
    all_ts = [
        (start.replace(tzinfo=None) + __import__("datetime").timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S")
        for i in range(400)
    ]

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        to = request.url.params.get("to")
        cutoff = datetime.strptime(to, "%Y-%m-%dT%H:%M:%SZ") if to else None
        eligible = [t for t in all_ts if cutoff is None or datetime.fromisoformat(t) < cutoff]
        page = sorted(eligible, reverse=True)[:200]
        return httpx.Response(200, json=[candle(t) for t in page])

    transport = httpx.MockTransport(handler)
    async with UpbitClient(fast_settings(), httpx.AsyncClient(transport=transport, base_url="https://api.upbit.com")) as c:
        out = await c.get_candles_range("KRW-BTC", "1m", start, end)
    assert len(calls) >= 2
    assert len(out) == 400
    ts_set = {o["candle_date_time_utc"] for o in out}
    assert len(ts_set) == 400  # no duplicates


@pytest.mark.asyncio
async def test_429_retries_then_succeeds():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(429)
        return httpx.Response(200, json=[candle("2026-01-01T00:00:00")])

    transport = httpx.MockTransport(handler)
    async with UpbitClient(fast_settings(), httpx.AsyncClient(transport=transport, base_url="https://api.upbit.com")) as c:
        out = await c.get_candles("KRW-BTC", "5m")
    assert attempts["n"] == 3
    assert len(out) == 1


@pytest.mark.asyncio
async def test_retry_limit_exhausted_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    cfg = fast_settings(max_retries=2)
    async with UpbitClient(cfg, httpx.AsyncClient(transport=transport, base_url="https://api.upbit.com")) as c:
        with pytest.raises(Exception, match="failed after retries"):
            await c.get_candles("KRW-BTC", "5m")


@pytest.mark.asyncio
async def test_4xx_no_retry():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        return httpx.Response(400, json={"error": {"message": "bad"}})

    transport = httpx.MockTransport(handler)
    async with UpbitClient(fast_settings(), httpx.AsyncClient(transport=transport, base_url="https://api.upbit.com")) as c:
        with pytest.raises(Exception):
            await c.get_candles("KRW-BTC", "5m")
    assert attempts["n"] == 1
