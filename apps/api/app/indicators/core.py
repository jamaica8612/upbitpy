"""Indicator library implemented directly on pandas for testability.

Every function takes/returns pandas Series aligned to the candle index and
produces NaN during its warm-up window so the engine can skip signals until
values are reliable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---- moving averages -----------------------------------------------------

def sma(s: pd.Series, period: int) -> pd.Series:
    return s.rolling(period, min_periods=period).mean()


def ema(s: pd.Series, period: int) -> pd.Series:
    out = s.ewm(span=period, adjust=False, min_periods=period).mean()
    return out


def wma(s: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1, dtype=float)
    return s.rolling(period, min_periods=period).apply(
        lambda x: float(np.dot(x, weights) / weights.sum()), raw=True
    )


def slope(s: pd.Series, period: int = 1) -> pd.Series:
    """Per-bar change over `period` bars (absolute)."""
    return s.diff(period) / period


def disparity(price: pd.Series, ma: pd.Series) -> pd.Series:
    """Percent distance of price from a moving average."""
    return (price / ma - 1.0) * 100.0


# ---- momentum --------------------------------------------------------------

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(avg_loss != 0, 100.0).where(~(avg_gain.isna() | avg_loss.isna()))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return pd.DataFrame(
        {"macd": macd_line, "signal": signal_line, "histogram": macd_line - signal_line}
    )


def stochastic(high: pd.Series, low: pd.Series, close: pd.Series, k: int = 14, d: int = 3, smooth: int = 3) -> pd.DataFrame:
    ll = low.rolling(k, min_periods=k).min()
    hh = high.rolling(k, min_periods=k).max()
    raw_k = (close - ll) / (hh - ll).replace(0.0, np.nan) * 100.0
    k_line = raw_k.rolling(smooth, min_periods=smooth).mean()
    d_line = k_line.rolling(d, min_periods=d).mean()
    return pd.DataFrame({"k": k_line, "d": d_line})


def roc(close: pd.Series, period: int = 12) -> pd.Series:
    return (close / close.shift(period) - 1.0) * 100.0


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    tr = true_range(high, low, close)
    alpha = 1 / period
    atr_s = tr.ewm(alpha=alpha, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_s
    minus_di = 100 * minus_dm.ewm(alpha=alpha, adjust=False, min_periods=period).mean() / atr_s
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


# ---- volatility ------------------------------------------------------------

def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    return pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    return true_range(high, low, close).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def bollinger(close: pd.Series, period: int = 20, mult: float = 2.0) -> pd.DataFrame:
    mid = sma(close, period)
    std = close.rolling(period, min_periods=period).std(ddof=0)
    upper = mid + mult * std
    lower = mid - mult * std
    width = (upper - lower) / mid * 100.0
    return pd.DataFrame({"mid": mid, "upper": upper, "lower": lower, "width": width})


def donchian(high: pd.Series, low: pd.Series, period: int = 20) -> pd.DataFrame:
    """Uses only *previous* N bars (shift(1)) so a candle never breaks out of
    a channel that includes itself."""
    upper = high.shift(1).rolling(period, min_periods=period).max()
    lower = low.shift(1).rolling(period, min_periods=period).min()
    return pd.DataFrame({"upper": upper, "lower": lower, "mid": (upper + lower) / 2})


def highest(s: pd.Series, period: int) -> pd.Series:
    return s.rolling(period, min_periods=period).max()


def lowest(s: pd.Series, period: int) -> pd.Series:
    return s.rolling(period, min_periods=period).min()


# ---- volume ----------------------------------------------------------------

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff().fillna(0.0))
    return (direction * volume).cumsum()


def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
    tp = (high + low + close) / 3
    flow = tp * volume
    pos = flow.where(tp > tp.shift(1), 0.0)
    neg = flow.where(tp < tp.shift(1), 0.0)
    pos_sum = pos.rolling(period, min_periods=period).sum()
    neg_sum = neg.rolling(period, min_periods=period).sum()
    ratio = pos_sum / neg_sum.replace(0.0, np.nan)
    out = 100 - 100 / (1 + ratio)
    return out.where(neg_sum != 0, 100.0).where(pos_sum.notna() & neg_sum.notna())


def relative_volume(volume: pd.Series, period: int = 20) -> pd.Series:
    base = sma(volume, period)
    return volume / base.replace(0.0, np.nan)


# ---- trend -----------------------------------------------------------------

def supertrend(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10, mult: float = 3.0) -> pd.DataFrame:
    atr_s = atr(high, low, close, period)
    hl2 = (high + low) / 2
    upper_basic = hl2 + mult * atr_s
    lower_basic = hl2 - mult * atr_s

    n = len(close)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    st = np.full(n, np.nan)
    direction = np.zeros(n)  # 1 up, -1 down

    for i in range(n):
        if np.isnan(atr_s.iloc[i]):
            continue
        ub, lb = upper_basic.iloc[i], lower_basic.iloc[i]
        prev_ub = upper[i - 1] if i > 0 and not np.isnan(upper[i - 1]) else ub
        prev_lb = lower[i - 1] if i > 0 and not np.isnan(lower[i - 1]) else lb
        upper[i] = ub if (ub < prev_ub or close.iloc[i - 1] > prev_ub) else prev_ub
        lower[i] = lb if (lb > prev_lb or close.iloc[i - 1] < prev_lb) else prev_lb
        prev_dir = direction[i - 1] if i > 0 else 1
        if prev_dir == 1:
            direction[i] = -1 if close.iloc[i] < lower[i] else 1
        else:
            direction[i] = 1 if close.iloc[i] > upper[i] else -1
        st[i] = lower[i] if direction[i] == 1 else upper[i]

    return pd.DataFrame({"supertrend": st, "direction": direction}, index=close.index)


# ---- VWAP ------------------------------------------------------------------

def vwap(df: pd.DataFrame, anchor: str = "utc_day", anchor_ts: pd.Timestamp | None = None) -> pd.Series:
    """Candle-based approximate VWAP (typical price weighted by volume).

    anchor:
      - 'utc_day': resets at 00:00 UTC (Upbit daily candle boundary, 09:00 KST)
      - 'kst_day': resets at 00:00 KST
      - 'anchored': cumulative from `anchor_ts` onward
    """
    tp = (df["high"] + df["low"] + df["close"]) / 3
    pv = tp * df["volume"]
    ts = df["ts"]

    if anchor == "anchored":
        if anchor_ts is None:
            raise ValueError("anchored VWAP requires anchor_ts")
        mask = ts >= anchor_ts
        group = mask.cumsum().where(mask)  # single group after anchor, NaN before
    elif anchor == "kst_day":
        group = ts.dt.tz_convert("Asia/Seoul").dt.date
    else:  # utc_day
        group = ts.dt.date

    cum_pv = pv.groupby(group).cumsum()
    cum_vol = df["volume"].groupby(group).cumsum()
    out = cum_pv / cum_vol.replace(0.0, np.nan)
    if anchor == "anchored":
        out = out.where(ts >= anchor_ts)
    return out
