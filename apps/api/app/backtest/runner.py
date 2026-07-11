"""Backtest run orchestration: data -> indicators -> engine -> metrics."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import pandas as pd

from app.backtest.engine import BacktestEngine, CostConfig, EngineConfig, SizingConfig, buy_and_hold
from app.backtest.metrics import compute_metrics
from app.config import settings
from app.data.service import apply_candle_policy, ensure_candles
from app.data.store import CandleStore
from app.db import db
from app.jobs import Job
from app.strategies.builtin import build_strategy_definition


def resolve_strategy(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve the strategy definition from a backtest config.

    Accepts either {"template": "...", "params": {...}},
    {"strategyId": "..."} (saved strategy), or a full inline {"definition"}.
    """
    if config.get("definition"):
        return config["definition"]
    if config.get("strategyId"):
        saved = db.get_strategy(config["strategyId"])
        if not saved:
            raise ValueError(f"strategy not found: {config['strategyId']}")
        definition = saved["definition"]
        if definition.get("template") and config.get("params"):
            return build_strategy_definition(definition["template"], {**definition.get("params", {}), **config["params"]})
        return definition
    if config.get("template"):
        return build_strategy_definition(config["template"], config.get("params"))
    raise ValueError("config must include template, strategyId, or definition")


def _cost_config(config: dict[str, Any]) -> CostConfig:
    c = config.get("costs", {}) or {}
    return CostConfig(
        buy_fee_rate=float(c.get("buyFeeRate", settings.default_fee_rate)),
        sell_fee_rate=float(c.get("sellFeeRate", settings.default_fee_rate)),
        buy_slippage_rate=float(c.get("buySlippageRate", settings.default_slippage_rate)),
        sell_slippage_rate=float(c.get("sellSlippageRate", settings.default_slippage_rate)),
        min_order_krw=float(c.get("minOrderKrw", settings.default_min_order_krw)),
        initial_capital=float(c.get("initialCapital", settings.default_initial_capital)),
    )


def _sizing_config(config: dict[str, Any]) -> SizingConfig:
    s = config.get("positionSizing", {}) or {}
    return SizingConfig(type=s.get("type", "all_in"), value=float(s.get("value", 0.0)))


def run_backtest_sync(df: pd.DataFrame, config: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    """Pure CPU part of a backtest on prepared candles (no I/O)."""
    costs = _cost_config(config)
    sizing = _sizing_config(config)
    engine_cfg = EngineConfig(
        ambiguity_mode=config.get("ambiguityMode", "conservative"),
        force_exit_at_end=bool(config.get("forceExitAtEnd", True)),
    )
    engine = BacktestEngine(df, strategy, costs, sizing, engine_cfg)
    raw = engine.run()
    bh = buy_and_hold(df, costs)

    trades = raw["trades"]
    if config.get("ambiguityMode") == "invalidate":
        stats_trades = [t for t in trades if not t.get("ambiguous")]
    else:
        stats_trades = trades

    metrics = compute_metrics(
        stats_trades,
        raw["equity"],
        df["ts"],
        config["timeframe"],
        costs.initial_capital,
        bh["return_pct"],
        settings.min_trades_for_confidence,
    )
    if raw["synthetic_ratio"] > settings.synthetic_candle_warn_ratio:
        metrics["warnings"].append(
            f"합성(빈) 캔들 비율이 {raw['synthetic_ratio'] * 100:.1f}%로 높습니다. 유동성이 낮아 백테스트 신뢰도가 떨어질 수 있습니다."
        )
    if raw["skipped_min_order"]:
        metrics["warnings"].append(f"최소 주문금액 미만으로 건너뛴 진입 {raw['skipped_min_order']}건이 있습니다.")

    ts_list = df["ts"].dt.strftime("%Y-%m-%dT%H:%M:%S%z").tolist()
    return {
        "metrics": metrics,
        "trades": trades,
        "equity_curve": [round(float(v), 2) for v in raw["equity"]],
        "buy_hold_curve": [round(float(v), 2) for v in bh["equity"]],
        "timestamps": ts_list,
        "synthetic_ratio": raw["synthetic_ratio"],
    }


async def execute_backtest(run_id: str, config: dict[str, Any], job: Job) -> None:
    """Full async pipeline persisted to the `backtests` table."""
    store = CandleStore()

    def progress(stage: str, n: int = 0) -> None:
        db.update_run("backtests", run_id, status=stage, progress={"stage": stage, "count": n})

    try:
        strategy = resolve_strategy(config)
        db.update_run("backtests", run_id, status="fetching_data")
        start = datetime.fromisoformat(config["start"])
        end = datetime.fromisoformat(config["end"])
        df = await ensure_candles(
            store, config["market"], config["timeframe"], start, end,
            progress=lambda s, n: progress("fetching_data", n),
            cancelled=lambda: job.cancelled,
        )
        if job.cancelled:
            db.update_run("backtests", run_id, status="cancelled")
            return
        db.update_run("backtests", run_id, status="preparing_data")
        df = apply_candle_policy(df, config["timeframe"], config.get("candlePolicy", "raw"))
        if len(df) < 10:
            raise ValueError(f"캔들 데이터가 부족합니다 ({len(df)}개). 기간 또는 종목을 확인하세요.")

        db.update_run("backtests", run_id, status="running_backtest")
        result = await asyncio.to_thread(run_backtest_sync, df, config, strategy)
        if job.cancelled:
            db.update_run("backtests", run_id, status="cancelled")
            return

        db.update_run("backtests", run_id, status="calculating_metrics")
        # candles for the chart (bounded payload)
        chart = df[["ts", "open", "high", "low", "close", "volume", "is_synthetic"]].copy()
        # datetime may be ns- or us-resolution depending on source; convert robustly
        epoch = pd.Timestamp(0, tz="UTC")
        chart["time"] = ((chart["ts"] - epoch) // pd.Timedelta(seconds=1)).astype(int)
        result["candles"] = chart.drop(columns=["ts"]).to_dict(orient="records")
        db.update_run("backtests", run_id, status="completed", result=result)
    except asyncio.CancelledError:
        db.update_run("backtests", run_id, status="cancelled")
        raise
    except Exception as exc:  # persist failure reason for the UI
        db.update_run("backtests", run_id, status="failed", error=str(exc))


def _slice_period(df: pd.DataFrame, ratio: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    cut = int(len(df) * ratio)
    return df.iloc[:cut].reset_index(drop=True), df.iloc[cut:].reset_index(drop=True)


OBJECTIVES = {
    "total_return": lambda m: m["total_return_pct"],
    "sharpe": lambda m: m["sharpe"],
    "sortino": lambda m: m["sortino"],
    "calmar": lambda m: m["calmar"],
    "profit_factor": lambda m: m["profit_factor"] or 0.0,
    "return_over_mdd": lambda m: (m["total_return_pct"] / abs(m["max_drawdown_pct"])) if m["max_drawdown_pct"] < 0 else m["total_return_pct"],
}


async def execute_optimization(run_id: str, config: dict[str, Any], job: Job) -> None:
    """Grid search with train/validation split (anti-overfit by default)."""
    store = CandleStore()
    try:
        template = config["template"]
        base_params = config.get("params", {}) or {}
        grid: dict[str, list[Any]] = config["grid"]
        objective = OBJECTIVES.get(config.get("objective", "return_over_mdd"), OBJECTIVES["return_over_mdd"])
        train_ratio = float(config.get("trainRatio", 0.7))

        # cartesian product with a hard cap
        import itertools

        keys = list(grid.keys())
        combos = list(itertools.product(*[grid[k] for k in keys]))
        if len(combos) > settings.optimization_max_combinations:
            raise ValueError(
                f"조합 수 {len(combos)}개가 최대 허용치({settings.optimization_max_combinations})를 초과합니다."
            )

        db.update_run("optimizations", run_id, status="fetching_data")
        start = datetime.fromisoformat(config["start"])
        end = datetime.fromisoformat(config["end"])
        df = await ensure_candles(
            store, config["market"], config["timeframe"], start, end,
            cancelled=lambda: job.cancelled,
        )
        df = apply_candle_policy(df, config["timeframe"], config.get("candlePolicy", "raw"))
        if len(df) < 50:
            raise ValueError("최적화에 필요한 캔들 데이터가 부족합니다.")
        train_df, valid_df = _slice_period(df, train_ratio)

        db.update_run("optimizations", run_id, status="running_backtest",
                      progress={"total": len(combos), "done": 0})
        results = []
        for idx, combo in enumerate(combos):
            if job.cancelled:
                db.update_run("optimizations", run_id, status="cancelled")
                return
            params = {**base_params, **dict(zip(keys, combo))}
            strategy = build_strategy_definition(template, params)
            bt_config = {**config, "params": params}
            train_res = await asyncio.to_thread(run_backtest_sync, train_df, bt_config, strategy)
            valid_res = (
                await asyncio.to_thread(run_backtest_sync, valid_df, bt_config, strategy)
                if len(valid_df) >= 10
                else None
            )
            entry = {
                "params": dict(zip(keys, combo)),
                "train": _summarize(train_res["metrics"]),
                "valid": _summarize(valid_res["metrics"]) if valid_res else None,
                "score": objective(train_res["metrics"]),
            }
            if valid_res:
                entry["valid_score"] = objective(valid_res["metrics"])
            results.append(entry)
            if (idx + 1) % 5 == 0 or idx == len(combos) - 1:
                db.update_run("optimizations", run_id, progress={"total": len(combos), "done": idx + 1})

        results.sort(key=lambda r: r["score"], reverse=True)
        warnings = []
        if results and results[0].get("valid_score") is not None:
            top = results[0]
            if top["score"] > 0 and (top["valid_score"] or 0) < top["score"] * 0.3:
                warnings.append("훈련 구간 성과 대비 검증 구간 성과가 크게 낮습니다. 과최적화 가능성이 큽니다.")
        db.update_run(
            "optimizations", run_id, status="completed",
            result={"results": results, "keys": keys, "warnings": warnings,
                    "train_ratio": train_ratio, "combinations": len(combos)},
        )
    except asyncio.CancelledError:
        db.update_run("optimizations", run_id, status="cancelled")
        raise
    except Exception as exc:
        db.update_run("optimizations", run_id, status="failed", error=str(exc))


def _summarize(m: dict[str, Any]) -> dict[str, Any]:
    keys = ["total_return_pct", "max_drawdown_pct", "sharpe", "sortino", "profit_factor",
            "win_rate_pct", "trade_count", "payoff_ratio", "excess_return_pct"]
    return {k: (None if m.get(k) is None else round(float(m[k]), 4)) for k in keys}
