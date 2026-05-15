"""Canonical typed event schemas for Arbibot."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MarketSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class BookSide(StrEnum):
    BID = "BID"
    ASK = "ASK"


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




class BookLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float
    size: float

    @field_validator("price")
    @classmethod
    def validate_price_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("price must be > 0")
        return value

    @field_validator("size")
    @classmethod
    def validate_size_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("size must be >= 0")
        return value


def _coerce_book_levels(
    raw: list[BookLevel | list[float] | list[str] | tuple[float, float] | tuple[str, str]],
) -> list[BookLevel]:
    levels: list[BookLevel] = []
    for item in raw:
        if isinstance(item, BookLevel):
            levels.append(item)
            continue
        if isinstance(item, (list, tuple)) and len(item) == 2:
            levels.append(BookLevel(price=float(item[0]), size=float(item[1])))
            continue
        if isinstance(item, dict) and "price" in item and "size" in item:
            levels.append(BookLevel(price=float(item["price"]), size=float(item["size"])))
            continue
        raise ValueError("book level must be BookLevel, [price, size], or dict")
    return levels


class PolyBookSnapshot(BaseEvent):
    market_id: str
    outcome: str
    token_id: str | None = None
    tick_size: float | None = None
    bids: list[BookLevel] = Field(default_factory=list)
    asks: list[BookLevel] = Field(default_factory=list)

    @field_validator("bids", "asks", mode="before")
    @classmethod
    def validate_levels(cls, value: object) -> list[BookLevel]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("levels must be a list")
        return _coerce_book_levels(value)


class PolyBookDelta(BaseEvent):
    market_id: str
    outcome: str
    token_id: str | None = None
    side: MarketSide | None = None
    book_side: BookSide | None = None
    price: float
    size: float
    tick_size: float | None = None


    @property
    def resolved_book_side(self) -> BookSide:
        if self.book_side is not None:
            return self.book_side
        if self.side is MarketSide.BUY:
            return BookSide.BID
        if self.side is MarketSide.SELL:
            return BookSide.ASK
        raise ValueError("PolyBookDelta requires book_side or side")


class SpotBookTicker(BaseEvent):
    symbol: str
    bid_price: float
    bid_size: float
    ask_price: float
    ask_size: float
    stream_event_type: str = "bookTicker"

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("symbol must not be empty")
        return value

    @field_validator("bid_price", "ask_price")
    @classmethod
    def validate_price(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("price must be > 0")
        return value

    @field_validator("bid_size", "ask_size")
    @classmethod
    def validate_size(cls, value: float) -> float:
        if value < 0:
            raise ValueError("size must be >= 0")
        return value


class PolyTrade(BaseEvent):
    market_id: str
    outcome: str
    side: MarketSide | None = None
    book_side: BookSide | None = None
    price: float
    size: float


class ExternalSignal(BaseEvent):
    provider: str
    direction: SignalDirection
    strength: float | None = None
    ttl_ms: int | None = None
    symbol: str | None = None
    signal_name: str | None = None
    timeframe: str | None = None
    expires_at_ms: int | None = None
    metadata: dict[str, str | int | float | bool | None] | None = None


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
    bull_score: float | None = None
    bear_score: float | None = None
    convergence: float | None = None


class OpportunityCandidate(BaseEvent):
    market_id: str
    outcome: str
    side: MarketSide | None = None
    book_side: BookSide | None = None
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
    realized_daily_pnl: float | None = None
    unrealized_pnl: float | None = None
    open_market_exposure: float | None = None
    open_orders: int | None = None
    daily_traded_notional: float | None = None
    unknown_order_state: bool | None = None
    kill_switch_active: bool | None = None
    disabled: bool | None = None
    disable_reasons: list[str] = Field(default_factory=list)


class HealthState(BaseEvent):
    status: HealthStatus
    reason: str | None = None
