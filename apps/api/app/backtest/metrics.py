"""Performance metrics computed from trades + equity curve."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from app.data.store import timeframe_delta

MINUTES_PER_YEAR = 365 * 24 * 60


def compute_metrics(
    trades: list[dict[str, Any]],
    equity: np.ndarray,
    ts: pd.Series,
    timeframe: str,
    initial_capital: float,
    buy_hold_return_pct: float,
    min_trades_warn: int = 20,
) -> dict[str, Any]:
    closed = [t for t in trades if t.get("exit_price") is not None]
    returns = np.array([t["return_pct"] for t in closed]) if closed else np.array([])
    pnls = np.array([t["pnl_krw"] for t in closed]) if closed else np.array([])

    final_equity = float(equity[-1]) if len(equity) else initial_capital
    total_return_pct = (final_equity / initial_capital - 1) * 100.0

    # drawdown
    if len(equity):
        peak = np.maximum.accumulate(equity)
        dd = (equity / peak - 1) * 100.0
        max_drawdown_pct = float(dd.min())
    else:
        dd = np.array([])
        max_drawdown_pct = 0.0

    wins = returns[returns > 0]
    losses = returns[returns <= 0]
    win_pnls = pnls[pnls > 0]
    loss_pnls = pnls[pnls <= 0]
    win_rate = len(wins) / len(returns) * 100.0 if len(returns) else 0.0
    gross_profit = float(win_pnls.sum()) if len(win_pnls) else 0.0
    gross_loss = float(-loss_pnls.sum()) if len(loss_pnls) else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else 0.0)

    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    payoff = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0
    expectancy = float(returns.mean()) if len(returns) else 0.0

    # per-bar returns for Sharpe/Sortino, annualized by bar duration
    bar_minutes = timeframe_delta(timeframe).total_seconds() / 60
    bars_per_year = MINUTES_PER_YEAR / bar_minutes
    if len(equity) > 1:
        bar_returns = np.diff(equity) / equity[:-1]
        mean_r, std_r = bar_returns.mean(), bar_returns.std(ddof=1) if len(bar_returns) > 1 else 0.0
        sharpe = float(mean_r / std_r * math.sqrt(bars_per_year)) if std_r > 0 else 0.0
        downside = bar_returns[bar_returns < 0]
        downside_std = downside.std(ddof=1) if len(downside) > 1 else 0.0
        sortino = float(mean_r / downside_std * math.sqrt(bars_per_year)) if downside_std > 0 else 0.0
        years = len(bar_returns) / bars_per_year
        # annualizing sub-week periods explodes numerically; report 0 and warn
        if years >= 7 / 365 and final_equity > 0:
            try:
                cagr = ((final_equity / initial_capital) ** (1 / years) - 1) * 100.0
            except OverflowError:
                cagr = 0.0
        else:
            cagr = 0.0
    else:
        sharpe = sortino = cagr = 0.0
        years = 0.0
    calmar = float(cagr / abs(max_drawdown_pct)) if max_drawdown_pct < 0 else 0.0

    # streaks
    max_win_streak = max_loss_streak = cur_w = cur_l = 0
    for r in returns:
        if r > 0:
            cur_w += 1
            cur_l = 0
        else:
            cur_l += 1
            cur_w = 0
        max_win_streak = max(max_win_streak, cur_w)
        max_loss_streak = max(max_loss_streak, cur_l)

    hold_bars = [t["hold_bars"] for t in closed]
    exposure_bars = sum(hold_bars)
    exposure_pct = exposure_bars / len(equity) * 100.0 if len(equity) else 0.0
    total_fees = float(sum(t.get("entry_fee", 0) + t.get("exit_fee", 0) for t in closed))

    # calendar breakdowns (in KST per UI convention)
    monthly: dict[str, float] = {}
    weekday: dict[str, float] = {}
    hourly: dict[str, float] = {}
    if closed:
        tdf = pd.DataFrame(closed)
        entry_ts = pd.to_datetime(tdf["exit_ts"], utc=True, format="ISO8601").dt.tz_convert("Asia/Seoul")
        tdf["_month"] = entry_ts.dt.strftime("%Y-%m")
        tdf["_weekday"] = entry_ts.dt.weekday.astype(str)
        tdf["_hour"] = entry_ts.dt.hour.astype(str)
        monthly = tdf.groupby("_month")["pnl_krw"].sum().round(0).to_dict()
        weekday = tdf.groupby("_weekday")["pnl_krw"].sum().round(0).to_dict()
        hourly = tdf.groupby("_hour")["pnl_krw"].sum().round(0).to_dict()

    warnings: list[str] = []
    if len(closed) < min_trades_warn:
        warnings.append(f"거래 수가 {len(closed)}건으로 적어 통계 신뢰도가 낮습니다 (최소 {min_trades_warn}건 권장).")
    if years > 0 and years < 0.25:
        warnings.append("백테스트 기간이 3개월 미만이라 연환산 지표(CAGR·Sharpe)가 왜곡될 수 있습니다.")
    if closed and len(pnls) > 0 and pnls.sum() > 0:
        top = float(np.sort(pnls)[-1])
        if top > pnls.sum() * 0.5:
            warnings.append("한 건의 거래가 전체 수익의 50% 이상을 차지합니다. 과최적화 가능성에 주의하세요.")

    best = max(closed, key=lambda t: t["return_pct"], default=None)
    worst = min(closed, key=lambda t: t["return_pct"], default=None)

    return {
        "final_equity": final_equity,
        "total_return_pct": total_return_pct,
        "buy_hold_return_pct": buy_hold_return_pct,
        "excess_return_pct": total_return_pct - buy_hold_return_pct,
        "max_drawdown_pct": max_drawdown_pct,
        "cagr_pct": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "trade_count": len(closed),
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor if math.isfinite(profit_factor) else None,
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "payoff_ratio": payoff,
        "expectancy_pct": expectancy,
        "max_win_streak": max_win_streak,
        "max_loss_streak": max_loss_streak,
        "avg_hold_bars": float(np.mean(hold_bars)) if hold_bars else 0.0,
        "max_hold_bars": int(max(hold_bars)) if hold_bars else 0,
        "exposure_pct": exposure_pct,
        "total_fees_krw": total_fees,
        "best_trade_pct": best["return_pct"] if best else None,
        "worst_trade_pct": worst["return_pct"] if worst else None,
        "monthly_pnl": monthly,
        "weekday_pnl": weekday,
        "hourly_pnl": hourly,
        "warnings": warnings,
        "drawdown_curve": dd.tolist(),
    }
