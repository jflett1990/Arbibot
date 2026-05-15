from decimal import Decimal

import pytest

from arbibot.core.errors import LiveTradingDisabledError
from arbibot.core.events import HealthStatus, OrderIntent
from arbibot.execution.live import LiveExecutionConfig, LiveExecutionGuard
from arbibot.ops.health import SystemHealth


def _intent(size: float = 1.0, price: float = 0.5) -> OrderIntent:
    return OrderIntent(
        event_id="i1",
        source="test",
        source_ts_ms=1,
        recv_wall_ts_ms=2,
        recv_monotonic_ns=3,
        side="BUY",
        client_order_id="cid1",
        token_id="tok",
        order_type="FAK",
        price_limit=price,
        size=size,
    )


def _healthy() -> SystemHealth:
    return SystemHealth(HealthStatus.HEALTHY, [], True, True, [])


def test_default_config_disables_live_trading() -> None:
    guard = LiveExecutionGuard(LiveExecutionConfig())
    with pytest.raises(LiveTradingDisabledError):
        guard.validate_submit(_intent(), risk_allowed=True, health=_healthy())


def test_config_validation_live_enabled_requirements() -> None:
    with pytest.raises(ValueError):
        LiveExecutionConfig(live_trading_enabled=True)


def test_guard_blocks_pilot_startup_and_max() -> None:
    with pytest.raises(LiveTradingDisabledError):
        LiveExecutionGuard(
            LiveExecutionConfig(
                live_trading_enabled=True,
                pilot_mode=True,
                startup_confirmed=True,
                max_order_size_usd=Decimal("1"),
            )
        ).validate_submit(_intent(size=10, price=1), risk_allowed=True, health=_healthy())


def test_guard_blocks_required_dependencies() -> None:
    cfg = LiveExecutionConfig(
        live_trading_enabled=True,
        pilot_mode=True,
        startup_confirmed=True,
        max_order_size_usd=Decimal("10"),
    )
    guard = LiveExecutionGuard(cfg)
    with pytest.raises(LiveTradingDisabledError):
        guard.validate_submit(_intent(), risk_allowed=False, health=_healthy())
    with pytest.raises(LiveTradingDisabledError):
        guard.validate_submit(
            _intent(),
            risk_allowed=True,
            event_store_available=False,
            health=_healthy(),
        )
    with pytest.raises(LiveTradingDisabledError):
        guard.validate_submit(
            _intent(),
            risk_allowed=True,
            market_metadata_available=False,
            health=_healthy(),
        )
    blocked = SystemHealth(HealthStatus.BLOCKED, [], False, False, ["X"])
    with pytest.raises(LiveTradingDisabledError):
        guard.validate_submit(_intent(), risk_allowed=True, health=blocked)


def test_guard_allows_healthy_submit() -> None:
    cfg = LiveExecutionConfig(
        live_trading_enabled=True,
        pilot_mode=True,
        startup_confirmed=True,
        max_order_size_usd=Decimal("10"),
    )
    LiveExecutionGuard(cfg).validate_submit(_intent(), risk_allowed=True, health=_healthy())
