from decimal import Decimal

import pytest

from arbibot.core.events import DecisionAction, DecisionRecord, OrderEvent, OrderStatus
from arbibot.ops.metrics import (
    DECISIONS_TOTAL,
    GATE_BLOCKS_TOTAL,
    ORDER_EVENTS_TOTAL,
    ORDERS_FILLED_TOTAL,
    ORDERS_PARTIALLY_FILLED_TOTAL,
    ORDERS_REJECTED_TOTAL,
    TRADE_DECISIONS_TOTAL,
    MetricsRegistry,
    record_decision_metrics,
    record_order_event_metrics,
    record_replay_summary_metrics,
    record_risk_state_metrics,
)
from arbibot.replay.summary import ReplaySummary
from arbibot.risk.engine import RiskEngineState


def test_counter_gauge_histogram_and_labels() -> None:
    m = MetricsRegistry()
    m.increment("x")
    m.increment("x", 2)
    assert m.get_counter("x") == 3
    with pytest.raises(ValueError):
        m.increment("x", -4)

    m.set_gauge("g", 10)
    assert m.get_gauge("g") == 10

    m.observe("h", 2)
    m.observe("h", 4)
    hist = m.get_histogram("h")
    assert hist["count"] == 2
    assert hist["min"] == 2
    assert hist["max"] == 4
    assert hist["sum"] == 6
    assert hist["average"] == 3

    m.increment("lbl", labels={"b": 2, "a": 1})
    m.increment("lbl", labels={"a": 1, "b": 2})
    assert m.get_counter("lbl", labels={"a": 1, "b": 2}) == 2


def test_snapshot_deterministic() -> None:
    m = MetricsRegistry()
    m.increment("z", labels={"b": 1, "a": 2})
    s1 = m.snapshot()
    s2 = m.snapshot()
    assert s1 == s2


def test_integration_helpers() -> None:
    m = MetricsRegistry()
    d_trade = DecisionRecord(
        event_id="d1", source="x", source_ts_ms=1, recv_wall_ts_ms=2, recv_monotonic_ns=3,
        action=DecisionAction.TRADE,
    )
    d_no = DecisionRecord(
        event_id="d2", source="x", source_ts_ms=1, recv_wall_ts_ms=2, recv_monotonic_ns=3,
        action=DecisionAction.NO_TRADE, reasons=["A", "B"],
    )
    record_decision_metrics(m, d_trade)
    record_decision_metrics(m, d_no)
    assert m.get_counter(DECISIONS_TOTAL) == 2
    assert m.get_counter(TRADE_DECISIONS_TOTAL) == 1
    assert m.get_counter(GATE_BLOCKS_TOTAL, labels={"reason": "A"}) == 1

    for status in [OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED, OrderStatus.REJECTED]:
        record_order_event_metrics(
            m,
            OrderEvent(
                event_id=f"o{status.value}", source="x", source_ts_ms=1, recv_wall_ts_ms=2,
                recv_monotonic_ns=3, order_id="oid", status=status,
            ),
        )
    assert m.get_counter(ORDER_EVENTS_TOTAL) == 3
    assert m.get_counter(ORDERS_FILLED_TOTAL) == 1
    assert m.get_counter(ORDERS_PARTIALLY_FILLED_TOTAL) == 1
    assert m.get_counter(ORDERS_REJECTED_TOTAL) == 1

    rs = ReplaySummary(total_events=5, malformed_events=1, unknown_events=2, decisions_total=3)
    record_replay_summary_metrics(m, rs)
    state = RiskEngineState(realized_daily_pnl=Decimal("1"), unknown_order_state=True)
    record_risk_state_metrics(m, state)
    assert m.get_gauge("realized_daily_pnl") == 1.0
