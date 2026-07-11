"""Performance metric tests on hand-computed examples."""
import numpy as np
import pandas as pd
import pytest

from app.backtest.metrics import compute_metrics


def _trade(pnl: float, ret: float, fee: float = 10.0, hold: int = 5) -> dict:
    return {
        "exit_price": 1.0, "pnl_krw": pnl, "return_pct": ret,
        "entry_fee": fee, "exit_fee": fee, "hold_bars": hold,
        "exit_ts": "2026-01-05T00:00:00+00:00",
    }


def make_inputs(trades, equity):
    ts = pd.Series(pd.date_range("2026-01-01", periods=len(equity), freq="5min", tz="UTC"))
    return trades, np.array(equity, dtype=float), ts


def test_total_return_and_final_equity():
    trades, equity, ts = make_inputs([_trade(100_000, 10.0)], [1_000_000, 1_050_000, 1_100_000])
    m = compute_metrics(trades, equity, ts, "5m", 1_000_000, buy_hold_return_pct=5.0)
    assert m["total_return_pct"] == pytest.approx(10.0)
    assert m["final_equity"] == pytest.approx(1_100_000)
    assert m["excess_return_pct"] == pytest.approx(5.0)


def test_max_drawdown():
    equity = [100, 120, 90, 110, 130]
    m = compute_metrics([], np.array(equity, float),
                        pd.Series(pd.date_range("2026-01-01", periods=5, freq="5min", tz="UTC")),
                        "5m", 100, 0.0)
    assert m["max_drawdown_pct"] == pytest.approx((90 / 120 - 1) * 100)


def test_win_rate_and_profit_factor():
    trades = [_trade(100, 1.0), _trade(200, 2.0), _trade(-100, -1.0), _trade(-50, -0.5)]
    trades, equity, ts = make_inputs(trades, [1000, 1150])
    m = compute_metrics(trades, equity, ts, "5m", 1000, 0.0)
    assert m["win_rate_pct"] == pytest.approx(50.0)
    assert m["profit_factor"] == pytest.approx(300 / 150)
    assert m["max_win_streak"] == 2
    assert m["max_loss_streak"] == 2


def test_total_fees_sum():
    trades = [_trade(100, 1.0, fee=25.0), _trade(-50, -0.5, fee=15.0)]
    trades, equity, ts = make_inputs(trades, [1000, 1050])
    m = compute_metrics(trades, equity, ts, "5m", 1000, 0.0)
    assert m["total_fees_krw"] == pytest.approx(25 * 2 + 15 * 2)


def test_short_period_and_low_trade_warnings():
    trades, equity, ts = make_inputs([_trade(100, 1.0)], [1000, 1010])
    m = compute_metrics(trades, equity, ts, "5m", 1000, 0.0, min_trades_warn=20)
    assert any("거래 수" in w for w in m["warnings"])
    assert any("연환산" in w for w in m["warnings"])


def test_single_trade_dominance_warning():
    trades = [_trade(1000, 10.0), _trade(10, 0.1), _trade(20, 0.2)]
    trades, equity, ts = make_inputs(trades, [1000, 2030])
    m = compute_metrics(trades, equity, ts, "5m", 1000, 0.0, min_trades_warn=1)
    assert any("50%" in w for w in m["warnings"])
