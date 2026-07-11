"""Test helpers: build small deterministic candle frames."""
from __future__ import annotations

import pandas as pd


def make_candles(
    closes: list[float],
    start: str = "2026-01-01T00:00:00Z",
    timeframe_minutes: int = 5,
    opens: list[float] | None = None,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
) -> pd.DataFrame:
    n = len(closes)
    ts = pd.date_range(start=start, periods=n, freq=f"{timeframe_minutes}min", tz="UTC")
    opens = opens or [closes[max(i - 1, 0)] for i in range(n)]
    highs = highs or [max(o, c) * 1.001 for o, c in zip(opens, closes)]
    lows = lows or [min(o, c) * 0.999 for o, c in zip(opens, closes)]
    volumes = volumes or [100.0] * n
    return pd.DataFrame(
        {
            "ts": ts,
            "open": [float(v) for v in opens],
            "high": [float(v) for v in highs],
            "low": [float(v) for v in lows],
            "close": [float(v) for v in closes],
            "volume": [float(v) for v in volumes],
            "value": [float(c * v) for c, v in zip(closes, volumes)],
            "is_synthetic": [False] * n,
        }
    )


def make_upbit_raw(ts_list: list[str], price: float = 100.0) -> list[dict]:
    """Raw Upbit-format candle dicts (newest-first like the real API)."""
    return [
        {
            "market": "KRW-TEST",
            "candle_date_time_utc": t,
            "opening_price": price,
            "high_price": price * 1.01,
            "low_price": price * 0.99,
            "trade_price": price,
            "candle_acc_trade_volume": 10.0,
            "candle_acc_trade_price": price * 10.0,
        }
        for t in ts_list
    ]
