from decimal import Decimal

from arbibot.core.events import OrderEvent, OrderStatus
from arbibot.risk.engine import (
    DAILY_LOSS_CAP_REACHED,
    DAILY_NOTIONAL_CAP_REACHED,
    HARD_STOP_REACHED,
    INVALID_ORDER_SIZE,
    INVALID_PRICE,
    MARKET_EXPOSURE_CAP_REACHED,
    OPEN_ORDER_LIMIT_REACHED,
    RISK_ENGINE_DISABLED,
    RISK_PER_TRADE_EXCEEDED,
    UNKNOWN_ORDER_STATE,
    RiskConfig,
    RiskEngine,
    risk_gate_flags,
)


def _event(
    status: OrderStatus,
    filled: float | None = None,
    price: float | None = None,
) -> OrderEvent:
    return OrderEvent(
        event_id=f"o:{status.value}",
        source="paper",
        source_ts_ms=1,
        recv_wall_ts_ms=2,
        recv_monotonic_ns=3,
        order_id="oid",
        status=status,
        client_order_id="cid",
        filled_size=filled,
        avg_fill_price=price,
    )


def test_clean_order_allowed_and_suggested_size_present() -> None:
    eng = RiskEngine(RiskConfig(account_equity=Decimal("1000")))
    result = eng.check_new_order(Decimal("0.5"), Decimal("1"))
    assert result.allowed is True
    assert result.suggested_size is not None


def test_invalid_inputs_and_multiple_reasons() -> None:
    eng = RiskEngine(RiskConfig(account_equity=Decimal("1000")))
    eng.state.unknown_order_state = True
    result = eng.check_new_order(Decimal("0"), Decimal("0"))
    assert INVALID_PRICE in result.reasons
    assert INVALID_ORDER_SIZE in result.reasons
    assert UNKNOWN_ORDER_STATE in result.reasons


def test_limits_blocking_conditions() -> None:
    eng = RiskEngine(RiskConfig(account_equity=Decimal("1000")))
    eng.state.realized_daily_pnl = Decimal("-20")
    eng.state.unrealized_pnl = Decimal("-4")
    eng.state.open_market_exposure = Decimal("20")
    eng.state.open_orders = 1
    eng.state.daily_traded_notional = Decimal("200")
    res = eng.check_new_order(Decimal("0.5"), Decimal("20"))
    assert DAILY_LOSS_CAP_REACHED in res.reasons
    assert HARD_STOP_REACHED in res.reasons
    assert MARKET_EXPOSURE_CAP_REACHED in res.reasons
    assert OPEN_ORDER_LIMIT_REACHED in res.reasons
    assert DAILY_NOTIONAL_CAP_REACHED in res.reasons
    assert RISK_PER_TRADE_EXCEEDED in res.reasons


def test_disabled_and_unknown_and_gate_flags() -> None:
    eng = RiskEngine(RiskConfig(account_equity=Decimal("1000")))
    eng.disable("manual")
    eng.set_unknown_order_state(True)
    res = eng.check_new_order(Decimal("0.5"), Decimal("1"))
    assert RISK_ENGINE_DISABLED in res.reasons
    assert UNKNOWN_ORDER_STATE in res.reasons
    flags = risk_gate_flags(res, eng.state)
    assert flags == {"risk_blocked": True, "unknown_order_state": True}


def test_apply_order_events_and_reset_daily() -> None:
    eng = RiskEngine(RiskConfig(account_equity=Decimal("1000")))
    eng.apply_order_event(_event(OrderStatus.SUBMITTED))
    assert eng.state.open_orders == 1
    eng.apply_order_event(_event(OrderStatus.FILLED, filled=2.0, price=0.5))
    assert eng.state.open_market_exposure == Decimal("1.0")
    assert eng.state.daily_traded_notional == Decimal("1.0")
    assert eng.state.open_orders == 0

    eng.apply_order_event(_event(OrderStatus.PARTIALLY_FILLED, filled=1.0, price=0.25))
    assert eng.state.open_market_exposure == Decimal("1.25")
    assert eng.state.daily_traded_notional == Decimal("1.25")

    eng.apply_order_event(_event(OrderStatus.CANCELLED))
    eng.apply_order_event(_event(OrderStatus.REJECTED))
    assert eng.state.open_orders == 0

    eng.state.realized_daily_pnl = Decimal("-3")
    eng.reset_daily()
    assert eng.state.realized_daily_pnl == Decimal("0")
    assert eng.state.daily_traded_notional == Decimal("0")
    assert eng.state.open_market_exposure == Decimal("1.25")


def test_disable_reason_deduplicated() -> None:
    eng = RiskEngine(RiskConfig(account_equity=Decimal("1000")))
    eng.disable("x")
    eng.disable("x")
    assert eng.state.disable_reasons == ["x"]
