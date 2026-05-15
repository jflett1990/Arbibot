"""Config loader and typed application config models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from arbibot.core.errors import ConfigError


class MarketConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    no_trade_final_seconds: int
    require_market_metadata: bool


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_per_trade_pct: float
    daily_loss_cap_pct: float
    hard_stop_pct: float
    max_market_exposure_pct: float
    max_open_orders: int
    max_daily_traded_notional_pct: float


class EdgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_net_edge: float
    model_error_buffer: float
    spread_penalty_multiplier: float


class LiquidityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_spread: float
    min_depth_ratio: float


class LatencyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_binance_event_age_ms: int
    max_polymarket_event_age_ms: int
    max_order_ack_p95_ms: int


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sqlite_path: str


class PaperLatencyInjectConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_delay: int
    decision_delay: int
    order_submit_delay: int
    cancel_delay: int


class PaperConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pessimistic_fills: bool
    inject_latency_ms: PaperLatencyInjectConfig


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    mode: Literal["paper", "live"]
    live_trading_enabled: bool = False
    symbol: str | None = None
    market: MarketConfig | None = None
    risk: RiskConfig | None = None
    edge: EdgeConfig | None = None
    liquidity: LiquidityConfig | None = None
    latency: LatencyConfig | None = None
    storage: StorageConfig | None = None
    paper: PaperConfig | None = None
    pilot_mode: bool | None = None
    startup_requires_confirmation: bool | None = None
    max_order_size_usd: float | int | None = None
    kill_switch_required: bool | None = None

    @classmethod
    def model_validate_with_defaults(cls, data: dict[str, Any]) -> AppConfig:
        if "live_trading_enabled" not in data:
            data["live_trading_enabled"] = False
        return cls.model_validate(data)


def load_config(path: str | Path) -> AppConfig:
    """Load and validate YAML config from disk."""
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Unable to read config file: {config_path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in config file: {config_path}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"Config root must be a mapping: {config_path}")

    return AppConfig.model_validate_with_defaults(raw)
