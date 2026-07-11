"""Backtest engine execution-rule tests (spec §9, §20)."""
import pytest

from app.backtest.engine import BacktestEngine, CostConfig, EngineConfig, SizingConfig, buy_and_hold
from tests.helpers import make_candles

NO_COST = CostConfig(buy_fee_rate=0, sell_fee_rate=0, buy_slippage_rate=0,
                     sell_slippage_rate=0, min_order_krw=1000, initial_capital=1_000_000)


def entry_close_above(threshold: float) -> dict:
    return {"operator": "AND", "conditions": [{
        "left": {"kind": "indicator", "name": "close"},
        "op": ">", "right": {"kind": "const", "value": threshold},
    }]}


def exit_close_below(threshold: float) -> dict:
    return {"operator": "OR", "conditions": [{
        "left": {"kind": "indicator", "name": "close"},
        "op": "<", "right": {"kind": "const", "value": threshold},
    }]}


def strategy(entry_th=105.0, exit_th=0.0, risk=None) -> dict:
    return {"entry": entry_close_above(entry_th), "exit": exit_close_below(exit_th),
            "risk": risk or {}}


def test_entry_fills_next_open_not_signal_close():
    # signal on bar 2 (close 106 > 105); entry must be bar 3's open (110)
    df = make_candles([100, 100, 106, 111, 112, 113],
                      opens=[100, 100, 100, 110, 111, 112])
    res = BacktestEngine(df, strategy(), NO_COST, SizingConfig("all_in")).run()
    trades = res["trades"]
    assert len(trades) >= 1
    assert trades[0]["entry_index"] == 3
    assert trades[0]["entry_price"] == pytest.approx(110.0)


def test_no_duplicate_entry_on_consecutive_signals():
    # signal true on every bar after threshold; must open only one position
    df = make_candles([100, 106, 107, 108, 109, 110, 111])
    res = BacktestEngine(df, strategy(), NO_COST, SizingConfig("all_in")).run()
    assert len(res["trades"]) == 1


def test_fees_charged_on_both_sides():
    costs = CostConfig(buy_fee_rate=0.001, sell_fee_rate=0.001, buy_slippage_rate=0,
                       sell_slippage_rate=0, min_order_krw=1000, initial_capital=1_000_000)
    df = make_candles([100, 106, 106, 106, 106, 106], opens=[100, 100, 106, 106, 106, 106])
    res = BacktestEngine(df, strategy(105.0), costs, SizingConfig("all_in")).run()
    t = res["trades"][0]
    assert t["entry_fee"] == pytest.approx(1_000_000 * 0.001)
    assert t["exit_fee"] > 0
    # flat price: pnl should be exactly the total fee drag
    assert t["pnl_krw"] < 0


def test_slippage_direction():
    costs = CostConfig(buy_fee_rate=0, sell_fee_rate=0, buy_slippage_rate=0.01,
                       sell_slippage_rate=0.01, min_order_krw=1000, initial_capital=1_000_000)
    df = make_candles([100, 106, 106, 106, 106, 106], opens=[100, 100, 106, 106, 106, 106])
    res = BacktestEngine(df, strategy(105.0), costs, SizingConfig("all_in"),
                         EngineConfig(force_exit_at_end=True)).run()
    t = res["trades"][0]
    assert t["entry_price"] == pytest.approx(106 * 1.01)   # buy fills higher
    assert t["exit_price"] == pytest.approx(106 * 0.99)    # sell fills lower


def test_never_buys_more_than_cash():
    df = make_candles([100, 106, 107, 108, 109, 110])
    sizing = SizingConfig("fixed_krw", 5_000_000)  # more than capital
    res = BacktestEngine(df, strategy(), NO_COST, sizing).run()
    t = res["trades"][0]
    assert t["invested_krw"] <= NO_COST.initial_capital


def test_min_order_skip():
    sizing = SizingConfig("fixed_krw", 500)  # below min_order_krw=1000
    df = make_candles([100, 106, 107, 108, 109, 110])
    res = BacktestEngine(df, strategy(), NO_COST, sizing).run()
    assert len(res["trades"]) == 0
    assert res["skipped_min_order"] >= 1


def test_conservative_stop_first_when_both_hit():
    # entry at bar1 open=100; percent stop 5% (95), tp 5% (105);
    # bar2 spans 90..110 touching both -> conservative = stop
    risk = {"stopLossType": "percent", "stopLossValue": 5.0,
            "takeProfitType": "percent", "takeProfitValue": 5.0}
    df = make_candles(
        [200, 100, 100, 100],   # close 200 > threshold on bar0 -> entry bar1
        opens=[200, 100, 100, 100],
        highs=[200, 100, 110, 100],
        lows=[200, 100, 90, 100],
    )
    st = strategy(entry_th=150.0, risk=risk)
    res = BacktestEngine(df, st, NO_COST, SizingConfig("all_in"),
                         EngineConfig(ambiguity_mode="conservative")).run()
    t = res["trades"][0]
    assert t["exit_reason"] == "stop_loss"
    assert t["exit_price"] == pytest.approx(95.0)

    res_opt = BacktestEngine(df, st, NO_COST, SizingConfig("all_in"),
                             EngineConfig(ambiguity_mode="optimistic")).run()
    assert res_opt["trades"][0]["exit_reason"] == "take_profit"
    assert res_opt["trades"][0]["exit_price"] == pytest.approx(105.0)

    res_inv = BacktestEngine(df, st, NO_COST, SizingConfig("all_in"),
                             EngineConfig(ambiguity_mode="invalidate")).run()
    assert res_inv["trades"][0]["ambiguous"] is True


def test_gap_through_stop_fills_at_open():
    risk = {"stopLossType": "percent", "stopLossValue": 5.0}
    df = make_candles(
        [200, 100, 80, 80],
        opens=[200, 100, 85, 80],  # gaps down through the 95 stop
        highs=[200, 100, 86, 80],
        lows=[200, 100, 79, 80],
    )
    res = BacktestEngine(df, strategy(entry_th=150.0, risk=risk), NO_COST,
                         SizingConfig("all_in")).run()
    t = res["trades"][0]
    assert t["exit_reason"] == "stop_loss"
    assert t["exit_price"] == pytest.approx(85.0)  # open, not the stop level


def test_forced_exit_at_last_candle():
    df = make_candles([100, 106, 107, 108])
    res = BacktestEngine(df, strategy(), NO_COST, SizingConfig("all_in"),
                         EngineConfig(force_exit_at_end=True)).run()
    t = res["trades"][0]
    assert t["forced_exit"] is True
    assert t["exit_reason"] == "end_of_data"
    assert t["exit_price"] == pytest.approx(108.0)

    res2 = BacktestEngine(df, strategy(), NO_COST, SizingConfig("all_in"),
                          EngineConfig(force_exit_at_end=False)).run()
    assert res2["trades"][0]["exit_price"] is None


def test_entry_skips_synthetic_candle():
    df = make_candles([100, 106, 107, 108, 109, 110])
    df.loc[2, "is_synthetic"] = True  # bar after the signal is synthetic
    res = BacktestEngine(df, strategy(), NO_COST, SizingConfig("all_in")).run()
    t = res["trades"][0]
    assert t["entry_index"] == 3  # deferred to the next real candle


def test_exit_signal_fills_next_open():
    df = make_candles([100, 106, 107, 90, 95, 96],
                      opens=[100, 100, 106, 107, 93, 95])
    st = strategy(entry_th=105.0, exit_th=92.0)
    res = BacktestEngine(df, st, NO_COST, SizingConfig("all_in")).run()
    t = res["trades"][0]
    # exit signal on bar3 (close 90 < 92) -> fill at bar4 open 93
    assert t["exit_index"] == 4
    assert t["exit_price"] == pytest.approx(93.0)
    assert t["exit_reason"] == "signal"


def test_max_hold_bars():
    risk = {"maxHoldBars": 2}
    df = make_candles([100, 106, 107, 108, 109, 110, 111])
    res = BacktestEngine(df, strategy(risk=risk), NO_COST, SizingConfig("all_in")).run()
    t = res["trades"][0]
    assert t["exit_reason"] == "max_hold"
    assert t["exit_index"] - t["entry_index"] == 3  # signal at hold=2, fill next bar


def test_buy_and_hold_benchmark():
    df = make_candles([100, 110, 120, 130], opens=[100, 100, 110, 120])
    bh = buy_and_hold(df, NO_COST)
    assert bh["return_pct"] == pytest.approx(30.0)


def test_trailing_stop_atr():
    risk = {"trailingStopType": "percent", "trailingStopValue": 5.0}
    df = make_candles(
        [200, 100, 120, 110, 110],
        opens=[200, 100, 110, 120, 113],
        highs=[200, 100, 121, 120, 114],
        lows=[200, 100, 109, 113.9, 112],
    )
    res = BacktestEngine(df, strategy(entry_th=150.0, risk=risk), NO_COST,
                         SizingConfig("all_in")).run()
    t = res["trades"][0]
    # bar2 high 121 ratchets trail to 114.95 (checked from bar3 onward);
    # bar3 low 113.9 <= 114.95 -> stop fills at min(open=120, 114.95)
    assert t["exit_reason"] == "stop_loss"
    assert t["exit_index"] == 3
    assert t["exit_price"] == pytest.approx(114.95)
