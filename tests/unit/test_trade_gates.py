from decimal import Decimal

from arbibot.core.events import DecisionAction, FeatureSnapshot
from arbibot.opportunity.edge import EdgeInput, OutcomeSide, calculate_edge
from arbibot.opportunity.gates import (
    TradeGateConfig,
    TradeGateInput,
    apply_trade_gates,
    build_decision_record,
)


def _snapshot(stale_spot: bool, stale_book: bool) -> FeatureSnapshot:
    return FeatureSnapshot(
        event_id="f",
        source="x",
        source_ts_ms=1,
        recv_wall_ts_ms=2,
        recv_monotonic_ns=3,
        feature_set="x",
        values={},
        stale_spot=stale_spot,
        stale_book=stale_book,
        symbol="BTCUSDT",
    )


def _edge(price: str) -> object:
    return calculate_edge(
        EdgeInput(
            outcome_side=OutcomeSide.UP,
            fair_up_probability=Decimal("0.6"),
            fair_down_probability=Decimal("0.4"),
            executable_price=Decimal(price),
            target_size=Decimal("1"),
        )
    )


def test_gates_block_and_accumulate_and_allow() -> None:
    cfg = TradeGateConfig()
    blocked = apply_trade_gates(
        TradeGateInput(
            edge_result=None,
            feature_snapshot=_snapshot(True, True),
            book_spread=None,
            depth_ratio=Decimal("1"),
            seconds_to_expiry=Decimal("10"),
            confidence=Decimal("0.1"),
            conflict=Decimal("0.9"),
            risk_blocked=True,
            unknown_order_state=True,
            daily_loss_cap_reached=True,
            health_blocked=True,
        ),
        cfg,
    )
    assert blocked.action is DecisionAction.NO_TRADE
    assert len(blocked.reasons) >= 10

    clean = apply_trade_gates(
        TradeGateInput(
            edge_result=_edge("0.58"),
            feature_snapshot=_snapshot(False, False),
            book_spread=Decimal("0.01"),
            depth_ratio=Decimal("5"),
            seconds_to_expiry=Decimal("60"),
        ),
        cfg,
    )
    assert clean.should_trade
    rec = build_decision_record(clean, "d1", 1, 2, 3, {"k": "v"})
    assert rec.action is DecisionAction.TRADE
    assert rec.reasons == []
    assert rec.metadata == {"k": "v"}

    no = apply_trade_gates(
        TradeGateInput(
            edge_result=_edge("0.599"),
            feature_snapshot=_snapshot(False, False),
            book_spread=Decimal("0.01"),
            depth_ratio=Decimal("5"),
            seconds_to_expiry=Decimal("60"),
        ),
        cfg,
    )
    rec2 = build_decision_record(no, "d2", 1, 2, 3)
    assert rec2.action is DecisionAction.NO_TRADE
    assert rec2.reasons
