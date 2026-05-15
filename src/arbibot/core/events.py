"""Canonical typed event schemas for Arbibot."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarketSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class SignalDirection(StrEnum):
    BULL = "BULL"
    BEAR = "BEAR"
    NEUTRAL = "NEUTRAL"


class DecisionAction(StrEnum):
    TRADE = "TRADE"
    NO_TRADE = "NO_TRADE"


class OrderStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"


class BaseEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    source: str
    source_ts_ms: int
    recv_wall_ts_ms: int
    recv_monotonic_ns: int
    sequence_id: str | None = None

    @field_validator("event_id", "source")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("source_ts_ms", "recv_wall_ts_ms", "recv_monotonic_ns")
    @classmethod
    def validate_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("value must be positive")
        return value


class SpotTick(BaseEvent):
    symbol: str
    price: float
    size: float | None = None
    trade_id: str | None = None
    stream_event_type: str | None = None


class SpotBar(BaseEvent):
    symbol: str
    interval_ms: int | None = None
    start_ts_ms: int | None = None
    end_ts_ms: int | None = None
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int | None = None


class PolyBookSnapshot(BaseEvent):
    market_id: str
    outcome: str
    token_id: str | None = None
    tick_size: float | None = None
    bids: list[list[float]] = Field(default_factory=list)
    asks: list[list[float]] = Field(default_factory=list)


class PolyBookDelta(BaseEvent):
    market_id: str
    outcome: str
    token_id: str | None = None
    side: MarketSide
    price: float
    size: float
    tick_size: float | None = None


class PolyTrade(BaseEvent):
    market_id: str
    outcome: str
    side: MarketSide
    price: float
    size: float


class ExternalSignal(BaseEvent):
    provider: str
    direction: SignalDirection
    strength: float | None = None
    ttl_ms: int | None = None


class FeatureSnapshot(BaseEvent):
    feature_set: str
    values: dict[str, float]
    symbol: str | None = None
    latest_price: float | None = None
    return_250ms: float | None = None
    return_500ms: float | None = None
    return_1s: float | None = None
    return_2s: float | None = None
    return_5s: float | None = None
    return_10s: float | None = None
    realized_vol_5s: float | None = None
    realized_vol_30s: float | None = None
    momentum_slope_5s: float | None = None
    acceleration_1s_2s: float | None = None
    book_best_bid: float | None = None
    book_best_ask: float | None = None
    book_mid: float | None = None
    book_spread: float | None = None
    book_depth_bid_3: float | None = None
    book_depth_ask_3: float | None = None
    book_imbalance_3: float | None = None
    book_is_crossed: bool | None = None
    book_is_empty: bool | None = None
    book_last_update_age_ms: int | None = None
    stale_spot: bool | None = None
    stale_book: bool | None = None


class SignalState(BaseEvent):
    direction: SignalDirection
    confidence: float
    conflict: float = 0.0


class OpportunityCandidate(BaseEvent):
    market_id: str
    outcome: str
    side: MarketSide
    fair_probability: float
    executable_price: float
    net_edge: float


class DecisionRecord(BaseEvent):
    action: DecisionAction
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool | None] | None = None
    net_edge: float | None = None
    gross_edge: float | None = None
    outcome_side: str | None = None
    executable_price: float | None = None
    fair_probability: float | None = None
    target_size: float | None = None
    market_id: str | None = None
    outcome: str | None = None


class OrderIntent(BaseEvent):
    market_id: str | None = None
    outcome: str | None = None
    side: MarketSide | str
    target_price: float | None = None
    quantity: float | None = None
    client_order_id: str | None = None
    token_id: str | None = None
    outcome_side: str | None = None
    order_type: str | None = None
    price_limit: float | None = None
    size: float | None = None
    metadata: dict[str, str | int | float | bool | None] | None = None


class OrderEvent(BaseEvent):
    order_id: str
    status: OrderStatus
    client_order_id: str | None = None
    token_id: str | None = None
    requested_size: float | None = None
    filled_size: float | None = None
    avg_fill_price: float | None = None
    remaining_size: float | None = None
    reason: str | None = None
    metadata: dict[str, str | int | float | bool | None] | None = None


class RiskState(BaseEvent):
    trading_allowed: bool
    reason: str | None = None


class HealthState(BaseEvent):
    status: HealthStatus
    reason: str | None = None
