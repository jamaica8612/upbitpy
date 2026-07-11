"""Seed the candle cache with GENERATED demo data (offline development only).

⚠️ This is NOT real Upbit market data. It exists so the app can be exercised
in environments without network access to api.upbit.com. In normal use the
app downloads real candles automatically and this script is unnecessary.

Usage: python scripts/seed_demo_data.py [days] [market] [timeframe]
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))

from app.data.store import CandleStore, timeframe_delta  # noqa: E402


def generate(days: int, market: str, timeframe: str, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    step = timeframe_delta(timeframe)
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % max(int(step.total_seconds() // 60), 1))
    n = int(timedelta(days=days) / step)
    ts = pd.date_range(end=end - step, periods=n, freq=step, tz="UTC")

    # geometric random walk with volatility clustering + intraday volume cycle
    base = 100_000_000.0 if market.endswith("BTC") else 3_000_000.0
    vol = 0.0015 + 0.001 * np.abs(np.sin(np.linspace(0, 20, n)))
    rets = rng.normal(0.00002, vol)
    closes = base * np.exp(np.cumsum(rets))
    opens = np.concatenate([[base], closes[:-1]])
    spreads = np.abs(rng.normal(0, vol)) * closes
    highs = np.maximum(opens, closes) + spreads
    lows = np.minimum(opens, closes) - spreads
    volumes = np.abs(rng.lognormal(0, 0.8, n)) * (1 + 0.5 * np.sin(np.linspace(0, 200, n)))

    return pd.DataFrame({
        "ts": ts,
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": volumes, "value": volumes * closes,
        "is_synthetic": False,
    })


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    market = sys.argv[2] if len(sys.argv) > 2 else "KRW-BTC"
    timeframe = sys.argv[3] if len(sys.argv) > 3 else "5m"
    df = generate(days, market, timeframe)
    store = CandleStore()
    store.save(market, timeframe, df)
    print(f"seeded {len(df)} DEMO candles for {market} {timeframe} "
          f"({df['ts'].iloc[0]} ~ {df['ts'].iloc[-1]})")
    print("⚠️  generated data, not real Upbit prices — for offline development only")
