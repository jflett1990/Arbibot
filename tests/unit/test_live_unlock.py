from decimal import Decimal

from arbibot.core.events import HealthStatus
from arbibot.live.unlock import (
    EVENT_STORE_UNAVAILABLE,
    HEALTH_BLOCKED,
    LIVE_TRADING_DISABLED,
    MARKET_METADATA_MISSING,
    MAX_ORDER_SIZE_NOT_SET,
    PILOT_MODE_DISABLED,
    RISK_BLOCKED,
    STARTUP_NOT_CONFIRMED,
    LivePilotUnlockConfig,
    validate_live_pilot_unlock,
)
from arbibot.ops.health import SystemHealth


def _healthy() -> SystemHealth:
    return SystemHealth(HealthStatus.HEALTHY, [], True, True, [])


def test_default_locked_with_accumulated_reasons() -> None:
    res = validate_live_pilot_unlock(
        LivePilotUnlockConfig(),
        _healthy(),
        risk_allowed=True,
        event_store_available=True,
        market_metadata_available=True,
    )
    assert not res.unlocked
    assert LIVE_TRADING_DISABLED in res.reasons
    assert PILOT_MODE_DISABLED in res.reasons
    assert STARTUP_NOT_CONFIRMED in res.reasons
    assert MAX_ORDER_SIZE_NOT_SET in res.reasons


def test_unlock_blocks_for_each_guard_and_unlocks_when_valid() -> None:
    cfg = LivePilotUnlockConfig(
        live_trading_enabled=True,
        pilot_mode=True,
        startup_confirmed=True,
        max_order_size_usd=Decimal("10"),
        max_orders_per_session=1,
    )
    blocked = validate_live_pilot_unlock(
        cfg,
        SystemHealth(HealthStatus.BLOCKED, [], False, False, ["x"]),
        risk_allowed=False,
        event_store_available=False,
        market_metadata_available=False,
    )
    assert EVENT_STORE_UNAVAILABLE in blocked.reasons
    assert MARKET_METADATA_MISSING in blocked.reasons
    assert HEALTH_BLOCKED in blocked.reasons
    assert RISK_BLOCKED in blocked.reasons

    ok = validate_live_pilot_unlock(
        cfg,
        _healthy(),
        risk_allowed=True,
        event_store_available=True,
        market_metadata_available=True,
    )
    assert ok.unlocked
    assert ok.reasons == []


def test_config_validations() -> None:
    import pytest

    with pytest.raises(ValueError):
        LivePilotUnlockConfig(
            live_trading_enabled=True,
            pilot_mode=True,
            startup_confirmed=True,
            max_order_size_usd=Decimal("1"),
            max_orders_per_session=1,
            allow_mock_execution_only=False,
        )

    with pytest.raises(ValueError):
        LivePilotUnlockConfig(
            live_trading_enabled=True,
            pilot_mode=True,
            startup_confirmed=True,
            max_order_size_usd=Decimal("1"),
            max_orders_per_session=0,
            allow_mock_execution_only=False,
        )
