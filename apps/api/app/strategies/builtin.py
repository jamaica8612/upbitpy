"""Built-in strategy templates.

Each template is a function (params -> strategy definition JSON). Every
numeric value is a parameter so the optimizer and the UI can vary them.
"""
from __future__ import annotations

from typing import Any


def _ind(name: str, timeframe: str | None = None, field: str | None = None, **params: Any) -> dict[str, Any]:
    op: dict[str, Any] = {"kind": "indicator", "name": name}
    if params:
        op["params"] = params
    if field:
        op["field"] = field
    if timeframe:
        op["timeframe"] = timeframe
    return op


def _const(value: Any) -> dict[str, Any]:
    return {"kind": "const", "value": value}


def _cond(left: dict, op: str, right: dict, **params: Any) -> dict[str, Any]:
    c: dict[str, Any] = {"left": left, "op": op, "right": right}
    if params:
        c["params"] = params
    return c


def _and(*conditions: dict) -> dict[str, Any]:
    return {"operator": "AND", "conditions": list(conditions)}


def _or(*conditions: dict) -> dict[str, Any]:
    return {"operator": "OR", "conditions": list(conditions)}


# ---------------------------------------------------------------------------

def vwap_pullback(p: dict[str, Any]) -> dict[str, Any]:
    """전략 1: VWAP 눌림매수."""
    ema_fast = _ind("ema", period=p["emaFast"])
    ema_slow = _ind("ema", period=p["emaSlow"])
    vwap = _ind("vwap", anchor=p["vwapAnchor"])
    return {
        "entry": _and(
            _cond(ema_fast, ">", ema_slow),
            _cond(_ind("close"), ">", vwap),
            _or(
                _cond(_ind("low"), "touched_within", vwap, bars=p["pullbackBars"], tolerance_percent=p["pullbackTolerancePct"]),
                _cond(_ind("low"), "touched_within", ema_fast, bars=p["pullbackBars"], tolerance_percent=p["pullbackTolerancePct"]),
            ),
            _cond(_ind("close"), "crosses_above", ema_fast),
            _cond(_ind("volume"), ">=", {**_ind("volume_sma", period=p["volumeSmaPeriod"]), "multiply": p["volumeMult"]}),
            _cond(_ind("rsi", period=p["rsiPeriod"]), "between", _const([p["rsiMin"], p["rsiMax"]])),
        ),
        "exit": _or(_cond(_ind("close"), "<", vwap)),
        "risk": {
            "stopLossType": "atr", "stopLossValue": p["atrStopMult"],
            "takeProfitType": "atr", "takeProfitValue": p["atrTakeMult"],
            "atrPeriod": p["atrPeriod"], "maxHoldBars": p["maxHoldBars"],
        },
    }


def ema_pullback(p: dict[str, Any]) -> dict[str, Any]:
    """전략 2: EMA 눌림매수."""
    ema_fast = _ind("ema", period=p["emaFast"])
    ema_slow = _ind("ema", period=p["emaSlow"])
    return {
        "entry": _and(
            _cond(ema_fast, ">", ema_slow),
            _cond(_ind("close"), ">", ema_slow),
            _cond(_ind("low"), "touched_within", ema_fast, bars=p["pullbackBars"], tolerance_percent=p["pullbackTolerancePct"]),
            _cond(_ind("close"), ">", ema_fast),
            _cond(_ind("rsi", period=p["rsiPeriod"]), "between", _const([p["rsiMin"], p["rsiMax"]])),
        ),
        "exit": _or(
            _cond(ema_fast, "crosses_below", ema_slow),
            _cond(_ind("close"), "<", ema_slow),
        ),
        "risk": {
            "stopLossType": "atr", "stopLossValue": p["atrStopMult"],
            "takeProfitType": "atr", "takeProfitValue": p["atrTakeMult"],
            "atrPeriod": p["atrPeriod"], "maxHoldBars": p["maxHoldBars"],
        },
    }


def ema_golden_cross(p: dict[str, Any]) -> dict[str, Any]:
    """전략 3: EMA 골든크로스 (+상위 타임프레임 추세 필터)."""
    ema_fast = _ind("ema", period=p["emaFast"])
    ema_slow = _ind("ema", period=p["emaSlow"])
    conditions = [
        _cond(ema_fast, "crosses_above", ema_slow),
        _cond(_ind("relative_volume", period=p["volumeSmaPeriod"]), ">=", _const(p["minRelativeVolume"])),
    ]
    if p.get("htf"):
        conditions.append(
            _cond(_ind("close", timeframe=p["htf"]), ">", _ind("ema", timeframe=p["htf"], period=p["htfEmaPeriod"]))
        )
    return {
        "entry": _and(*conditions),
        "exit": _or(_cond(ema_fast, "crosses_below", ema_slow)),
        "risk": {
            "stopLossType": "atr", "stopLossValue": p["atrStopMult"],
            "takeProfitType": "atr", "takeProfitValue": p["atrTakeMult"],
            "atrPeriod": p["atrPeriod"], "maxHoldBars": p["maxHoldBars"],
        },
    }


def rsi_trend_rebound(p: dict[str, Any]) -> dict[str, Any]:
    """전략 4: RSI 추세 필터 반등 — RSI가 과매도선을 '상향 재돌파'해야 진입."""
    rsi = _ind("rsi", period=p["rsiPeriod"])
    conditions = [
        _cond(_ind("close"), ">", _ind("ema", period=p["trendEmaPeriod"])),
        _cond(rsi, "crosses_above", _const(p["rsiOversold"])),
    ]
    if p.get("useBollingerReentry"):
        conditions.append(
            _cond(_ind("close"), "crosses_above", _ind("bollinger", field="lower", period=p["bbPeriod"], mult=p["bbMult"]))
        )
    return {
        "entry": _and(*conditions),
        "exit": _or(_cond(rsi, ">", _const(p["rsiExit"]))),
        "risk": {
            "stopLossType": "atr", "stopLossValue": p["atrStopMult"],
            "takeProfitType": "atr", "takeProfitValue": p["atrTakeMult"],
            "atrPeriod": p["atrPeriod"], "maxHoldBars": p["maxHoldBars"],
        },
    }


def bollinger_mean_reversion(p: dict[str, Any]) -> dict[str, Any]:
    """전략 5: 볼린저밴드 평균회귀."""
    bb_lower = _ind("bollinger", field="lower", period=p["bbPeriod"], mult=p["bbMult"])
    bb_mid = _ind("bollinger", field="mid", period=p["bbPeriod"], mult=p["bbMult"])
    bb_width = _ind("bollinger", field="width", period=p["bbPeriod"], mult=p["bbMult"])
    return {
        "entry": _and(
            _cond(_ind("low"), "touched_within", bb_lower, bars=p["reentryBars"], tolerance_percent=0.0),
            _cond(_ind("close"), "crosses_above", bb_lower),
            _cond(_ind("close"), ">", _ind("ema", period=p["trendEmaPeriod"])),
            _cond(bb_width, ">=", _const(p["minBandWidthPct"])),
        ),
        "exit": _or(
            _cond(_ind("close"), ">=", bb_mid),
            _cond(_ind("close"), ">=", _ind("bollinger", field="upper", period=p["bbPeriod"], mult=p["bbMult"])),
        ),
        "risk": {
            "stopLossType": "atr", "stopLossValue": p["atrStopMult"],
            "takeProfitType": "none", "takeProfitValue": 0,
            "atrPeriod": p["atrPeriod"], "maxHoldBars": p["maxHoldBars"],
        },
    }


def donchian_breakout(p: dict[str, Any]) -> dict[str, Any]:
    """전략 6: 돈치안 돌파 — 채널은 현재 봉을 제외한 이전 N봉만 사용."""
    return {
        "entry": _and(
            _cond(_ind("close"), ">", _ind("donchian", field="upper", period=p["entryPeriod"])),
            _cond(_ind("relative_volume", period=p["volumeSmaPeriod"]), ">=", _const(p["minRelativeVolume"])),
            _cond(_ind("adx", period=p["adxPeriod"]), ">=", _const(p["minAdx"])),
        ),
        "exit": _or(
            _cond(_ind("close"), "<", _ind("donchian", field="lower", period=p["exitPeriod"])),
        ),
        "risk": {
            "stopLossType": "atr", "stopLossValue": p["atrStopMult"],
            "takeProfitType": "none", "takeProfitValue": 0,
            "trailingStopType": "atr", "trailingStopValue": p["atrTrailMult"],
            "atrPeriod": p["atrPeriod"], "maxHoldBars": p["maxHoldBars"],
        },
    }


def macd_trend(p: dict[str, Any]) -> dict[str, Any]:
    """전략 7: MACD 추세 전략."""
    macd_line = _ind("macd", field="macd", fast=p["macdFast"], slow=p["macdSlow"], signal=p["macdSignal"])
    signal_line = _ind("macd", field="signal", fast=p["macdFast"], slow=p["macdSlow"], signal=p["macdSignal"])
    hist = _ind("macd", field="histogram", fast=p["macdFast"], slow=p["macdSlow"], signal=p["macdSignal"])
    return {
        "entry": _and(
            _cond(macd_line, "crosses_above", signal_line),
            _cond(hist, "rising_for", _const(p["histRisingBars"]), bars=p["histRisingBars"]),
            _cond(_ind("close"), ">", _ind("ema", period=p["trendEmaPeriod"])),
        ),
        "exit": _or(
            _cond(macd_line, "crosses_below", signal_line),
            _cond(hist, "falling_for", _const(p["histFallingBars"]), bars=p["histFallingBars"]),
        ),
        "risk": {
            "stopLossType": "atr", "stopLossValue": p["atrStopMult"],
            "takeProfitType": "atr", "takeProfitValue": p["atrTakeMult"],
            "atrPeriod": p["atrPeriod"], "maxHoldBars": p["maxHoldBars"],
        },
    }


# template id -> (builder, korean name, default params)
TEMPLATES: dict[str, dict[str, Any]] = {
    "vwap_pullback": {
        "builder": vwap_pullback,
        "name": "VWAP 눌림매수",
        "defaults": {
            "emaFast": 20, "emaSlow": 50, "vwapAnchor": "utc_day",
            "pullbackBars": 5, "pullbackTolerancePct": 0.3,
            "volumeSmaPeriod": 20, "volumeMult": 1.2,
            "rsiPeriod": 14, "rsiMin": 45, "rsiMax": 70,
            "atrPeriod": 14, "atrStopMult": 1.0, "atrTakeMult": 1.8, "maxHoldBars": 48,
        },
    },
    "ema_pullback": {
        "builder": ema_pullback,
        "name": "EMA 눌림매수",
        "defaults": {
            "emaFast": 20, "emaSlow": 50,
            "pullbackBars": 3, "pullbackTolerancePct": 0.2,
            "rsiPeriod": 14, "rsiMin": 40, "rsiMax": 70,
            "atrPeriod": 14, "atrStopMult": 1.2, "atrTakeMult": 2.0, "maxHoldBars": 72,
        },
    },
    "ema_golden_cross": {
        "builder": ema_golden_cross,
        "name": "EMA 골든크로스",
        "defaults": {
            "emaFast": 20, "emaSlow": 50, "htf": "60m", "htfEmaPeriod": 50,
            "volumeSmaPeriod": 20, "minRelativeVolume": 1.0,
            "atrPeriod": 14, "atrStopMult": 1.5, "atrTakeMult": 3.0, "maxHoldBars": 288,
        },
    },
    "rsi_trend_rebound": {
        "builder": rsi_trend_rebound,
        "name": "RSI 추세 필터 반등",
        "defaults": {
            "rsiPeriod": 14, "rsiOversold": 30, "rsiExit": 60,
            "trendEmaPeriod": 200, "useBollingerReentry": False, "bbPeriod": 20, "bbMult": 2.0,
            "atrPeriod": 14, "atrStopMult": 1.2, "atrTakeMult": 2.0, "maxHoldBars": 96,
        },
    },
    "bollinger_mean_reversion": {
        "builder": bollinger_mean_reversion,
        "name": "볼린저밴드 평균회귀",
        "defaults": {
            "bbPeriod": 20, "bbMult": 2.0, "reentryBars": 3,
            "trendEmaPeriod": 200, "minBandWidthPct": 1.0,
            "atrPeriod": 14, "atrStopMult": 1.5, "maxHoldBars": 96,
        },
    },
    "donchian_breakout": {
        "builder": donchian_breakout,
        "name": "돈치안 돌파",
        "defaults": {
            "entryPeriod": 20, "exitPeriod": 10,
            "volumeSmaPeriod": 20, "minRelativeVolume": 1.2,
            "adxPeriod": 14, "minAdx": 20,
            "atrPeriod": 14, "atrStopMult": 1.5, "atrTrailMult": 2.0, "maxHoldBars": 288,
        },
    },
    "macd_trend": {
        "builder": macd_trend,
        "name": "MACD 추세 전략",
        "defaults": {
            "macdFast": 12, "macdSlow": 26, "macdSignal": 9,
            "histRisingBars": 2, "histFallingBars": 3, "trendEmaPeriod": 100,
            "atrPeriod": 14, "atrStopMult": 1.5, "atrTakeMult": 2.5, "maxHoldBars": 288,
        },
    },
}


def build_strategy_definition(template: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if template not in TEMPLATES:
        raise ValueError(f"unknown template: {template}")
    spec = TEMPLATES[template]
    merged = {**spec["defaults"], **(params or {})}
    body = spec["builder"](merged)
    return {
        "name": spec["name"],
        "version": 1,
        "marketType": "spot",
        "direction": "long",
        "template": template,
        "params": merged,
        **body,
    }
