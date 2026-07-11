"""Candle normalization + Parquet cache store.

Layout: <data_dir>/candles/market=KRW-BTC/timeframe=5m/year=2026/month=07.parquet
Unique key: (market, timeframe, ts). Timestamps are stored in UTC.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from app.config import Settings, settings as default_settings
from app.upbit.client import TIMEFRAMES

COLUMNS = ["ts", "open", "high", "low", "close", "volume", "value", "is_synthetic"]


def timeframe_delta(timeframe: str) -> timedelta:
    unit = TIMEFRAMES[timeframe]
    return timedelta(days=1) if unit is None else timedelta(minutes=unit)


def normalize_candles(raw: list[dict[str, Any]]) -> pd.DataFrame:
    """Upbit raw candles (any order) -> ascending, deduped, UTC dataframe."""
    if not raw:
        return pd.DataFrame(columns=COLUMNS).astype({"is_synthetic": bool})
    df = pd.DataFrame(
        {
            "ts": pd.to_datetime([c["candle_date_time_utc"] for c in raw], utc=True),
            "open": [float(c["opening_price"]) for c in raw],
            "high": [float(c["high_price"]) for c in raw],
            "low": [float(c["low_price"]) for c in raw],
            "close": [float(c["trade_price"]) for c in raw],
            "volume": [float(c["candle_acc_trade_volume"]) for c in raw],
            "value": [float(c["candle_acc_trade_price"]) for c in raw],
        }
    )
    df["is_synthetic"] = False
    df = df.drop_duplicates(subset="ts", keep="last").sort_values("ts").reset_index(drop=True)
    return df


def drop_incomplete_last_candle(df: pd.DataFrame, timeframe: str, now_utc: datetime | None = None) -> pd.DataFrame:
    """Remove candles whose period has not fully closed yet."""
    if df.empty:
        return df
    now = now_utc or datetime.now(timezone.utc)
    cutoff = pd.Timestamp(now) - timeframe_delta(timeframe)
    return df[df["ts"] <= cutoff].reset_index(drop=True)


def detect_gaps(df: pd.DataFrame, timeframe: str) -> list[dict[str, Any]]:
    """List of gaps where consecutive candles are further apart than expected.

    On Upbit a missing candle simply means no trades happened, so gaps are
    informational, not necessarily data errors.
    """
    if len(df) < 2:
        return []
    step = timeframe_delta(timeframe)
    ts = df["ts"].reset_index(drop=True)
    diffs = ts.diff()
    gaps = []
    for i in range(1, len(ts)):
        if diffs[i] > step:
            missing = int(diffs[i] / step) - 1
            gaps.append({"after": ts[i - 1].isoformat(), "before": ts[i].isoformat(), "missing": missing})
    return gaps


def fill_synthetic(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Continuous-candle mode: fill missing periods with flat zero-volume
    candles at the previous close, flagged is_synthetic=True."""
    if df.empty:
        return df
    step = timeframe_delta(timeframe)
    full_index = pd.date_range(df["ts"].iloc[0], df["ts"].iloc[-1], freq=step)
    out = df.set_index("ts").reindex(full_index)
    synthetic = out["open"].isna()
    prev_close = out["close"].ffill().shift(1)
    for col in ("open", "high", "low", "close"):
        out[col] = out[col].where(~synthetic, prev_close)
    out["volume"] = out["volume"].fillna(0.0)
    out["value"] = out["value"].fillna(0.0)
    out["is_synthetic"] = synthetic.fillna(False)
    out = out.dropna(subset=["close"])  # leading rows with no prior close
    return out.rename_axis("ts").reset_index()


class CandleStore:
    def __init__(self, cfg: Settings | None = None) -> None:
        self.cfg = cfg or default_settings
        self.root = self.cfg.candle_dir
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, market: str, timeframe: str) -> Path:
        return self.root / f"market={market}" / f"timeframe={timeframe}"

    def _partition_path(self, market: str, timeframe: str, year: int, month: int) -> Path:
        return self._dir(market, timeframe) / f"year={year}" / f"month={month:02d}.parquet"

    def save(self, market: str, timeframe: str, df: pd.DataFrame) -> int:
        """Merge candles into the cache (dedupe on ts). Returns rows written."""
        if df.empty:
            return 0
        df = df[COLUMNS].copy()
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        written = 0
        for (year, month), part in df.groupby([df["ts"].dt.year, df["ts"].dt.month]):
            path = self._partition_path(market, timeframe, int(year), int(month))
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                existing = pd.read_parquet(path)
                existing["ts"] = pd.to_datetime(existing["ts"], utc=True)
                part = (
                    pd.concat([existing, part])
                    .drop_duplicates(subset="ts", keep="last")
                    .sort_values("ts")
                )
            part.reset_index(drop=True).to_parquet(path, index=False)
            written += len(part)
        return written

    def load(
        self,
        market: str,
        timeframe: str,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
    ) -> pd.DataFrame:
        base = self._dir(market, timeframe)
        if not base.exists():
            return pd.DataFrame(columns=COLUMNS)
        glob = str(base / "year=*" / "month=*.parquet")
        con = duckdb.connect()
        try:
            query = f"SELECT ts, open, high, low, close, volume, value, is_synthetic FROM read_parquet('{glob}')"
            clauses = []
            if start_utc is not None:
                clauses.append(f"ts >= TIMESTAMP '{start_utc.astimezone(timezone.utc):%Y-%m-%d %H:%M:%S}'")
            if end_utc is not None:
                clauses.append(f"ts <= TIMESTAMP '{end_utc.astimezone(timezone.utc):%Y-%m-%d %H:%M:%S}'")
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY ts"
            df = con.execute(query).df()
        finally:
            con.close()
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        return df.drop_duplicates(subset="ts", keep="last").reset_index(drop=True)

    def delete(self, market: str, timeframe: str | None = None) -> None:
        target = self._dir(market, timeframe) if timeframe else self.root / f"market={market}"
        if target.exists():
            shutil.rmtree(target)

    def status(self) -> list[dict[str, Any]]:
        """Cache inventory for the data-management screen."""
        out = []
        for market_dir in sorted(self.root.glob("market=*")):
            market = market_dir.name.split("=", 1)[1]
            for tf_dir in sorted(market_dir.glob("timeframe=*")):
                timeframe = tf_dir.name.split("=", 1)[1]
                df = self.load(market, timeframe)
                if df.empty:
                    continue
                files = list(tf_dir.rglob("*.parquet"))
                gaps = detect_gaps(df, timeframe)
                out.append(
                    {
                        "market": market,
                        "timeframe": timeframe,
                        "first_ts": df["ts"].iloc[0].isoformat(),
                        "last_ts": df["ts"].iloc[-1].isoformat(),
                        "candle_count": int(len(df)),
                        "gap_count": len(gaps),
                        "size_bytes": sum(f.stat().st_size for f in files),
                        "last_updated": max(f.stat().st_mtime for f in files),
                    }
                )
        return out
