from decimal import Decimal

from arbibot.core.events import (
    DecisionAction,
    DecisionRecord,
    HealthStatus,
    OrderIntent,
    OrderStatus,
)
from arbibot.execution.live import LiveExecutionConfig, LiveExecutionGuard, MockLiveExecutionClient
from arbibot.live.pilot import (
    MAX_ORDERS_REACHED,
    MISSING_ORDER_INTENT,
    UNSAFE_EXECUTION_CLIENT,
    LivePilotRunner,
)
from arbibot.live.runtime import LivePilotRuntimeState
from arbibot.live.unlock import LivePilotUnlockConfig
from arbibot.ops.health import SystemHealth
from arbibot.risk.engine import RiskConfig, RiskEngine


class FakeClient:
    def submit_order(self, intent: OrderIntent):
        raise RuntimeError


def _decision(action: DecisionAction = DecisionAction.TRADE) -> DecisionRecord:
    return DecisionRecord(
        event_id="d1",
        source="x",
        source_ts_ms=1,
        recv_wall_ts_ms=2,
        recv_monotonic_ns=3,
        action=action,
    )


def _intent() -> OrderIntent:
    return OrderIntent(
        event_id="i1",
        source="x",
        source_ts_ms=1,
        recv_wall_ts_ms=2,
        recv_monotonic_ns=3,
        side="BUY",
        client_order_id="cid1",
        token_id="tok",
        order_type="FAK",
        price_limit=0.5,
        size=1.0,
    )


def _health(blocked: bool = False) -> SystemHealth:
    if blocked:
        return SystemHealth(HealthStatus.BLOCKED, [], False, False, ["x"])
    return SystemHealth(HealthStatus.HEALTHY, [], True, True, [])


def _runner(max_orders: int = 1) -> LivePilotRunner:
    unlock_cfg = LivePilotUnlockConfig(
        live_trading_enabled=True,
        pilot_mode=True,
        startup_confirmed=True,
        max_order_size_usd=Decimal("10"),
        max_orders_per_session=max_orders,
    )
    client = MockLiveExecutionClient(
        LiveExecutionGuard(
            LiveExecutionConfig(
                live_trading_enabled=True,
                pilot_mode=True,
                startup_confirmed=True,
                max_order_size_usd=Decimal("10"),
            )
        )
    )
    return LivePilotRunner(
        unlock_cfg,
        client,
        RiskEngine(RiskConfig(account_equity=Decimal("1000"))),
        LivePilotRuntimeState(session_id="s", started_at_ms=1),
    )


def test_pilot_runner_paths() -> None:
    runner = _runner()
    assert (
        runner.maybe_submit_decision(
            _decision(DecisionAction.NO_TRADE),
            _intent(),
            _health(),
            True,
            True,
        )
        is None
    )

    assert runner.maybe_submit_decision(_decision(), None, _health(), True, True) is None
    assert MISSING_ORDER_INTENT in runner.runtime_state.disable_reasons

    runner2 = _runner()
    runner2.execution_client = FakeClient()  # type: ignore[assignment]
    assert runner2.maybe_submit_decision(_decision(), _intent(), _health(), True, True) is None
    assert UNSAFE_EXECUTION_CLIENT in runner2.runtime_state.disable_reasons

    runner3 = _runner(max_orders=1)
    evt = runner3.maybe_submit_decision(_decision(), _intent(), _health(), True, True)
    assert evt is not None and evt.status is OrderStatus.SUBMITTED
    assert runner3.runtime_state.orders_submitted == 1
    evt2 = runner3.maybe_submit_decision(_decision(), _intent(), _health(), True, True)
    assert evt2 is None
    assert MAX_ORDERS_REACHED in runner3.runtime_state.disable_reasons

    runner4 = _runner()
    assert (
        runner4.maybe_submit_decision(
            _decision(),
            _intent(),
            _health(blocked=True),
            True,
            True,
        )
        is None
    )
    runner5 = _runner()
    assert runner5.maybe_submit_decision(_decision(), _intent(), _health(), False, True) is None
    runner6 = _runner()
    assert runner6.maybe_submit_decision(_decision(), _intent(), _health(), True, False) is None
