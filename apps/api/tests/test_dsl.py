"""DSL evaluation + multi-timeframe no-lookahead tests."""

from app.strategies.dsl import FeatureEngine, align_htf_to_base, eval_condition, eval_group, resample_htf
from tests.helpers import make_candles


def test_crosses_above_fires_only_on_cross_bar():
    df = make_candles([100, 100, 100, 105, 106, 107])
    fe = FeatureEngine(df)
    cond = {
        "left": {"kind": "indicator", "name": "close"},
        "op": "crosses_above",
        "right": {"kind": "const", "value": 102},
    }
    out = eval_condition(fe, cond)
    assert out.tolist() == [False, False, False, True, False, False]


def test_between_and_group_logic():
    df = make_candles([10, 20, 30, 40])
    fe = FeatureEngine(df)
    between = {
        "left": {"kind": "indicator", "name": "close"},
        "op": "between",
        "right": {"kind": "const", "value": [15, 35]},
    }
    gt = {
        "left": {"kind": "indicator", "name": "close"},
        "op": ">",
        "right": {"kind": "const", "value": 25},
    }
    and_group = {"operator": "AND", "conditions": [between, gt]}
    or_group = {"operator": "OR", "conditions": [between, gt]}
    assert eval_group(fe, and_group).tolist() == [False, False, True, False]
    assert eval_group(fe, or_group).tolist() == [False, True, True, True]


def test_resample_drops_incomplete_htf_candle():
    # 10 five-minute bars = 50 minutes -> only three complete 15m candles
    df = make_candles(list(range(100, 110)), timeframe_minutes=5)
    htf = resample_htf(df, "15m")
    assert len(htf) == 3
    assert htf["close"].iloc[0] == 102  # bars 0,1,2


def test_htf_alignment_no_lookahead():
    # 5m base, 15m HTF: base bar at 00:15 may only see the HTF candle
    # covering 00:00-00:15 (closed at 00:15), never the one containing itself.
    df = make_candles(list(range(100, 112)), timeframe_minutes=5)
    htf = resample_htf(df, "15m")
    aligned = align_htf_to_base(df["ts"], htf, htf["close"], "15m")
    # bars 0..2 (00:00-00:10): no completed HTF candle yet -> NaN
    assert aligned.iloc[:3].isna().all()
    # bars 3..5 (00:15-00:25): see HTF candle closed at 00:15 (close=102)
    assert (aligned.iloc[3:6] == 102).all()
    # bars 6..8: see candle closed at 00:30 (close=105)
    assert (aligned.iloc[6:9] == 105).all()


def test_htf_operand_in_condition():
    df = make_candles(list(range(100, 130)), timeframe_minutes=5)
    fe = FeatureEngine(df)
    cond = {
        "left": {"kind": "indicator", "name": "close"},
        "op": ">",
        "right": {"kind": "indicator", "name": "close", "timeframe": "15m"},
    }
    out = eval_condition(fe, cond)
    # early bars where HTF value is NaN must be False, not True
    assert not out.iloc[0]
    assert out.iloc[10]  # rising series: base close > last completed HTF close


def test_rising_for():
    df = make_candles([1, 2, 3, 4, 3, 4])
    fe = FeatureEngine(df)
    cond = {
        "left": {"kind": "indicator", "name": "close"},
        "op": "rising_for",
        "right": {"kind": "const", "value": 3},
        "params": {"bars": 3},
    }
    out = eval_condition(fe, cond)
    assert out.tolist() == [False, False, False, True, False, False]


def test_touched_within():
    df = make_candles([100, 100, 95, 100, 100, 100, 100],
                      lows=[100, 100, 94, 100, 100, 100, 100])
    fe = FeatureEngine(df)
    cond = {
        "left": {"kind": "indicator", "name": "low"},
        "op": "touched_within",
        "right": {"kind": "const", "value": 95},
        "params": {"bars": 3, "tolerance_percent": 0.0},
    }
    out = eval_condition(fe, cond)
    # touch happens at index 2 (low=94 <= 95); remembered for 3 bars (idx 2..4)
    assert out.tolist() == [False, False, True, True, True, False, False]
