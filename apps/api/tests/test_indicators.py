"""Indicator correctness on small fixed datasets (spec §20)."""
import numpy as np
import pandas as pd
import pytest

from app.indicators import core as ind
from tests.helpers import make_candles


def test_sma_known_values():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    out = ind.sma(s, 3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_matches_recursive_formula():
    s = pd.Series([10, 11, 12, 13, 14, 15], dtype=float)
    out = ind.ema(s, 3)
    # pandas ewm(span=3, adjust=False): alpha = 0.5, seeded from first value
    alpha = 2 / (3 + 1)
    manual = s.iloc[0]
    for v in s.iloc[1:]:
        manual = alpha * v + (1 - alpha) * manual
    assert out.iloc[-1] == pytest.approx(manual)
    # warm-up: first period-1 values are NaN
    assert np.isnan(out.iloc[0])


def test_rsi_all_gains_is_100_and_bounds():
    up = pd.Series(np.arange(1, 30, dtype=float))
    out = ind.rsi(up, 14)
    assert out.iloc[-1] == pytest.approx(100.0)
    mixed = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42,
                       45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00,
                       46.03, 46.41, 46.22, 45.64])
    out2 = ind.rsi(mixed, 14).dropna()
    assert ((out2 >= 0) & (out2 <= 100)).all()


def test_atr_constant_range():
    # constant candles with high-low = 2 -> ATR converges to 2
    n = 100
    df = make_candles([100.0] * n, highs=[101.0] * n, lows=[99.0] * n, opens=[100.0] * n)
    out = ind.atr(df["high"], df["low"], df["close"], 14)
    assert out.iloc[-1] == pytest.approx(2.0, rel=1e-3)


def test_macd_zero_for_constant_series():
    s = pd.Series([50.0] * 60)
    out = ind.macd(s)
    assert out["macd"].iloc[-1] == pytest.approx(0.0, abs=1e-9)
    assert out["histogram"].iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_bollinger_constant_series_bands_collapse():
    s = pd.Series([100.0] * 30)
    out = ind.bollinger(s, 20, 2.0)
    assert out["upper"].iloc[-1] == pytest.approx(100.0)
    assert out["lower"].iloc[-1] == pytest.approx(100.0)
    assert out["mid"].iloc[-1] == pytest.approx(100.0)


def test_bollinger_known_std():
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = ind.bollinger(s, 5, 2.0)
    # mean 3, population std sqrt(2)
    assert out["mid"].iloc[-1] == pytest.approx(3.0)
    assert out["upper"].iloc[-1] == pytest.approx(3.0 + 2 * np.sqrt(2.0))


def test_vwap_utc_day_reset():
    # two UTC days, constant price 100 then 200
    df1 = make_candles([100.0] * 288, start="2026-01-01T00:00:00Z")
    df2 = make_candles([200.0] * 288, start="2026-01-02T00:00:00Z")
    df = pd.concat([df1, df2], ignore_index=True)
    out = ind.vwap(df, anchor="utc_day")
    # each day's VWAP equals that day's typical price (flat prices)
    day2_first = out.iloc[288]
    assert day2_first == pytest.approx((df["high"].iloc[288] + df["low"].iloc[288] + 200.0) / 3, rel=1e-6)


def test_anchored_vwap_starts_at_anchor():
    df = make_candles([100.0] * 10 + [110.0] * 10)
    anchor_ts = df["ts"].iloc[10]
    out = ind.vwap(df, anchor="anchored", anchor_ts=anchor_ts)
    assert out.iloc[:10].isna().all()
    tp = (df["high"].iloc[10] + df["low"].iloc[10] + 110.0) / 3
    assert out.iloc[10] == pytest.approx(tp, rel=1e-6)


def test_donchian_excludes_current_bar():
    # rising highs: current close always exceeds the *previous* N-bar high,
    # which would be impossible if the channel included the current bar.
    closes = list(np.linspace(100, 150, 40))
    df = make_candles(closes)
    ch = ind.donchian(df["high"], df["low"], 10)
    valid = ch["upper"].dropna().index
    assert (df["close"].loc[valid] > ch["upper"].loc[valid]).all()


def test_relative_volume():
    vols = [100.0] * 20 + [300.0]
    df = make_candles([100.0] * 21, volumes=vols)
    out = ind.relative_volume(df["volume"], 20)
    # last bar: 20-bar SMA includes the 300 spike -> (19*100+300)/20 = 110
    assert out.iloc[-1] == pytest.approx(300.0 / 110.0, rel=1e-6)


def test_stochastic_range():
    closes = list(100 + 10 * np.sin(np.linspace(0, 6, 60)))
    df = make_candles(closes)
    out = ind.stochastic(df["high"], df["low"], df["close"]).dropna()
    assert ((out["k"] >= 0) & (out["k"] <= 100)).all()
