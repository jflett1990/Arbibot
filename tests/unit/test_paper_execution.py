from decimal import Decimal

from arbibot.core.events import MarketSide, OrderIntent, OrderStatus, PolyBookSnapshot
from arbibot.execution.interfaces import OrderType
from arbibot.execution.paper import PaperExecutionEngine
from arbibot.market.book import LocalOrderBook


def _book() -> LocalOrderBook:
    b = LocalOrderBook("tok")
    b.apply_snapshot(
        PolyBookSnapshot(
            event_id="s",
            source="poly",
            source_ts_ms=1,
            recv_wall_ts_ms=2,
            recv_monotonic_ns=3,
            market_id="m",
            outcome="UP",
            token_id="tok",
            bids=[[0.5, 10]],
            asks=[[0.51, 3], [0.52, 4], [0.53, 10]],
        )
    )
    return b


def _intent(order_type: str, size: float, limit: float) -> OrderIntent:
    return OrderIntent(
        event_id="i1",
        source="test",
        source_ts_ms=10,
        recv_wall_ts_ms=11,
        recv_monotonic_ns=12,
        side=MarketSide.BUY,
        client_order_id="c1",
        token_id="tok",
        order_type=order_type,
        price_limit=limit,
        size=size,
    )


def test_fak_full_and_partial_and_limit_behavior() -> None:
    b = _book()
    eng = PaperExecutionEngine(allow_partial_fak=True, fee_rate=Decimal("0.01"))
    full = eng.execute_buy(_intent(OrderType.FAK.value, 2, 0.52), b)[0]
    assert full.status is OrderStatus.FILLED
    assert full.filled_size == 2.0

    partial = eng.execute_buy(_intent(OrderType.FAK.value, 20, 0.52), b)[0]
    assert partial.status is OrderStatus.PARTIALLY_FILLED
    assert partial.filled_size == 7.0
    assert partial.remaining_size == 13.0
    assert partial.avg_fill_price is not None
    assert partial.status is not OrderStatus.CANCELLED

    no_partial = PaperExecutionEngine(allow_partial_fak=False).execute_buy(
        _intent(OrderType.FAK.value, 20, 0.52), b
    )[0]
    assert no_partial.reason == "FAK_PARTIAL_DISABLED"

    no_fill = eng.execute_buy(_intent(OrderType.FAK.value, 1, 0.50), b)[0]
    assert no_fill.reason == "NO_FILL"

    default_limit = PaperExecutionEngine().execute_buy(
        _intent(OrderType.LIMIT.value, 1, 0.55), b
    )[0]
    assert default_limit.status is OrderStatus.SUBMITTED

    cross_limit = PaperExecutionEngine(allow_immediate_limit_cross=True).execute_buy(
        _intent(OrderType.LIMIT.value, 1, 0.55), b
    )[0]
    assert cross_limit.filled_size == 1.0


def test_fok_and_validations_and_determinism() -> None:
    b = _book()
    eng = PaperExecutionEngine()
    fok_ok = eng.execute_buy(_intent(OrderType.FOK.value, 7, 0.52), b)[0]
    assert fok_ok.status is OrderStatus.FILLED

    fok_no = eng.execute_buy(_intent(OrderType.FOK.value, 8, 0.52), b)[0]
    assert fok_no.reason == "FOK_INSUFFICIENT_DEPTH"

    bad_size = eng.execute_buy(_intent(OrderType.FAK.value, 0, 0.52), b)[0]
    assert bad_size.status is OrderStatus.REJECTED

    bad_price = eng.execute_buy(_intent(OrderType.FAK.value, 1, 0), b)[0]
    assert bad_price.status is OrderStatus.REJECTED

    bad_token = eng.execute_buy(
        _intent(OrderType.FAK.value, 1, 0.52).model_copy(update={"token_id": "other"}), b
    )[0]
    assert bad_token.reason == "TOKEN_MISMATCH"

    missing_id = eng.execute_buy(
        _intent(OrderType.FAK.value, 1, 0.52).model_copy(update={"client_order_id": ""}), b
    )[0]
    assert missing_id.reason == "MISSING_CLIENT_ORDER_ID"

    unsupported = eng.execute_buy(_intent("X", 1, 0.52), b)[0]
    assert unsupported.reason == "UNSUPPORTED_ORDER_TYPE"

    e1 = eng.execute_buy(_intent(OrderType.FAK.value, 2, 0.52), b)[0]
    e2 = eng.execute_buy(_intent(OrderType.FAK.value, 2, 0.52), b)[0]
    assert e1.event_id == e2.event_id
    assert e1.metadata is not None and "gross_notional" in e1.metadata
