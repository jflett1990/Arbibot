from decimal import Decimal

import pytest

from arbibot.core.errors import LiveTradingDisabledError
from arbibot.core.events import OrderIntent, OrderStatus
from arbibot.execution.live import (
    DisabledLiveExecutionClient,
    LiveExecutionConfig,
    LiveExecutionGuard,
    MockLiveExecutionClient,
)
from arbibot.execution.paper import PaperExecutionEngine


def _intent(cid: str = "cid1") -> OrderIntent:
    return OrderIntent(
        event_id=f"i:{cid}",
        source="test",
        source_ts_ms=10,
        recv_wall_ts_ms=11,
        recv_monotonic_ns=12,
        side="BUY",
        client_order_id=cid,
        token_id="tok",
        order_type="FAK",
        price_limit=0.5,
        size=1.0,
    )


def _client() -> MockLiveExecutionClient:
    cfg = LiveExecutionConfig(
        live_trading_enabled=True,
        pilot_mode=True,
        startup_confirmed=True,
        max_order_size_usd=Decimal("10"),
    )
    guard = LiveExecutionGuard(cfg)
    return MockLiveExecutionClient(guard)


def test_disabled_client_safe_methods() -> None:
    c = DisabledLiveExecutionClient()
    with pytest.raises(LiveTradingDisabledError):
        c.submit_order(_intent())
    with pytest.raises(LiveTradingDisabledError):
        c.cancel_order("x")
    assert c.cancel_all() == []
    assert c.get_open_orders() == []
    assert c.get_order_status("x") is None


def test_mock_client_submit_cancel_cancel_all_and_missing() -> None:
    c = _client()
    submitted = c.submit_order(_intent("a1"))
    assert submitted.status is OrderStatus.SUBMITTED
    assert submitted.event_id == "live_submit:a1"
    assert len(c.get_open_orders()) == 1
    assert c.get_order_status("a1") is not None

    cancelled = c.cancel_order("a1")
    assert cancelled.status is OrderStatus.CANCELLED
    assert cancelled.event_id == "live_cancel:a1"
    assert c.get_order_status("a1") is None

    c.submit_order(_intent("b1"))
    c.submit_order(_intent("b2"))
    cancelled_all = c.cancel_all()
    assert [e.event_id for e in cancelled_all] == ["live_cancel:b1", "live_cancel:b2"]

    missing = c.cancel_order("zzz")
    assert missing.status is OrderStatus.REJECTED
    assert missing.event_id == "live_missing:zzz"


def test_paper_execution_engine_unaffected_import() -> None:
    assert PaperExecutionEngine is not None
