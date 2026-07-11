"""Event-driven long-only spot backtest engine.

Execution rules (defaults, see spec §9):
- Signals are computed on completed candles; fills happen at the *next*
  available candle's open (synthetic candles are skipped for entries).
- Fees are charged on both buy and sell; slippage worsens fills.
- Intrabar stop/take-profit uses conservative / optimistic / invalidate
  ambiguity modes when both levels are touched in one candle.
- One position at a time, no averaging down, no pyramiding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from app.indicators import core as ind
from app.strategies.dsl import FeatureEngine, eval_group, warmup_mask


@dataclass
class CostConfig:
    buy_fee_rate: float = 0.0005
    sell_fee_rate: float = 0.0005
    buy_slippage_rate: float = 0.0005
    sell_slippage_rate: float = 0.0005
    min_order_krw: float = 5000.0
    initial_capital: float = 10_000_000.0


@dataclass
class SizingConfig:
    type: str = "all_in"  # all_in | fixed_krw | percent_equity | risk_percent
    value: float = 0.0


@dataclass
class EngineConfig:
    ambiguity_mode: str = "conservative"  # conservative | optimistic | invalidate
    force_exit_at_end: bool = True


@dataclass
class Trade:
    entry_index: int
    entry_ts: str
    entry_price: float
    quantity: float
    invested_krw: float
    entry_fee: float
    entry_reason: str = "signal"
    entry_snapshot: dict[str, float] = field(default_factory=dict)
    exit_index: int | None = None
    exit_ts: str | None = None
    exit_price: float | None = None
    exit_fee: float = 0.0
    exit_reason: str | None = None
    proceeds_krw: float | None = None
    pnl_krw: float | None = None
    return_pct: float | None = None
    gross_return_pct: float | None = None
    hold_bars: int = 0
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    ambiguous: bool = False
    forced_exit: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class BacktestEngine:
    def __init__(
        self,
        df: pd.DataFrame,
        strategy: dict[str, Any],
        costs: CostConfig,
        sizing: SizingConfig,
        engine_cfg: EngineConfig | None = None,
    ) -> None:
        if not df["ts"].is_monotonic_increasing:
            raise ValueError("candles must be ascending by ts")
        self.df = df.reset_index(drop=True)
        self.strategy = strategy
        self.costs = costs
        self.sizing = sizing
        self.cfg = engine_cfg or EngineConfig()

    # ------------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        df = self.df
        fe = FeatureEngine(df)
        entry_signal = eval_group(fe, self.strategy.get("entry", {"operator": "AND", "conditions": []}))
        exit_signal = eval_group(fe, self.strategy.get("exit", {"operator": "OR", "conditions": []}))
        warm = warmup_mask(fe, self.strategy.get("entry", {})) & warmup_mask(fe, self.strategy.get("exit", {}))
        entry_signal &= warm

        risk = self.strategy.get("risk", {}) or {}
        atr_period = int(risk.get("atrPeriod", 14))
        needs_atr = "atr" in (
            str(risk.get("stopLossType")), str(risk.get("takeProfitType")), str(risk.get("trailingStopType")),
        ) or self.sizing.type == "risk_percent"
        atr_series = ind.atr(df["high"], df["low"], df["close"], atr_period) if needs_atr else None

        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()
        synthetic = df["is_synthetic"].to_numpy() if "is_synthetic" in df else np.zeros(len(df), bool)
        ts = df["ts"]

        cash = self.costs.initial_capital
        qty = 0.0
        trades: list[Trade] = []
        open_trade: Trade | None = None
        pending_entry_signal_idx: int | None = None
        pending_exit_reason: str | None = None
        stop_price = np.nan
        take_price = np.nan
        trail_price = np.nan
        skipped_min_order = 0
        equity = np.empty(len(df))

        max_hold = risk.get("maxHoldBars")
        max_hold = int(max_hold) if max_hold else None

        for i in range(len(df)):
            o, h, lo, c = opens[i], highs[i], lows[i], closes[i]

            # -- 1) pending exit from previous bar's signal: fill at this open
            if open_trade is not None and pending_exit_reason is not None:
                self._close(open_trade, i, ts, self._sell_fill(o), pending_exit_reason)
                cash += open_trade.proceeds_krw or 0.0
                qty = 0.0
                trades.append(open_trade)
                open_trade = None
                pending_exit_reason = None

            # -- 2) pending entry: fill at this open (skip synthetic bars)
            if open_trade is None and pending_entry_signal_idx is not None:
                if not synthetic[i]:
                    invest = self._position_size(cash, cash + qty * closes[i - 1] if i else cash,
                                                 atr_series.iloc[pending_entry_signal_idx] if atr_series is not None else np.nan,
                                                 o)
                    invest = min(invest, cash)
                    if invest < self.costs.min_order_krw:
                        skipped_min_order += 1
                    else:
                        fill = self._buy_fill(o)
                        fee = invest * self.costs.buy_fee_rate
                        bought_qty = (invest - fee) / fill
                        cash -= invest
                        qty = bought_qty
                        sig_i = pending_entry_signal_idx
                        snapshot = self._snapshot(fe, sig_i)
                        open_trade = Trade(
                            entry_index=i,
                            entry_ts=ts.iloc[i].isoformat(),
                            entry_price=fill,
                            quantity=bought_qty,
                            invested_krw=invest,
                            entry_fee=fee,
                            entry_snapshot=snapshot,
                        )
                        stop_price, take_price = self._initial_levels(risk, fill, atr_series, sig_i)
                        trail_price = self._initial_trail(risk, fill, atr_series, sig_i)
                    pending_entry_signal_idx = None
                # else: wait for the next non-synthetic bar

            # -- 3) intrabar stop / take-profit on the open position
            if open_trade is not None and i > open_trade.entry_index:
                open_trade.hold_bars = i - open_trade.entry_index
                # Trailing stop: check against the level ratcheted by *previous*
                # bars first (intra-bar high->low order is unknowable from OHLC),
                # then update with this bar's high afterwards.
                eff_stop = np.nanmax([stop_price, trail_price]) if not (np.isnan(stop_price) and np.isnan(trail_price)) else np.nan

                hit_stop = not np.isnan(eff_stop) and lo <= eff_stop
                hit_take = not np.isnan(take_price) and h >= take_price
                exit_now: tuple[float, str] | None = None
                ambiguous = False
                if hit_stop and hit_take:
                    ambiguous = True
                    if self.cfg.ambiguity_mode == "optimistic":
                        exit_now = (min(max(o, take_price), h), "take_profit")
                    else:  # conservative & invalidate both fill at stop
                        exit_now = (min(o, eff_stop), "stop_loss")
                elif hit_stop:
                    exit_now = (min(o, eff_stop), "stop_loss")
                elif hit_take:
                    exit_now = (max(o, take_price), "take_profit")

                if exit_now is not None:
                    price, reason = exit_now
                    open_trade.ambiguous = ambiguous and self.cfg.ambiguity_mode == "invalidate"
                    self._close(open_trade, i, ts, self._sell_fill(price), reason)
                    cash += open_trade.proceeds_krw or 0.0
                    qty = 0.0
                    trades.append(open_trade)
                    open_trade = None
                else:
                    # track MFE / MAE on candle extremes
                    open_trade.mfe_pct = max(open_trade.mfe_pct, (h / open_trade.entry_price - 1) * 100)
                    open_trade.mae_pct = min(open_trade.mae_pct, (lo / open_trade.entry_price - 1) * 100)
                    # ratchet the trailing stop with this bar's high
                    if not np.isnan(trail_price):
                        new_trail = self._update_trail(risk, h, atr_series, i)
                        if not np.isnan(new_trail):
                            trail_price = max(trail_price, new_trail)

            # -- 4) signals on this completed bar -> queue for next bar
            if open_trade is not None:
                if bool(exit_signal.iloc[i]):
                    pending_exit_reason = "signal"
                elif max_hold is not None and (i - open_trade.entry_index) >= max_hold:
                    pending_exit_reason = "max_hold"
            elif pending_entry_signal_idx is None and bool(entry_signal.iloc[i]):
                pending_entry_signal_idx = i

            equity[i] = cash + qty * c

        # -- forced exit at the end of data
        if open_trade is not None:
            if self.cfg.force_exit_at_end:
                last = len(df) - 1
                open_trade.hold_bars = last - open_trade.entry_index
                open_trade.forced_exit = True
                self._close(open_trade, last, ts, self._sell_fill(closes[last]), "end_of_data")
                cash += open_trade.proceeds_krw or 0.0
                qty = 0.0
                equity[last] = cash
                trades.append(open_trade)
                open_trade = None
            else:
                trades.append(open_trade)  # left open, exit fields None

        return {
            "trades": [t.as_dict() for t in trades],
            "equity": equity,
            "entry_signal": entry_signal,
            "exit_signal": exit_signal,
            "skipped_min_order": skipped_min_order,
            "synthetic_ratio": float(synthetic.mean()) if len(df) else 0.0,
        }

    # ------------------------------------------------------------------

    def _buy_fill(self, price: float) -> float:
        return price * (1 + self.costs.buy_slippage_rate)

    def _sell_fill(self, price: float) -> float:
        return price * (1 - self.costs.sell_slippage_rate)

    def _position_size(self, cash: float, equity: float, atr_value: float, price: float) -> float:
        s = self.sizing
        if s.type == "fixed_krw":
            return float(s.value)
        if s.type == "percent_equity":
            return equity * float(s.value) / 100.0
        if s.type == "risk_percent":
            # risk `value`% of equity per trade based on ATR stop distance
            risk = self.strategy.get("risk", {}) or {}
            stop_mult = float(risk.get("stopLossValue", 1.0) or 1.0)
            if np.isnan(atr_value) or atr_value <= 0 or stop_mult <= 0:
                return 0.0
            risk_amount = equity * float(s.value) / 100.0
            stop_distance_pct = (atr_value * stop_mult) / price
            if stop_distance_pct <= 0:
                return 0.0
            return min(risk_amount / stop_distance_pct, cash)
        return cash  # all_in

    def _initial_levels(self, risk: dict, fill: float, atr_series: pd.Series | None, sig_i: int) -> tuple[float, float]:
        stop = np.nan
        take = np.nan
        atr_v = float(atr_series.iloc[sig_i]) if atr_series is not None and not np.isnan(atr_series.iloc[sig_i]) else np.nan
        slt, slv = risk.get("stopLossType", "none"), float(risk.get("stopLossValue", 0) or 0)
        tpt, tpv = risk.get("takeProfitType", "none"), float(risk.get("takeProfitValue", 0) or 0)
        if slt == "atr" and not np.isnan(atr_v):
            stop = fill - atr_v * slv
        elif slt == "percent" and slv > 0:
            stop = fill * (1 - slv / 100.0)
        if tpt == "atr" and not np.isnan(atr_v):
            take = fill + atr_v * tpv
        elif tpt == "percent" and tpv > 0:
            take = fill * (1 + tpv / 100.0)
        return stop, take

    def _initial_trail(self, risk: dict, fill: float, atr_series: pd.Series | None, sig_i: int) -> float:
        tt, tv = risk.get("trailingStopType"), float(risk.get("trailingStopValue", 0) or 0)
        if tt == "atr" and atr_series is not None and not np.isnan(atr_series.iloc[sig_i]):
            return fill - float(atr_series.iloc[sig_i]) * tv
        if tt == "percent" and tv > 0:
            return fill * (1 - tv / 100.0)
        return np.nan

    def _update_trail(self, risk: dict, high: float, atr_series: pd.Series | None, i: int) -> float:
        tt, tv = risk.get("trailingStopType"), float(risk.get("trailingStopValue", 0) or 0)
        if tt == "atr" and atr_series is not None and not np.isnan(atr_series.iloc[i]):
            return high - float(atr_series.iloc[i]) * tv
        if tt == "percent" and tv > 0:
            return high * (1 - tv / 100.0)
        return np.nan

    def _close(self, trade: Trade, i: int, ts: pd.Series, fill: float, reason: str) -> None:
        gross = trade.quantity * fill
        fee = gross * self.costs.sell_fee_rate
        trade.exit_index = i
        trade.exit_ts = ts.iloc[i].isoformat()
        trade.exit_price = fill
        trade.exit_fee = fee
        trade.exit_reason = reason
        trade.proceeds_krw = gross - fee
        trade.pnl_krw = trade.proceeds_krw - trade.invested_krw
        trade.return_pct = (trade.proceeds_krw / trade.invested_krw - 1) * 100.0
        trade.gross_return_pct = (fill / trade.entry_price - 1) * 100.0
        trade.hold_bars = i - trade.entry_index

    def _snapshot(self, fe: FeatureEngine, i: int) -> dict[str, float]:
        """Indicator values at signal time, for the trade-detail popup."""
        out: dict[str, float] = {}
        for key, series in list(fe._cache.items())[:12]:
            try:
                v = series.iloc[i]
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    out[_short_key(key)] = round(float(v), 8)
            except (IndexError, TypeError, ValueError):
                continue
        return out


def _short_key(key: str) -> str:
    # cache keys are repr() of operand dicts; compress for display
    return key.replace("'", "").replace(", ", ",")[:80]


def buy_and_hold(df: pd.DataFrame, costs: CostConfig) -> dict[str, Any]:
    """Benchmark: buy at first open (with fees/slippage), hold to last close."""
    if df.empty:
        return {"equity": np.array([]), "return_pct": 0.0}
    fill = df["open"].iloc[0] * (1 + costs.buy_slippage_rate)
    fee = costs.initial_capital * costs.buy_fee_rate
    qty = (costs.initial_capital - fee) / fill
    equity = qty * df["close"].to_numpy()
    final = qty * df["close"].iloc[-1] * (1 - costs.sell_slippage_rate) * (1 - costs.sell_fee_rate)
    return {"equity": equity, "return_pct": (final / costs.initial_capital - 1) * 100.0}
