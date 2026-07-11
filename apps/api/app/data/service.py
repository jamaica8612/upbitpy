"""Data service: decides what to download and keeps the cache warm.

Given (market, timeframe, start, end) it loads cached candles, fetches only
the missing head/tail from Upbit, merges, and returns an ascending frame.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd

from app.data.store import (
    CandleStore,
    drop_incomplete_last_candle,
    fill_synthetic,
    normalize_candles,
    timeframe_delta,
)
from app.upbit.client import UpbitClient

logger = logging.getLogger(__name__)


async def ensure_candles(
    store: CandleStore,
    market: str,
    timeframe: str,
    start_utc: datetime,
    end_utc: datetime,
    progress: Callable[[str, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> pd.DataFrame:
    """Return candles for the window, downloading only missing ranges."""
    now = datetime.now(timezone.utc)
    end_utc = min(end_utc, now)
    cached = store.load(market, timeframe, start_utc, end_utc)
    step = timeframe_delta(timeframe)

    missing: list[tuple[datetime, datetime]] = []
    if cached.empty:
        missing.append((start_utc, end_utc))
    else:
        first, last = cached["ts"].iloc[0], cached["ts"].iloc[-1]
        if first - pd.Timestamp(start_utc) > step:
            missing.append((start_utc, (first - step).to_pydatetime()))
        if pd.Timestamp(end_utc) - last > step:
            missing.append(((last + step).to_pydatetime(), end_utc))

    async with UpbitClient() as client:
        for seg_start, seg_end in missing:
            if cancelled and cancelled():
                break
            raw = await client.get_candles_range(
                market,
                timeframe,
                seg_start,
                seg_end,
                progress=(lambda n: progress("fetching_data", n)) if progress else None,
                cancelled=cancelled,
            )
            df = normalize_candles(raw)
            if not df.empty:
                store.save(market, timeframe, df)

    out = store.load(market, timeframe, start_utc, end_utc)
    return drop_incomplete_last_candle(out, timeframe)


def apply_candle_policy(df: pd.DataFrame, timeframe: str, policy: str) -> pd.DataFrame:
    """policy: 'raw' keeps Upbit candles as-is; 'continuous' fills gaps with
    synthetic flat candles (is_synthetic=True)."""
    if policy == "continuous":
        return fill_synthetic(df, timeframe)
    return df.reset_index(drop=True)


async def fetch_markets() -> list[dict[str, Any]]:
    async with UpbitClient() as client:
        markets = await client.get_markets(is_details=True)
    out = []
    for m in markets:
        event = m.get("market_event") or {}
        caution = event.get("caution")
        out.append(
            {
                "market": m["market"],
                "korean_name": m.get("korean_name", ""),
                "english_name": m.get("english_name", ""),
                "is_warning": bool(event.get("warning", False)),
                "is_caution": bool(any(caution.values()) if isinstance(caution, dict) else caution),
            }
        )
    return out
