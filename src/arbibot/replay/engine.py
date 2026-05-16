from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ValidationError

from arbibot.core.events import (
    DecisionAction,
    DecisionRecord,
    ExternalSignal,
    FeatureSnapshot,
    OrderEvent,
    OrderIntent,
    PolyBookDelta,
    PolyBookSnapshot,
    PolyTrade,
    SpotBar,
    SpotTick,
)
from arbibot.execution.interfaces import ExecutionSide, OrderType
from arbibot.execution.paper import PaperExecutionEngine
from arbibot.features.feature_snapshot import build_feature_snapshot
from arbibot.features.spot import SpotFeatureWindow
from arbibot.market.book import LocalOrderBook
from arbibot.market.candles import CandleBuilder
from arbibot.model.fair_price import estimate_from_feature_snapshot
from arbibot.opportunity.detector import OpportunityDetector
from arbibot.opportunity.edge import OutcomeSide
from arbibot.replay.latency_model import LatencyConfig, adjusted_event_time, apply_delay_ms
from arbibot.replay.summary import ReplaySummary
from arbibot.storage.event_store import EventStore, StoredEvent


@dataclass(frozen=True, slots=True)
class ReplayConfig:
    symbol: str = "BTCUSDT"
    interval_ms: int = 300_000
    allowed_lateness_ms: int = 1_000
    strict_deserialization: bool = False
    evaluate_opportunities: bool = False
    paper_execute: bool = False
    threshold_price: Decimal | None = None
    seconds_to_expiry: Decimal | None = None
    target_size: Decimal = Decimal("1")
    outcome_side: OutcomeSide | None = None
    stale_spot_after_ms: int = 750
    stale_book_after_ms: int = 1000
    fee_cost: Decimal = Decimal("0")
    slippage_cost: Decimal = Decimal("0")
    latency_risk: Decimal = Decimal("0")
    queue_uncertainty: Decimal = Decimal("0")
    model_error_buffer: Decimal = Decimal("0.005")

    def __post_init__(self) -> None:
        if self.interval_ms <= 0:
            raise ValueError("interval_ms must be positive")
        if self.allowed_lateness_ms < 0:
            raise ValueError("allowed_lateness_ms must be >= 0")
        if self.target_size <= 0:
            raise ValueError("target_size must be positive")
        if self.evaluate_opportunities and (
            self.threshold_price is None
            or self.seconds_to_expiry is None
            or self.outcome_side is None
        ):
            raise ValueError(
                "opportunity evaluation requires "
                "threshold_price, seconds_to_expiry, outcome_side"
            )
        if self.paper_execute and not self.evaluate_opportunities:
            raise ValueError("paper_execute requires evaluate_opportunities=True")


@dataclass(frozen=True, slots=True)
class ReplayResult:
    summary: ReplaySummary
    candles: list[SpotBar]
    feature_snapshots: list[FeatureSnapshot]
    decisions: list[DecisionRecord]
    order_events: list[OrderEvent]


_EVENT_MODELS: dict[str, type[BaseModel]] = {
    "SpotTick": SpotTick,
    "SpotBar": SpotBar,
    "PolyBookSnapshot": PolyBookSnapshot,
    "PolyBookDelta": PolyBookDelta,
    "PolyTrade": PolyTrade,
    "ExternalSignal": ExternalSignal,
    "DecisionRecord": DecisionRecord,
    "OrderEvent": OrderEvent,
}


class ReplayEngine:
    def __init__(
        self,
        store: EventStore,
        config: ReplayConfig,
        latency: LatencyConfig | None = None,
    ) -> None:
        self.store = store
        self.config = config
        self.latency = latency or LatencyConfig()

    def run(self) -> ReplayResult:
        summary = ReplaySummary()
        spot = SpotFeatureWindow(self.config.symbol)
        candles_builder = CandleBuilder(self.config.interval_ms, self.config.allowed_lateness_ms)
        detector = OpportunityDetector()
        paper = PaperExecutionEngine()
        books: dict[str, LocalOrderBook] = {}
        active_token: str | None = None

        candles: list[SpotBar] = []
        snapshots: list[FeatureSnapshot] = []
        decisions: list[DecisionRecord] = []
        orders: list[OrderEvent] = []

        for idx, stored in enumerate(self.store.iter_events()):
            summary.total_events += 1
            event = self._deserialize(stored, summary)
            if event is None:
                continue
            summary.deserialized_events += 1

            if isinstance(event, SpotTick):
                summary.spot_ticks += 1
                spot.add_tick(event)
                candles.extend(candles_builder.add_tick(event))
                book = books.get(active_token) if active_token else None
                source_ts = adjusted_event_time(event.source_ts_ms, self.latency.data_delay_ms)
                snapshot = build_feature_snapshot(
                    symbol=self.config.symbol,
                    spot_window=spot,
                    order_book=book,
                    now_source_ts_ms=source_ts,
                    recv_wall_ts_ms=event.recv_wall_ts_ms,
                    recv_monotonic_ns=event.recv_monotonic_ns,
                    stale_spot_after_ms=self.config.stale_spot_after_ms,
                    stale_book_after_ms=self.config.stale_book_after_ms,
                )
                snapshots.append(snapshot)
                summary.feature_snapshots += 1

                if self.config.evaluate_opportunities:
                    decision = self._evaluate(snapshot, detector, book, idx)
                    decisions.append(decision)
                    summary.decisions_total += 1
                    if decision.action is DecisionAction.TRADE:
                        summary.decisions_trade += 1
                    else:
                        summary.decisions_no_trade += 1
                    if book is None:
                        summary.skipped_no_book += 1

                    if (
                        self.config.paper_execute
                        and decision.action is DecisionAction.TRADE
                        and book is not None
                    ):
                        order_intent = self._build_order_intent(decision, book.token_id)
                        for order in paper.execute_buy(order_intent, book):
                            orders.append(order)
                            summary.order_events_total += 1
                            if order.status.value == "FILLED":
                                summary.orders_filled += 1
                            elif order.status.value == "PARTIALLY_FILLED":
                                summary.orders_partially_filled += 1
                            elif order.status.value == "REJECTED":
                                summary.orders_rejected += 1
                            elif order.status.value == "CANCELLED":
                                summary.orders_cancelled += 1
                                if order.reason in {
                                    "NO_FILL",
                                    "FOK_INSUFFICIENT_DEPTH",
                                    "FAK_PARTIAL_DISABLED",
                                }:
                                    summary.orders_expired_or_no_fill += 1

            elif isinstance(event, SpotBar):
                summary.spot_bars_input += 1
            elif isinstance(event, PolyBookSnapshot):
                summary.book_snapshots += 1
                token = event.token_id or ""
                book = LocalOrderBook(token)
                book.apply_snapshot(event)
                books[token] = book
                active_token = token
            elif isinstance(event, PolyBookDelta):
                summary.book_deltas += 1
                token = event.token_id or ""
                if token not in books:
                    summary.orphan_book_deltas += 1
                    continue
                books[token].apply_delta(event)
                active_token = token
            elif isinstance(event, PolyTrade):
                summary.poly_trades += 1
            elif isinstance(event, ExternalSignal):
                summary.external_signals += 1

        flushed = candles_builder.flush(finalize_all=True)
        candles.extend(flushed)
        summary.candles_emitted = len(candles)
        return ReplayResult(summary, candles, snapshots, decisions, orders)

    def _deserialize(
        self,
        stored: StoredEvent,
        summary: ReplaySummary,
    ) -> BaseModel | None:
        model = _EVENT_MODELS.get(stored.event_type)
        if model is None:
            if self.config.strict_deserialization:
                raise ValueError(f"Unknown event type: {stored.event_type}")
            summary.unknown_events += 1
            return None
        try:
            payload = json.loads(stored.payload_json)
            return model.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            if self.config.strict_deserialization:
                raise
            summary.malformed_events += 1
            return None

    def _evaluate(
        self,
        snapshot: FeatureSnapshot,
        detector: OpportunityDetector,
        book: LocalOrderBook | None,
        idx: int,
    ) -> DecisionRecord:
        eid = f"replay_decision:{snapshot.source_ts_ms}:{idx}"
        if book is None:
            return DecisionRecord(
                event_id=eid,
                source="arbibot.replay",
                source_ts_ms=apply_delay_ms(snapshot.source_ts_ms, self.latency.decision_delay_ms),
                recv_wall_ts_ms=snapshot.recv_wall_ts_ms,
                recv_monotonic_ns=snapshot.recv_monotonic_ns,
                action=DecisionAction.NO_TRADE,
                reasons=["NO_ACTIVE_BOOK"],
                metadata={"replay": True},
            )
        threshold_price = self.config.threshold_price
        seconds_to_expiry = self.config.seconds_to_expiry
        outcome_side = self.config.outcome_side
        assert threshold_price is not None
        assert seconds_to_expiry is not None
        assert outcome_side is not None

        fair = estimate_from_feature_snapshot(
            snapshot,
            threshold_price=threshold_price,
            seconds_to_expiry=seconds_to_expiry,
        )
        result = detector.detect(
            fair_price=fair,
            order_book=book,
            feature_snapshot=snapshot,
            target_size=self.config.target_size,
            outcome_side=outcome_side,
            seconds_to_expiry=seconds_to_expiry,
            fee_cost=self.config.fee_cost,
            slippage_cost=self.config.slippage_cost,
            latency_risk=self.config.latency_risk,
            queue_uncertainty=self.config.queue_uncertainty,
            model_error_buffer=self.config.model_error_buffer,
        )
        return result.decision_record.model_copy(update={"event_id": eid})

    def _build_order_intent(self, decision: DecisionRecord, token_id: str) -> OrderIntent:
        cid = f"paper:{decision.event_id}"
        return OrderIntent(
            event_id=f"intent:{decision.event_id}",
            source="arbibot.replay",
            source_ts_ms=apply_delay_ms(decision.source_ts_ms, self.latency.order_submit_delay_ms),
            recv_wall_ts_ms=decision.recv_wall_ts_ms,
            recv_monotonic_ns=decision.recv_monotonic_ns,
            side=ExecutionSide.BUY.value,
            client_order_id=cid,
            token_id=token_id,
            order_type=OrderType.FAK.value,
            price_limit=decision.executable_price,
            size=float(self.config.target_size),
        )
