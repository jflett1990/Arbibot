from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arbibot.core.events import DecisionAction, DecisionRecord, FeatureSnapshot
from arbibot.opportunity.edge import EdgeResult

MISSING_EDGE = "MISSING_EDGE"
EDGE_TOO_SMALL = "EDGE_TOO_SMALL"
STALE_SPOT = "STALE_SPOT"
STALE_BOOK = "STALE_BOOK"
SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
LOW_LIQUIDITY = "LOW_LIQUIDITY"
TOO_CLOSE_TO_EXPIRY = "TOO_CLOSE_TO_EXPIRY"
LOW_CONFIDENCE = "LOW_CONFIDENCE"
HIGH_CONFLICT = "HIGH_CONFLICT"
RISK_BLOCKED = "RISK_BLOCKED"
UNKNOWN_ORDER_STATE = "UNKNOWN_ORDER_STATE"
DAILY_LOSS_CAP = "DAILY_LOSS_CAP"
HEALTH_BLOCKED = "HEALTH_BLOCKED"


@dataclass(frozen=True, slots=True)
class TradeGateConfig:
    min_net_edge: Decimal = Decimal("0.015")
    max_spread: Decimal = Decimal("0.03")
    min_depth_ratio: Decimal = Decimal("3.0")
    max_spot_age_ms: int = 750
    max_book_age_ms: int = 1000
    no_trade_final_seconds: int = 15
    max_conflict: Decimal = Decimal("0.35")
    min_confidence: Decimal = Decimal("0.50")

    def __post_init__(self) -> None:
        if self.min_net_edge < 0 or self.max_spread <= 0 or self.min_depth_ratio <= 0:
            raise ValueError("invalid edge/spread/depth config")
        if self.max_spot_age_ms <= 0 or self.max_book_age_ms <= 0:
            raise ValueError("age thresholds must be > 0")
        if self.no_trade_final_seconds < 0:
            raise ValueError("no_trade_final_seconds must be >= 0")
        if self.max_conflict < 0 or self.max_conflict > 1:
            raise ValueError("max_conflict must be within [0,1]")
        if self.min_confidence < 0 or self.min_confidence > 1:
            raise ValueError("min_confidence must be within [0,1]")


@dataclass(frozen=True, slots=True)
class TradeGateInput:
    edge_result: EdgeResult | None
    feature_snapshot: FeatureSnapshot | None
    book_spread: Decimal | None
    depth_ratio: Decimal | None
    seconds_to_expiry: int | Decimal
    confidence: Decimal | None = None
    conflict: Decimal | None = None
    risk_blocked: bool = False
    unknown_order_state: bool = False
    daily_loss_cap_reached: bool = False
    health_blocked: bool = False


@dataclass(frozen=True, slots=True)
class TradeGateResult:
    action: DecisionAction
    should_trade: bool
    reasons: list[str]
    edge_result: EdgeResult | None


def apply_trade_gates(input: TradeGateInput, config: TradeGateConfig) -> TradeGateResult:
    reasons: list[str] = []
    if input.edge_result is None:
        reasons.append(MISSING_EDGE)
    elif input.edge_result.net_edge < config.min_net_edge:
        reasons.append(EDGE_TOO_SMALL)

    fs = input.feature_snapshot
    if fs is None or fs.stale_spot is True:
        reasons.append(STALE_SPOT)
    if fs is None or fs.stale_book is True:
        reasons.append(STALE_BOOK)

    if input.book_spread is None or input.book_spread > config.max_spread:
        reasons.append(SPREAD_TOO_WIDE)
    if input.depth_ratio is None or input.depth_ratio < config.min_depth_ratio:
        reasons.append(LOW_LIQUIDITY)
    if Decimal(str(input.seconds_to_expiry)) <= Decimal(config.no_trade_final_seconds):
        reasons.append(TOO_CLOSE_TO_EXPIRY)

    if input.confidence is not None and input.confidence < config.min_confidence:
        reasons.append(LOW_CONFIDENCE)
    if input.conflict is not None and input.conflict > config.max_conflict:
        reasons.append(HIGH_CONFLICT)
    if input.risk_blocked:
        reasons.append(RISK_BLOCKED)
    if input.unknown_order_state:
        reasons.append(UNKNOWN_ORDER_STATE)
    if input.daily_loss_cap_reached:
        reasons.append(DAILY_LOSS_CAP)
    if input.health_blocked:
        reasons.append(HEALTH_BLOCKED)

    should_trade = len(reasons) == 0
    return TradeGateResult(
        action=DecisionAction.TRADE if should_trade else DecisionAction.NO_TRADE,
        should_trade=should_trade,
        reasons=reasons,
        edge_result=input.edge_result,
    )


def build_decision_record(
    gate_result: TradeGateResult,
    event_id: str,
    source_ts_ms: int,
    recv_wall_ts_ms: int,
    recv_monotonic_ns: int,
    metadata: dict[str, str | int | float | bool | None] | None = None,
) -> DecisionRecord:
    edge = gate_result.edge_result
    return DecisionRecord(
        event_id=event_id,
        source="arbibot.opportunity_detector",
        source_ts_ms=source_ts_ms,
        recv_wall_ts_ms=recv_wall_ts_ms,
        recv_monotonic_ns=recv_monotonic_ns,
        action=gate_result.action,
        reasons=list(gate_result.reasons),
        metadata=metadata,
        net_edge=None if edge is None else float(edge.net_edge),
        gross_edge=None if edge is None else float(edge.gross_edge),
        outcome_side=None if edge is None else edge.outcome_side.value,
        executable_price=None if edge is None else float(edge.executable_price),
        fair_probability=None if edge is None else float(edge.fair_probability),
        target_size=None if edge is None else float(edge.target_size),
    )
