"""Data layer tests: normalization, gaps, synthetic fill, cache, rate limiter."""
from datetime import datetime, timezone

import pandas as pd

from app.config import Settings
from app.data.store import (
    CandleStore,
    detect_gaps,
    drop_incomplete_last_candle,
    fill_synthetic,
    normalize_candles,
)
from app.upbit.rate_limiter import parse_remaining_req
from tests.helpers import make_candles, make_upbit_raw


def test_normalize_dedup_and_ascending():
    raw = make_upbit_raw(["2026-01-01T00:10:00", "2026-01-01T00:00:00",
                          "2026-01-01T00:05:00", "2026-01-01T00:05:00"])
    df = normalize_candles(raw)
    assert len(df) == 3
    assert df["ts"].is_monotonic_increasing
    assert str(df["ts"].dt.tz) == "UTC"


def test_drop_incomplete_last_candle():
    now = datetime(2026, 1, 1, 0, 12, tzinfo=timezone.utc)
    raw = make_upbit_raw(["2026-01-01T00:00:00", "2026-01-01T00:05:00", "2026-01-01T00:10:00"])
    df = normalize_candles(raw)
    out = drop_incomplete_last_candle(df, "5m", now_utc=now)
    # the 00:10 candle closes at 00:15 (> now) so it must be dropped
    assert len(out) == 2
    assert out["ts"].iloc[-1] == pd.Timestamp("2026-01-01T00:05:00Z")


def test_detect_gaps():
    raw = make_upbit_raw(["2026-01-01T00:00:00", "2026-01-01T00:05:00", "2026-01-01T00:25:00"])
    df = normalize_candles(raw)
    gaps = detect_gaps(df, "5m")
    assert len(gaps) == 1
    assert gaps[0]["missing"] == 3


def test_fill_synthetic():
    raw = make_upbit_raw(["2026-01-01T00:00:00", "2026-01-01T00:15:00"], price=100.0)
    df = normalize_candles(raw)
    out = fill_synthetic(df, "5m")
    assert len(out) == 4  # 00:00, 00:05, 00:10, 00:15
    synth = out[out["is_synthetic"]]
    assert len(synth) == 2
    assert (synth["open"] == 100.0).all()
    assert (synth["close"] == 100.0).all()
    assert (synth["volume"] == 0.0).all()


def test_store_roundtrip_and_merge(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    store = CandleStore(cfg)
    df1 = make_candles([100.0, 101.0, 102.0], start="2026-01-01T00:00:00Z")
    store.save("KRW-BTC", "5m", df1)
    # overlapping save must dedupe on ts
    df2 = make_candles([102.0, 103.0], start="2026-01-01T00:10:00Z")
    store.save("KRW-BTC", "5m", df2)
    out = store.load("KRW-BTC", "5m")
    assert len(out) == 4
    assert out["ts"].is_monotonic_increasing
    status = store.status()
    assert status[0]["candle_count"] == 4
    store.delete("KRW-BTC", "5m")
    assert store.load("KRW-BTC", "5m").empty


def test_store_range_query(tmp_path):
    cfg = Settings(data_dir=tmp_path)
    store = CandleStore(cfg)
    store.save("KRW-BTC", "5m", make_candles([100.0] * 10, start="2026-01-01T00:00:00Z"))
    out = store.load(
        "KRW-BTC", "5m",
        start_utc=datetime(2026, 1, 1, 0, 10, tzinfo=timezone.utc),
        end_utc=datetime(2026, 1, 1, 0, 25, tzinfo=timezone.utc),
    )
    assert len(out) == 4


def test_parse_remaining_req_header():
    assert parse_remaining_req("group=candles; min=599; sec=9") == 9
    assert parse_remaining_req(None) is None
    assert parse_remaining_req("garbage") is None
