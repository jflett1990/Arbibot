from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arbibot.core.events import DecisionRecord, FeatureSnapshot
from arbibot.market.book import LocalOrderBook
from arbibot.model.fair_price import FairPriceResult
from arbibot.opportunity.edge import EdgeInput, EdgeResult, OutcomeSide, calculate_edge
from arbibot.opportunity.gates import (
    TradeGateConfig,
    TradeGateInput,
    TradeGateResult,
    apply_trade_gates,
    build_decision_record,
)


@dataclass(frozen=True, slots=True)
class OpportunityDecision:
    edge_result: EdgeResult | None
    gate_result: TradeGateResult
    decision_record: DecisionRecord


def executable_price_from_book(book: LocalOrderBook, target_size: Decimal) -> Decimal | None:
    return book.weighted_avg_price("ask", target_size)


class OpportunityDetector:
    def __init__(self, gate_config: TradeGateConfig | None = None) -> None:
        self.gate_config = gate_config or TradeGateConfig()

    def detect(
        self,
        fair_price: FairPriceResult,
        order_book: LocalOrderBook,
        feature_snapshot: FeatureSnapshot,
        target_size: Decimal,
        outcome_side: OutcomeSide,
        seconds_to_expiry: Decimal,
        confidence: Decimal | None = None,
        conflict: Decimal | None = None,
        fee_cost: Decimal = Decimal("0"),
        slippage_cost: Decimal = Decimal("0"),
        latency_risk: Decimal = Decimal("0"),
        queue_uncertainty: Decimal = Decimal("0"),
        model_error_buffer: Decimal = Decimal("0"),
    ) -> OpportunityDecision:
        executable = executable_price_from_book(order_book, target_size)
        spread = order_book.spread()
        ask_depth3 = order_book.depth("ask", levels=3)
        depth_ratio = None if target_size <= 0 else ask_depth3 / target_size

        edge_result: EdgeResult | None = None
        if executable is not None:
            edge_result = calculate_edge(
                EdgeInput(
                    outcome_side=outcome_side,
                    fair_up_probability=fair_price.fair_up_probability,
                    fair_down_probability=fair_price.fair_down_probability,
                    executable_price=executable,
                    target_size=target_size,
                    fee_cost=fee_cost,
                    slippage_cost=slippage_cost,
                    spread_cost=Decimal("0") if spread is None else spread,
                    latency_risk=latency_risk,
                    queue_uncertainty=queue_uncertainty,
                    model_error_buffer=model_error_buffer,
                )
            )

        gate_result = apply_trade_gates(
            TradeGateInput(
                edge_result=edge_result,
                feature_snapshot=feature_snapshot,
                book_spread=spread,
                depth_ratio=depth_ratio,
                seconds_to_expiry=seconds_to_expiry,
                confidence=confidence,
                conflict=conflict,
            ),
            self.gate_config,
        )
        decision_record = build_decision_record(
            gate_result,
            event_id=f"decision:{feature_snapshot.symbol}:{feature_snapshot.source_ts_ms}",
            source_ts_ms=feature_snapshot.source_ts_ms,
            recv_wall_ts_ms=feature_snapshot.recv_wall_ts_ms,
            recv_monotonic_ns=feature_snapshot.recv_monotonic_ns,
            metadata={"outcome_side": outcome_side.value},
        )
        return OpportunityDecision(
            edge_result=edge_result, gate_result=gate_result, decision_record=decision_record
        )
