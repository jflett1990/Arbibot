from __future__ import annotations

from dataclasses import dataclass

from arbibot.core.events import DecisionAction, DecisionRecord, OrderEvent, OrderStatus
from arbibot.replay.summary import ReplaySummary
from arbibot.risk.engine import RiskEngineState

EVENTS_TOTAL = "events_total"
MALFORMED_EVENTS_TOTAL = "malformed_events_total"
UNKNOWN_EVENTS_TOTAL = "unknown_events_total"
STALE_SPOT_TOTAL = "stale_spot_total"
STALE_BOOK_TOTAL = "stale_book_total"
DECISIONS_TOTAL = "decisions_total"
TRADE_DECISIONS_TOTAL = "trade_decisions_total"
NO_TRADE_DECISIONS_TOTAL = "no_trade_decisions_total"
GATE_BLOCKS_TOTAL = "gate_blocks_total"
ORDER_EVENTS_TOTAL = "order_events_total"
ORDERS_FILLED_TOTAL = "orders_filled_total"
ORDERS_PARTIALLY_FILLED_TOTAL = "orders_partially_filled_total"
ORDERS_REJECTED_TOTAL = "orders_rejected_total"
ORDER_LATENCY_MS = "order_latency_ms"
EVENT_AGE_MS = "event_age_ms"
PROCESSING_LATENCY_MS = "processing_latency_ms"
OPEN_ORDERS = "open_orders"
OPEN_MARKET_EXPOSURE = "open_market_exposure"
DAILY_TRADED_NOTIONAL = "daily_traded_notional"
REALIZED_DAILY_PNL = "realized_daily_pnl"
RISK_BLOCKS_TOTAL = "risk_blocks_total"


@dataclass(slots=True)
class _HistogramStats:
    count: int = 0
    min: float | None = None
    max: float | None = None
    sum: float = 0.0

    def observe(self, value: float) -> None:
        self.count += 1
        self.sum += value
        self.min = value if self.min is None else min(self.min, value)
        self.max = value if self.max is None else max(self.max, value)

    def as_dict(self) -> dict[str, float | int | None]:
        avg = None if self.count == 0 else self.sum / self.count
        return {
            "count": self.count,
            "min": self.min,
            "max": self.max,
            "sum": self.sum,
            "average": avg,
        }


MetricKey = tuple[str, tuple[tuple[str, str], ...]]


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[MetricKey, float] = {}
        self._gauges: dict[MetricKey, float] = {}
        self._histograms: dict[MetricKey, _HistogramStats] = {}

    def _key(
        self,
        name: str,
        labels: dict[str, object] | None = None,
    ) -> MetricKey:
        normalized = tuple(sorted((k, str(v)) for k, v in (labels or {}).items()))
        return name, normalized

    def increment(
        self,
        name: str,
        amount: int | float = 1,
        labels: dict[str, object] | None = None,
    ) -> None:
        key = self._key(name, labels)
        current = self._counters.get(key, 0.0)
        if current + amount < 0:
            raise ValueError("counter cannot be decremented below zero")
        self._counters[key] = current + float(amount)

    def set_gauge(
        self,
        name: str,
        value: int | float,
        labels: dict[str, object] | None = None,
    ) -> None:
        self._gauges[self._key(name, labels)] = float(value)

    def observe(
        self,
        name: str,
        value: int | float,
        labels: dict[str, object] | None = None,
    ) -> None:
        key = self._key(name, labels)
        hist = self._histograms.setdefault(key, _HistogramStats())
        hist.observe(float(value))

    def get_counter(self, name: str, labels: dict[str, object] | None = None) -> float:
        return self._counters.get(self._key(name, labels), 0.0)

    def get_gauge(
        self,
        name: str,
        labels: dict[str, object] | None = None,
    ) -> float | None:
        return self._gauges.get(self._key(name, labels))

    def get_histogram(
        self,
        name: str,
        labels: dict[str, object] | None = None,
    ) -> dict[str, float | int | None]:
        hist = self._histograms.get(self._key(name, labels), _HistogramStats())
        return hist.as_dict()

    def snapshot(self) -> dict[str, object]:
        def key_to_str(name: str, labels: tuple[tuple[str, str], ...]) -> str:
            if not labels:
                return name
            return f"{name}|" + ",".join(f"{k}={v}" for k, v in labels)

        counters = {key_to_str(k[0], k[1]): v for k, v in sorted(self._counters.items())}
        gauges = {key_to_str(k[0], k[1]): v for k, v in sorted(self._gauges.items())}
        histograms = {
            key_to_str(k[0], k[1]): v.as_dict() for k, v in sorted(self._histograms.items())
        }
        return {"counters": counters, "gauges": gauges, "histograms": histograms}


def record_decision_metrics(metrics: MetricsRegistry, decision_record: DecisionRecord) -> None:
    metrics.increment(DECISIONS_TOTAL)
    if decision_record.action is DecisionAction.TRADE:
        metrics.increment(TRADE_DECISIONS_TOTAL)
    else:
        metrics.increment(NO_TRADE_DECISIONS_TOTAL)
        for reason in decision_record.reasons:
            metrics.increment(GATE_BLOCKS_TOTAL, labels={"reason": reason})


def record_order_event_metrics(metrics: MetricsRegistry, order_event: OrderEvent) -> None:
    metrics.increment(ORDER_EVENTS_TOTAL)
    if order_event.status is OrderStatus.FILLED:
        metrics.increment(ORDERS_FILLED_TOTAL)
    elif order_event.status is OrderStatus.PARTIALLY_FILLED:
        metrics.increment(ORDERS_PARTIALLY_FILLED_TOTAL)
    elif order_event.status is OrderStatus.REJECTED:
        metrics.increment(ORDERS_REJECTED_TOTAL)


def record_replay_summary_metrics(metrics: MetricsRegistry, replay_summary: ReplaySummary) -> None:
    metrics.increment(EVENTS_TOTAL, replay_summary.total_events)
    metrics.increment(MALFORMED_EVENTS_TOTAL, replay_summary.malformed_events)
    metrics.increment(UNKNOWN_EVENTS_TOTAL, replay_summary.unknown_events)
    metrics.increment(DECISIONS_TOTAL, replay_summary.decisions_total)


def record_risk_state_metrics(metrics: MetricsRegistry, risk_state: RiskEngineState) -> None:
    metrics.set_gauge(OPEN_ORDERS, risk_state.open_orders)
    metrics.set_gauge(OPEN_MARKET_EXPOSURE, float(risk_state.open_market_exposure))
    metrics.set_gauge(DAILY_TRADED_NOTIONAL, float(risk_state.daily_traded_notional))
    metrics.set_gauge(REALIZED_DAILY_PNL, float(risk_state.realized_daily_pnl))
    if risk_state.unknown_order_state or risk_state.kill_switch_active or risk_state.disabled:
        metrics.increment(RISK_BLOCKS_TOTAL)
