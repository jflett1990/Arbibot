from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from arbibot.core.events import OrderEvent, OrderStatus
from arbibot.risk.kill_switch import KillSwitch
from arbibot.risk.limits import (
    daily_loss_limit,
    hard_stop_limit,
    max_daily_traded_notional,
    max_loss_per_trade,
    max_market_exposure,
    suggest_buy_size_for_binary,
)

RISK_PER_TRADE_EXCEEDED = "RISK_PER_TRADE_EXCEEDED"
DAILY_LOSS_CAP_REACHED = "DAILY_LOSS_CAP_REACHED"
HARD_STOP_REACHED = "HARD_STOP_REACHED"
MARKET_EXPOSURE_CAP_REACHED = "MARKET_EXPOSURE_CAP_REACHED"
OPEN_ORDER_LIMIT_REACHED = "OPEN_ORDER_LIMIT_REACHED"
DAILY_NOTIONAL_CAP_REACHED = "DAILY_NOTIONAL_CAP_REACHED"
UNKNOWN_ORDER_STATE = "UNKNOWN_ORDER_STATE"
KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
RISK_ENGINE_DISABLED = "RISK_ENGINE_DISABLED"
INVALID_ORDER_SIZE = "INVALID_ORDER_SIZE"
INVALID_PRICE = "INVALID_PRICE"


@dataclass(frozen=True, slots=True)
class RiskConfig:
    account_equity: Decimal
    risk_per_trade_pct: Decimal = Decimal("0.005")
    daily_loss_cap_pct: Decimal = Decimal("0.02")
    hard_stop_pct: Decimal = Decimal("0.004")
    max_market_exposure_pct: Decimal = Decimal("0.02")
    max_open_orders: int = 1
    max_daily_traded_notional_pct: Decimal = Decimal("0.20")

    def __post_init__(self) -> None:
        if self.account_equity <= 0:
            raise ValueError("account_equity must be > 0")
        pct_fields = (
            self.risk_per_trade_pct,
            self.daily_loss_cap_pct,
            self.hard_stop_pct,
            self.max_market_exposure_pct,
            self.max_daily_traded_notional_pct,
        )
        if any(value < 0 for value in pct_fields):
            raise ValueError("pct values must be >= 0")
        if self.max_open_orders < 0:
            raise ValueError("max_open_orders must be >= 0")
        if (
            self.max_market_exposure_pct != 0
            and self.risk_per_trade_pct > self.max_market_exposure_pct
        ):
            raise ValueError("risk_per_trade_pct must be <= max_market_exposure_pct")
        if (
            self.daily_loss_cap_pct != 0
            and self.hard_stop_pct != 0
            and self.daily_loss_cap_pct < self.hard_stop_pct
        ):
            raise ValueError("daily_loss_cap_pct must be >= hard_stop_pct")


@dataclass(slots=True)
class RiskEngineState:
    realized_daily_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    open_market_exposure: Decimal = Decimal("0")
    open_orders: int = 0
    daily_traded_notional: Decimal = Decimal("0")
    unknown_order_state: bool = False
    kill_switch_active: bool = False
    disabled: bool = False
    disable_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class RiskCheckResult:
    allowed: bool
    reasons: list[str]
    max_loss_allowed: Decimal
    max_position_notional: Decimal
    suggested_size: Decimal | None = None


class RiskEngine:
    def __init__(self, config: RiskConfig, state: RiskEngineState | None = None) -> None:
        self.config = config
        self.state = state or RiskEngineState()
        self._kill_switch = KillSwitch()

    def check_new_order(self, price: Decimal, size: Decimal) -> RiskCheckResult:
        reasons: list[str] = []
        max_loss_allowed = max_loss_per_trade(self.config)
        max_position_notional = max_market_exposure(self.config)

        if price <= 0:
            reasons.append(INVALID_PRICE)
        if size <= 0:
            reasons.append(INVALID_ORDER_SIZE)

        daily_limit = daily_loss_limit(self.config)
        hard_stop = hard_stop_limit(self.config)
        exposure_limit = max_position_notional
        daily_notional_limit = max_daily_traded_notional(self.config)

        if self.state.realized_daily_pnl <= -daily_limit:
            reasons.append(DAILY_LOSS_CAP_REACHED)
        if self.state.unrealized_pnl <= -hard_stop:
            reasons.append(HARD_STOP_REACHED)
        if self.state.open_market_exposure >= exposure_limit:
            reasons.append(MARKET_EXPOSURE_CAP_REACHED)
        if self.state.open_orders >= self.config.max_open_orders:
            reasons.append(OPEN_ORDER_LIMIT_REACHED)
        if self.state.daily_traded_notional >= daily_notional_limit:
            reasons.append(DAILY_NOTIONAL_CAP_REACHED)
        if self.state.unknown_order_state:
            reasons.append(UNKNOWN_ORDER_STATE)
        if self.state.kill_switch_active:
            reasons.append(KILL_SWITCH_ACTIVE)
        if self.state.disabled:
            reasons.append(RISK_ENGINE_DISABLED)

        proposed_notional = price * size
        if proposed_notional > max_loss_allowed:
            reasons.append(RISK_PER_TRADE_EXCEEDED)
        if (
            self.state.open_market_exposure + proposed_notional > exposure_limit
            and MARKET_EXPOSURE_CAP_REACHED not in reasons
        ):
            reasons.append(MARKET_EXPOSURE_CAP_REACHED)
        if (
            self.state.daily_traded_notional + proposed_notional > daily_notional_limit
            and DAILY_NOTIONAL_CAP_REACHED not in reasons
        ):
            reasons.append(DAILY_NOTIONAL_CAP_REACHED)

        suggested = None
        if price > 0:
            suggested = suggest_buy_size_for_binary(
                self.config,
                price,
                current_exposure=self.state.open_market_exposure,
            )

        return RiskCheckResult(
            allowed=not reasons,
            reasons=reasons,
            max_loss_allowed=max_loss_allowed,
            max_position_notional=max_position_notional,
            suggested_size=suggested,
        )

    def apply_order_event(self, order_event: OrderEvent) -> None:
        status = order_event.status
        if status is OrderStatus.SUBMITTED:
            self.state.open_orders += 1
            return

        if status in {OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED}:
            filled = Decimal(str(order_event.filled_size or 0))
            avg_price = Decimal(str(order_event.avg_fill_price or 0))
            notional = filled * avg_price
            self.state.open_market_exposure += notional
            self.state.daily_traded_notional += notional
            self.state.open_orders = max(0, self.state.open_orders - 1)
            return

        if status in {OrderStatus.CANCELLED, OrderStatus.REJECTED, OrderStatus.UNKNOWN}:
            self.state.open_orders = max(0, self.state.open_orders - 1)

    def set_unknown_order_state(self, value: bool) -> None:
        self.state.unknown_order_state = value

    def activate_kill_switch(self, reason: str) -> None:
        self._kill_switch.activate(reason)
        self.state.kill_switch_active = True

    def deactivate_kill_switch(self) -> None:
        self._kill_switch.deactivate()
        self.state.kill_switch_active = False

    def disable(self, reason: str) -> None:
        if reason not in self.state.disable_reasons:
            self.state.disable_reasons.append(reason)
        self.state.disabled = True

    def reset_daily(self) -> None:
        self.state.realized_daily_pnl = Decimal("0")
        self.state.daily_traded_notional = Decimal("0")


def risk_gate_flags(result: RiskCheckResult, state: RiskEngineState) -> dict[str, bool]:
    return {"risk_blocked": not result.allowed, "unknown_order_state": state.unknown_order_state}
