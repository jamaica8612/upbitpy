"""Strategy DSL: JSON conditions -> boolean pandas Series.

Operand:  {"kind": "indicator"|"const", "name": "...", "params": {...},
           "field": "...", "timeframe": "60m"|null, "multiply": 1.5, "value": 30}
Condition:{"left": op, "op": "crosses_above", "right": op, "params": {...}}
Group:    {"operator": "AND"|"OR", "conditions": [Condition|Group, ...]}

Higher-timeframe operands are computed on completed HTF candles only and
forward-filled onto base bars strictly after the HTF candle closes (no
future leakage; see resample_htf/align_htf_to_base).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from app.data.store import timeframe_delta
from app.indicators import core as ind

PRICE_FIELDS = {"open", "high", "low", "close", "volume", "value"}


def resample_htf(df: pd.DataFrame, htf: str) -> pd.DataFrame:
    """Aggregate base candles into higher-timeframe candles.

    The last HTF bucket is dropped unless the base data fully covers it
    (i.e., the bucket has closed), so incomplete HTF candles never exist.
    """
    step = timeframe_delta(htf)
    bucket = df["ts"].dt.floor(step if step < pd.Timedelta(days=1) else "1D")
    agg = df.groupby(bucket).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        value=("value", "sum"),
    )
    agg.index.name = "ts"
    agg = agg.reset_index()
    if agg.empty:
        return agg
    # Base timeframe delta = smallest observed spacing (robust to gaps).
    base_step = df["ts"].diff().min() if len(df) > 1 else step
    last_base_end = df["ts"].iloc[-1] + base_step
    if agg["ts"].iloc[-1] + step > last_base_end:
        agg = agg.iloc[:-1]
    agg["is_synthetic"] = False
    return agg.reset_index(drop=True)


def align_htf_to_base(base_ts: pd.Series, htf_df: pd.DataFrame, htf_series: pd.Series, htf: str) -> pd.Series:
    """Map an HTF indicator onto base bars without lookahead.

    A base bar at time t may only see HTF values whose candle *closed* at or
    before t (close time = htf ts + htf delta).
    """
    step = timeframe_delta(htf)
    avail = pd.DataFrame({"available_at": htf_df["ts"] + step, "v": htf_series.values}).dropna(
        subset=["available_at"]
    )
    merged = pd.merge_asof(
        pd.DataFrame({"ts": base_ts}).sort_values("ts"),
        avail.sort_values("available_at"),
        left_on="ts",
        right_on="available_at",
        direction="backward",
    )
    out = pd.Series(merged["v"].values, index=base_ts.index)
    return out


class FeatureEngine:
    """Computes and caches indicator series for a candle frame."""

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self._cache: dict[str, pd.Series] = {}
        self._htf_frames: dict[str, pd.DataFrame] = {}

    def _frame_for(self, timeframe: str | None) -> pd.DataFrame:
        if not timeframe:
            return self.df
        if timeframe not in self._htf_frames:
            self._htf_frames[timeframe] = resample_htf(self.df, timeframe)
        return self._htf_frames[timeframe]

    def series(self, operand: dict[str, Any]) -> pd.Series:
        kind = operand.get("kind", "indicator")
        if kind == "const":
            value = operand.get("value", 0.0)
            if isinstance(value, list):
                raise ValueError("list const only valid for between/outside")
            return pd.Series(float(value), index=self.df.index)

        key = repr(sorted(operand.items(), key=lambda kv: kv[0]))
        if key not in self._cache:
            timeframe = operand.get("timeframe")
            frame = self._frame_for(timeframe)
            raw = self._compute(frame, operand)
            if timeframe:
                raw = align_htf_to_base(self.df["ts"], frame, raw, timeframe)
            if operand.get("offset"):
                raw = raw.shift(int(operand["offset"]))
            if operand.get("multiply") is not None:
                raw = raw * float(operand["multiply"])
            self._cache[key] = raw
        return self._cache[key]

    def _compute(self, df: pd.DataFrame, operand: dict[str, Any]) -> pd.Series:
        name = operand["name"]
        p = operand.get("params", {}) or {}
        field = operand.get("field")
        src = df[p.get("source", "close")] if p.get("source") in PRICE_FIELDS else df["close"]

        if name in PRICE_FIELDS:
            return df[name]
        if name == "change_pct":
            return df["close"].pct_change(int(p.get("period", 1))) * 100.0
        if name == "gap_pct":
            return (df["open"] / df["close"].shift(1) - 1.0) * 100.0
        if name == "sma":
            return ind.sma(src, int(p.get("period", 20)))
        if name == "ema":
            return ind.ema(src, int(p.get("period", 20)))
        if name == "wma":
            return ind.wma(src, int(p.get("period", 20)))
        if name == "ema_slope":
            return ind.slope(ind.ema(src, int(p.get("period", 20))), int(p.get("slope_period", 1)))
        if name == "disparity":
            return ind.disparity(df["close"], ind.ema(src, int(p.get("period", 20))))
        if name == "rsi":
            return ind.rsi(df["close"], int(p.get("period", 14)))
        if name == "macd":
            out = ind.macd(df["close"], int(p.get("fast", 12)), int(p.get("slow", 26)), int(p.get("signal", 9)))
            return out[field or "macd"]
        if name == "stochastic":
            out = ind.stochastic(df["high"], df["low"], df["close"], int(p.get("k", 14)), int(p.get("d", 3)), int(p.get("smooth", 3)))
            return out[field or "k"]
        if name == "roc":
            return ind.roc(df["close"], int(p.get("period", 12)))
        if name == "adx":
            return ind.adx(df["high"], df["low"], df["close"], int(p.get("period", 14)))
        if name == "atr":
            return ind.atr(df["high"], df["low"], df["close"], int(p.get("period", 14)))
        if name == "bollinger":
            out = ind.bollinger(df["close"], int(p.get("period", 20)), float(p.get("mult", 2.0)))
            return out[field or "mid"]
        if name == "donchian":
            out = ind.donchian(df["high"], df["low"], int(p.get("period", 20)))
            return out[field or "upper"]
        if name == "highest":
            return ind.highest(df[p.get("source", "high")].shift(1), int(p.get("period", 20)))
        if name == "lowest":
            return ind.lowest(df[p.get("source", "low")].shift(1), int(p.get("period", 20)))
        if name == "obv":
            return ind.obv(df["close"], df["volume"])
        if name == "mfi":
            return ind.mfi(df["high"], df["low"], df["close"], df["volume"], int(p.get("period", 14)))
        if name == "volume_sma":
            return ind.sma(df["volume"], int(p.get("period", 20)))
        if name == "relative_volume":
            return ind.relative_volume(df["volume"], int(p.get("period", 20)))
        if name == "supertrend":
            out = ind.supertrend(df["high"], df["low"], df["close"], int(p.get("period", 10)), float(p.get("mult", 3.0)))
            return out[field or "supertrend"]
        if name == "vwap":
            anchor = p.get("anchor", "utc_day")
            anchor_ts = pd.Timestamp(p["anchor_ts"]).tz_localize("UTC") if p.get("anchor_ts") and pd.Timestamp(p["anchor_ts"]).tzinfo is None else (pd.Timestamp(p["anchor_ts"]) if p.get("anchor_ts") else None)
            return ind.vwap(df, anchor=anchor, anchor_ts=anchor_ts)
        raise ValueError(f"unknown indicator: {name}")


def _const_pair(operand: dict[str, Any]) -> tuple[float, float]:
    value = operand.get("value")
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("between/outside requires const value [low, high]")
    return float(value[0]), float(value[1])


def eval_condition(fe: FeatureEngine, cond: dict[str, Any]) -> pd.Series:
    op = cond["op"]
    left = fe.series(cond["left"])
    params = cond.get("params", {}) or {}

    if op in ("between", "outside"):
        low, high = _const_pair(cond["right"])
        inside = (left >= low) & (left <= high)
        result = inside if op == "between" else ~inside
        return result & left.notna()

    if op in ("rising_for", "falling_for"):
        n = int(params.get("bars", cond.get("right", {}).get("value", 3)))
        diff = left.diff()
        base = diff > 0 if op == "rising_for" else diff < 0
        return base.rolling(n, min_periods=n).sum().eq(n) & left.notna()

    right = fe.series(cond["right"])

    if op in (">", "percent_above"):
        pct = float(params.get("percent", 0.0)) if op == "percent_above" else 0.0
        return (left > right * (1 + pct / 100.0)) & left.notna() & right.notna()
    if op in ("<", "percent_below"):
        pct = float(params.get("percent", 0.0)) if op == "percent_below" else 0.0
        return (left < right * (1 - pct / 100.0)) & left.notna() & right.notna()
    if op == ">=":
        return (left >= right) & left.notna() & right.notna()
    if op == "<=":
        return (left <= right) & left.notna() & right.notna()
    if op == "==":
        return (left == right) & left.notna() & right.notna()
    if op == "crosses_above":
        prev = (left.shift(1) <= right.shift(1))
        return (left > right) & prev & left.notna() & right.notna()
    if op == "crosses_below":
        prev = (left.shift(1) >= right.shift(1))
        return (left < right) & prev & left.notna() & right.notna()
    if op == "distance_percent":
        max_pct = float(params.get("max_percent", 0.5))
        dist = (left / right - 1.0).abs() * 100.0
        return (dist <= max_pct) & left.notna() & right.notna()
    if op == "touched_within":
        # Within the last N bars, `left` came within tolerance% of (or below)
        # `right` — used for pullback detection.
        n = int(params.get("bars", 3))
        tol = float(params.get("tolerance_percent", 0.0))
        touched = left <= right * (1 + tol / 100.0)
        touched = touched & left.notna() & right.notna()
        return touched.rolling(n, min_periods=1).max().astype(bool)
    if op == "highest_of":
        n = int(params.get("bars", 20))
        return (left >= ind.highest(right.shift(1), n)) & left.notna()
    if op == "lowest_of":
        n = int(params.get("bars", 20))
        return (left <= ind.lowest(right.shift(1), n)) & left.notna()
    raise ValueError(f"unknown operator: {op}")


def eval_group(fe: FeatureEngine, group: dict[str, Any]) -> pd.Series:
    conditions = group.get("conditions", [])
    if not conditions:
        return pd.Series(False, index=fe.df.index)
    parts = []
    for c in conditions:
        if "operator" in c:
            parts.append(eval_group(fe, c))
        else:
            parts.append(eval_condition(fe, c).fillna(False))
    combined = parts[0]
    for p in parts[1:]:
        combined = (combined & p) if group.get("operator", "AND") == "AND" else (combined | p)
    return combined.astype(bool)


def warmup_mask(fe: FeatureEngine, group: dict[str, Any]) -> pd.Series:
    """True where every indicator referenced by the group has a value."""
    mask = pd.Series(True, index=fe.df.index)

    def visit(node: dict[str, Any]) -> None:
        nonlocal mask
        if "operator" in node:
            for c in node.get("conditions", []):
                visit(c)
            return
        for side in ("left", "right"):
            operand = node.get(side)
            if isinstance(operand, dict) and operand.get("kind", "indicator") != "const":
                try:
                    mask &= fe.series(operand).notna()
                except (ValueError, KeyError):
                    pass

    visit(group)
    return mask
