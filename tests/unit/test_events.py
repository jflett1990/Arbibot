import pytest
from pydantic import ValidationError

from arbibot.core.events import (
    DecisionAction,
    DecisionRecord,
    HealthState,
    HealthStatus,
    OrderEvent,
    OrderStatus,
    SpotTick,
)


def _base_payload() -> dict[str, object]:
    return {
        "event_id": "evt-1",
        "source": "binance",
        "source_ts_ms": 1000,
        "recv_wall_ts_ms": 1010,
        "recv_monotonic_ns": 10,
    }


def test_spot_tick_roundtrip() -> None:
    tick = SpotTick(**_base_payload(), symbol="BTCUSDT", price=70000.0, size=0.1)
    payload = tick.model_dump()
    rebuilt = SpotTick.model_validate(payload)
    assert rebuilt == tick


def test_empty_source_fails() -> None:
    with pytest.raises(ValidationError):
        SpotTick(**_base_payload() | {"source": " "}, symbol="BTCUSDT", price=1.0)


def test_negative_timestamps_fail() -> None:
    with pytest.raises(ValidationError):
        SpotTick(
            **_base_payload() | {"source_ts_ms": -1},
            symbol="BTCUSDT",
            price=1.0,
        )


def test_decision_record_trade_and_no_trade() -> None:
    trade = DecisionRecord(
        **_base_payload(),
        action=DecisionAction.TRADE,
        reasons=[],
        market_id="m1",
    )
    no_trade = DecisionRecord(
        **_base_payload() | {"event_id": "evt-2"},
        action=DecisionAction.NO_TRADE,
        reasons=["STALE_SPOT"],
    )
    assert trade.action is DecisionAction.TRADE
    assert no_trade.action is DecisionAction.NO_TRADE


def test_order_event_statuses_supported() -> None:
    for status in [
        OrderStatus.SUBMITTED,
        OrderStatus.FILLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.UNKNOWN,
    ]:
        event = OrderEvent(**_base_payload(), order_id="o1", status=status)
        assert event.status is status


def test_health_state_statuses_supported() -> None:
    for status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.BLOCKED]:
        state = HealthState(**_base_payload(), status=status)
        assert state.status is status
