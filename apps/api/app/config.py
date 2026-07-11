"""Application settings.

All tunable values (rate limits, default fees, paths) live here so they are
never hard-coded across the codebase.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class RateLimitPolicy(BaseModel):
    """Requests-per-second policy for one Upbit rate-limit group."""

    requests_per_second: float
    burst: int = 1


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="USL_", env_file=".env", extra="ignore")

    # Paths
    data_dir: Path = Path(__file__).resolve().parents[3] / "data"
    db_path: Path | None = None  # defaults to <data_dir>/meta.sqlite3

    upbit_base_url: str = "https://api.upbit.com"

    # Upbit public quotation API limits (see docs.upbit.com; subject to change,
    # which is why they are settings and not constants).
    rate_limit_quotation_market: RateLimitPolicy = RateLimitPolicy(requests_per_second=10)
    rate_limit_quotation_candle: RateLimitPolicy = RateLimitPolicy(requests_per_second=10)

    http_timeout_seconds: float = 10.0
    max_retries: int = 5
    backoff_base_seconds: float = 0.5
    backoff_max_seconds: float = 30.0

    # Backtest defaults (user-overridable per request)
    default_fee_rate: float = 0.0005  # Upbit KRW spot 0.05%
    default_slippage_rate: float = 0.0005
    default_initial_capital: float = 10_000_000.0
    default_min_order_krw: float = 5_000.0

    # Optimization
    optimization_max_combinations: int = 500
    optimization_max_workers: int = 4

    # Warnings
    min_trades_for_confidence: int = 20
    synthetic_candle_warn_ratio: float = 0.2

    @property
    def candle_dir(self) -> Path:
        return self.data_dir / "candles"

    @property
    def sqlite_path(self) -> Path:
        return self.db_path or (self.data_dir / "meta.sqlite3")


settings = Settings()
