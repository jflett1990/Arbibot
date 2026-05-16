from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arbibot.ops.health import SystemHealth

LIVE_TRADING_DISABLED = "LIVE_TRADING_DISABLED"
PILOT_MODE_DISABLED = "PILOT_MODE_DISABLED"
STARTUP_NOT_CONFIRMED = "STARTUP_NOT_CONFIRMED"
MAX_ORDER_SIZE_NOT_SET = "MAX_ORDER_SIZE_NOT_SET"
MAX_ORDERS_NOT_SET = "MAX_ORDERS_NOT_SET"
REAL_EXECUTION_NOT_ALLOWED = "REAL_EXECUTION_NOT_ALLOWED"
EVENT_STORE_UNAVAILABLE = "EVENT_STORE_UNAVAILABLE"
MARKET_METADATA_MISSING = "MARKET_METADATA_MISSING"
HEALTH_BLOCKED = "HEALTH_BLOCKED"
RISK_BLOCKED = "RISK_BLOCKED"


@dataclass(frozen=True, slots=True)
class LivePilotUnlockConfig:
    live_trading_enabled: bool = False
    pilot_mode: bool = False
    startup_confirmed: bool = False
    max_order_size_usd: Decimal = Decimal("0")
    max_orders_per_session: int = 1
    require_event_store_available: bool = True
    require_market_metadata: bool = True
    require_health_clear: bool = True
    require_risk_allowed: bool = True
    allow_mock_execution_only: bool = True

    def __post_init__(self) -> None:
        if self.max_order_size_usd < 0:
            raise ValueError("max_order_size_usd must be >= 0")
        if self.max_orders_per_session < 0:
            raise ValueError("max_orders_per_session must be >= 0")
        if self.live_trading_enabled:
            if not self.pilot_mode:
                raise ValueError("pilot_mode must be True when live_trading_enabled=True")
            if not self.startup_confirmed:
                raise ValueError("startup_confirmed must be True when live_trading_enabled=True")
            if self.max_order_size_usd <= 0:
                raise ValueError("max_order_size_usd must be > 0 when live_trading_enabled=True")
            if self.max_orders_per_session <= 0:
                raise ValueError(
                    "max_orders_per_session must be > 0 when live_trading_enabled=True"
                )
            if not self.allow_mock_execution_only:
                raise ValueError("allow_mock_execution_only must be True for this phase")


@dataclass(frozen=True, slots=True)
class LivePilotUnlockResult:
    unlocked: bool
    reasons: list[str]


def validate_live_pilot_unlock(
    config: LivePilotUnlockConfig,
    health: SystemHealth | None,
    risk_allowed: bool,
    event_store_available: bool,
    market_metadata_available: bool,
) -> LivePilotUnlockResult:
    reasons: list[str] = []
    if not config.live_trading_enabled:
        reasons.append(LIVE_TRADING_DISABLED)
    if not config.pilot_mode:
        reasons.append(PILOT_MODE_DISABLED)
    if not config.startup_confirmed:
        reasons.append(STARTUP_NOT_CONFIRMED)
    if config.max_order_size_usd <= 0:
        reasons.append(MAX_ORDER_SIZE_NOT_SET)
    if config.max_orders_per_session <= 0:
        reasons.append(MAX_ORDERS_NOT_SET)
    if not config.allow_mock_execution_only:
        reasons.append(REAL_EXECUTION_NOT_ALLOWED)

    if config.require_event_store_available and not event_store_available:
        reasons.append(EVENT_STORE_UNAVAILABLE)
    if config.require_market_metadata and not market_metadata_available:
        reasons.append(MARKET_METADATA_MISSING)
    if config.require_health_clear and (health is None or not health.can_submit_orders):
        reasons.append(HEALTH_BLOCKED)
    if config.require_risk_allowed and not risk_allowed:
        reasons.append(RISK_BLOCKED)

    return LivePilotUnlockResult(unlocked=len(reasons) == 0, reasons=reasons)
