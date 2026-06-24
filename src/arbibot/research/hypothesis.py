from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class HypothesisKind(StrEnum):
    IMPULSE_LAG = "impulse_lag"
    ORDER_BOOK_DISLOCATION = "order_book_dislocation"
    SPREAD_COMPRESSION = "spread_compression"
    EXTERNAL_SIGNAL_CONFIRMATION = "external_signal_confirmation"
    CUSTOM = "custom"


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str | None = None
    end: str | None = None


class ResearchHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    kind: HypothesisKind
    description: str
    market_scope: dict[str, Any] = Field(default_factory=dict)
    time_window: TimeWindow = Field(default_factory=TimeWindow)
    entry_conditions: dict[str, Any] = Field(default_factory=dict)
    exit_conditions: dict[str, Any] = Field(default_factory=dict)
    feature_requirements: dict[str, Any] = Field(default_factory=dict)
    cost_assumptions: dict[str, Any] = Field(default_factory=dict)
    risk_gates: dict[str, Any] = Field(default_factory=dict)
    promotion_criteria: dict[str, Any] = Field(default_factory=dict)
    rejection_criteria: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""

    @field_validator("id", "name", "description")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value


def slugify(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    if not slug:
        raise ValueError("slug must contain at least one alphanumeric character")
    return slug


def default_hypothesis(
    name: str, kind: HypothesisKind = HypothesisKind.IMPULSE_LAG
) -> ResearchHypothesis:
    slug = slugify(name)
    return ResearchHypothesis(
        id=slug,
        name=name,
        kind=kind,
        description=(
            "Polymarket BTC UP/DOWN 5-minute markets lag Binance BTCUSDT movement "
            "after sharp 30-second impulse candles."
        ),
        market_scope={"symbol": "BTCUSDT", "venue": "polymarket", "market_type": "btc_up_down_5m"},
        time_window=TimeWindow(),
        entry_conditions={"impulse_window_ms": 30_000, "impulse_threshold_bps": 10.0},
        exit_conditions={"max_hold_ms": 300_000},
        feature_requirements={"top_n_levels": 3, "required_sources": ["binance", "polymarket"]},
        cost_assumptions={"fee_bps": 0.0, "slippage_bps": 0.0, "latency_ms": 250},
        risk_gates={
            "max_spread_bps": 500.0,
            "min_liquidity": 1.0,
            "max_book_age_ms": 1_000,
            "min_raw_edge_bps": 1.0,
            "min_cost_adjusted_edge_bps": 0.0,
            "max_latency_ms": 1_000,
            "required_both_sides_present": True,
        },
        promotion_criteria={"min_passing_rows": 10, "min_median_cost_adjusted_edge_bps": 1.0},
        rejection_criteria={"max_passing_rows": 0},
        notes="Template generated for deterministic replay research; not a live trading config.",
    )


def load_hypothesis(path: str | Path) -> ResearchHypothesis:
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ResearchHypothesis.model_validate(data)


def write_hypothesis_template(name: str, out_dir: str | Path, kind: HypothesisKind) -> Path:
    hyp = default_hypothesis(name, kind)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{hyp.id}.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(hyp.model_dump(mode="json"), f, sort_keys=False)
    return path
