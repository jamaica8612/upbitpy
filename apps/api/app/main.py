"""Upbit Strategy Lab API.

연구·검증 도구입니다. 투자 추천이 아니며, 실주문 기능은 없습니다
(브로커 어댑터 인터페이스만 정의되어 있습니다 — docs/live-trading.md 참고).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.backtest.runner import execute_backtest, execute_optimization, resolve_strategy
from app.config import settings
from app.data.service import fetch_markets
from app.data.store import CandleStore, detect_gaps
from app.db import db
from app.jobs import job_manager
from app.strategies.builtin import TEMPLATES, build_strategy_definition

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Upbit Strategy Lab API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = CandleStore()


class StrategyBody(BaseModel):
    name: str
    definition: dict[str, Any]


class BacktestBody(BaseModel):
    market: str
    timeframe: str
    start: str
    end: str
    template: str | None = None
    strategyId: str | None = None
    definition: dict[str, Any] | None = None
    params: dict[str, Any] | None = None
    costs: dict[str, Any] | None = None
    positionSizing: dict[str, Any] | None = None
    candlePolicy: str = "raw"
    ambiguityMode: str = "conservative"
    forceExitAtEnd: bool = True


class OptimizationBody(BaseModel):
    market: str
    timeframe: str
    start: str
    end: str
    template: str
    params: dict[str, Any] | None = None
    grid: dict[str, list[Any]] = Field(default_factory=dict)
    objective: str = "return_over_mdd"
    trainRatio: float = 0.7
    costs: dict[str, Any] | None = None
    positionSizing: dict[str, Any] | None = None
    candlePolicy: str = "raw"


class SettingsBody(BaseModel):
    values: dict[str, Any]


# ---- markets & data --------------------------------------------------------

@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/markets")
async def markets(krw_only: bool = True) -> list[dict[str, Any]]:
    try:
        out = await fetch_markets()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"업비트 마켓 조회 실패: {exc}") from exc
    if krw_only:
        out = [m for m in out if m["market"].startswith("KRW-")]
    return out


@app.get("/api/data/status")
def data_status() -> list[dict[str, Any]]:
    return store.status()


@app.get("/api/data/gaps")
def data_gaps(market: str, timeframe: str) -> dict[str, Any]:
    df = store.load(market, timeframe)
    return {"gaps": detect_gaps(df, timeframe), "candle_count": len(df)}


@app.delete("/api/data/cache")
def delete_cache(market: str, timeframe: str | None = None) -> dict[str, str]:
    store.delete(market, timeframe)
    return {"status": "deleted"}


@app.get("/api/data/estimate")
def estimate_download(market: str, timeframe: str, start: str, end: str) -> dict[str, Any]:
    """Rough candle-count estimate shown before a backtest starts."""
    from datetime import datetime

    from app.data.store import timeframe_delta

    span = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    total = max(int(span / timeframe_delta(timeframe)), 0)
    cached = len(store.load(market, timeframe, datetime.fromisoformat(start), datetime.fromisoformat(end)))
    return {"estimated_candles": total, "cached_candles": cached,
            "estimated_requests": max((total - cached) // 200, 0)}


# ---- strategies -------------------------------------------------------------

@app.get("/api/strategies/templates")
def strategy_templates() -> list[dict[str, Any]]:
    return [
        {"template": key, "name": spec["name"], "defaults": spec["defaults"],
         "definition": build_strategy_definition(key)}
        for key, spec in TEMPLATES.items()
    ]


@app.post("/api/strategies", status_code=201)
def create_strategy(body: StrategyBody) -> dict[str, Any]:
    return db.create_strategy(body.name, body.definition)


@app.get("/api/strategies")
def list_strategies() -> list[dict[str, Any]]:
    return db.list_strategies()


@app.get("/api/strategies/{sid}")
def get_strategy(sid: str) -> dict[str, Any]:
    s = db.get_strategy(sid)
    if not s:
        raise HTTPException(404, "전략을 찾을 수 없습니다")
    return s


@app.put("/api/strategies/{sid}")
def update_strategy(sid: str, body: StrategyBody) -> dict[str, Any]:
    s = db.update_strategy(sid, body.name, body.definition)
    if not s:
        raise HTTPException(404, "전략을 찾을 수 없습니다")
    return s


@app.delete("/api/strategies/{sid}")
def delete_strategy(sid: str) -> dict[str, str]:
    if not db.delete_strategy(sid):
        raise HTTPException(404, "전략을 찾을 수 없습니다")
    return {"status": "deleted"}


# ---- backtests ---------------------------------------------------------------

@app.post("/api/backtests", status_code=202)
async def create_backtest(body: BacktestBody) -> dict[str, str]:
    config = body.model_dump(exclude_none=True)
    try:
        snapshot = resolve_strategy(config)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    run_id = db.create_run("backtests", config, strategy_snapshot=snapshot)
    job_manager.start(run_id, lambda job: execute_backtest(run_id, config, job))
    return {"id": run_id, "status": "queued"}


@app.get("/api/backtests")
def list_backtests(limit: int = 30) -> list[dict[str, Any]]:
    return db.list_runs("backtests", limit=limit)


@app.get("/api/backtests/{rid}")
def get_backtest(rid: str) -> dict[str, Any]:
    run = db.get_run("backtests", rid)
    if not run:
        raise HTTPException(404, "백테스트를 찾을 수 없습니다")
    return run


@app.post("/api/backtests/{rid}/cancel")
def cancel_backtest(rid: str) -> dict[str, str]:
    job_manager.cancel(rid)
    run = db.get_run("backtests", rid)
    if run and run["status"] not in ("completed", "failed"):
        db.update_run("backtests", rid, status="cancelled")
    return {"status": "cancelled"}


@app.get("/api/backtests/{rid}/trades")
def get_backtest_trades(rid: str) -> list[dict[str, Any]]:
    run = db.get_run("backtests", rid)
    if not run:
        raise HTTPException(404, "백테스트를 찾을 수 없습니다")
    if not run.get("result"):
        return []
    return run["result"].get("trades", [])


# ---- optimizations -------------------------------------------------------------

@app.post("/api/optimizations", status_code=202)
async def create_optimization(body: OptimizationBody) -> dict[str, Any]:
    config = body.model_dump(exclude_none=True)

    combos = 1
    for values in config.get("grid", {}).values():
        combos *= max(len(values), 1)
    if combos > settings.optimization_max_combinations:
        raise HTTPException(400, f"조합 수 {combos}개가 한도({settings.optimization_max_combinations})를 초과합니다")
    run_id = db.create_run("optimizations", config)
    job_manager.start(run_id, lambda job: execute_optimization(run_id, config, job))
    return {"id": run_id, "status": "queued", "combinations": combos}


@app.get("/api/optimizations/{rid}")
def get_optimization(rid: str) -> dict[str, Any]:
    run = db.get_run("optimizations", rid)
    if not run:
        raise HTTPException(404, "최적화 작업을 찾을 수 없습니다")
    return run


@app.post("/api/optimizations/{rid}/cancel")
def cancel_optimization(rid: str) -> dict[str, str]:
    job_manager.cancel(rid)
    run = db.get_run("optimizations", rid)
    if run and run["status"] not in ("completed", "failed"):
        db.update_run("optimizations", rid, status="cancelled")
    return {"status": "cancelled"}


# ---- app settings ---------------------------------------------------------------

@app.get("/api/settings")
def get_app_settings() -> dict[str, Any]:
    stored = db.get_setting("app", {}) or {}
    defaults = {
        "initialCapital": settings.default_initial_capital,
        "feeRate": settings.default_fee_rate,
        "slippageRate": settings.default_slippage_rate,
        "minOrderKrw": settings.default_min_order_krw,
        "vwapAnchor": "utc_day",
        "ambiguityMode": "conservative",
        "timezone": "Asia/Seoul",
    }
    return {**defaults, **stored}


@app.put("/api/settings")
def put_app_settings(body: SettingsBody) -> dict[str, Any]:
    db.set_setting("app", body.values)
    return get_app_settings()
