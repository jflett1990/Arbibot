from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from arbibot.core.errors import LiveTradingDisabledError
from arbibot.core.events import HealthStatus, OrderEvent, OrderIntent, OrderStatus
from arbibot.execution.interfaces import ExecutionClient
from arbibot.ops.health import SystemHealth


@dataclass(frozen=True, slots=True)
class LiveExecutionConfig:
    live_trading_enabled: bool = False
    pilot_mode: bool = False
    startup_confirmed: bool = False
    max_order_size_usd: Decimal = Decimal("0")
    require_event_store_available: bool = True
    require_market_metadata: bool = True
    require_risk_allowed: bool = True
    require_health_clear: bool = True

    def __post_init__(self) -> None:
        if self.max_order_size_usd < 0:
            raise ValueError("max_order_size_usd must be >= 0")
        if self.live_trading_enabled:
            if not self.pilot_mode:
                raise ValueError("pilot_mode must be True when live_trading_enabled=True")
            if not self.startup_confirmed:
                raise ValueError("startup_confirmed must be True when live_trading_enabled=True")
            if self.max_order_size_usd <= 0:
                raise ValueError("max_order_size_usd must be > 0 when live_trading_enabled=True")


class LiveExecutionGuard:
    def __init__(self, config: LiveExecutionConfig) -> None:
        self.config = config

    def validate_submit(
        self,
        intent: OrderIntent,
        risk_allowed: bool,
        health: SystemHealth | None = None,
        event_store_available: bool = True,
        market_metadata_available: bool = True,
    ) -> None:
        if not self.config.live_trading_enabled:
            raise LiveTradingDisabledError("live trading is disabled")
        if not self.config.pilot_mode:
            raise LiveTradingDisabledError("pilot mode is required")
        if not self.config.startup_confirmed:
            raise LiveTradingDisabledError("startup confirmation is required")
        if self.config.max_order_size_usd <= 0:
            raise LiveTradingDisabledError("max_order_size_usd must be > 0")
        if intent.size is None or intent.price_limit is None:
            raise LiveTradingDisabledError("order intent must include size and price_limit")

        notional = Decimal(str(intent.size)) * Decimal(str(intent.price_limit))
        if notional > self.config.max_order_size_usd:
            raise LiveTradingDisabledError("order size exceeds max_order_size_usd")

        if self.config.require_event_store_available and not event_store_available:
            raise LiveTradingDisabledError("event store unavailable")
        if self.config.require_market_metadata and not market_metadata_available:
            raise LiveTradingDisabledError("market metadata unavailable")
        if self.config.require_risk_allowed and not risk_allowed:
            raise LiveTradingDisabledError("risk engine blocked live submit")

        if self.config.require_health_clear:
            if health is None:
                raise LiveTradingDisabledError("health state is required")
            if not health.can_submit_orders:
                raise LiveTradingDisabledError("health monitor blocked live submit")


class DisabledLiveExecutionClient(ExecutionClient):
    def submit_order(self, intent: OrderIntent) -> OrderEvent:
        raise LiveTradingDisabledError("live execution client is disabled")

    def cancel_order(self, client_order_id: str) -> OrderEvent:
        raise LiveTradingDisabledError("live execution client is disabled")

    def cancel_all(self, market_id: str | None = None) -> list[OrderEvent]:
        return []

    def get_open_orders(self) -> list[OrderEvent]:
        return []

    def get_order_status(self, client_order_id: str) -> OrderEvent | None:
        return None


class MockLiveExecutionClient(ExecutionClient):
    def __init__(self, guard: LiveExecutionGuard) -> None:
        self.guard = guard
        self._open_orders: dict[str, OrderEvent] = {}

    def submit_order(self, intent: OrderIntent) -> OrderEvent:
        health = SystemHealth(
            status=HealthStatus.HEALTHY,
            checks=[],
            can_consider_trade=True,
            can_submit_orders=True,
            reasons=[],
        )
        self.guard.validate_submit(intent, risk_allowed=True, health=health)
        client_order_id = intent.client_order_id or ""
        evt = OrderEvent(
            event_id=f"live_submit:{client_order_id}",
            source="arbibot.mock_live_execution",
            source_ts_ms=intent.source_ts_ms,
            recv_wall_ts_ms=intent.recv_wall_ts_ms,
            recv_monotonic_ns=intent.recv_monotonic_ns,
            order_id=client_order_id,
            status=OrderStatus.SUBMITTED,
            client_order_id=client_order_id,
            token_id=intent.token_id,
            requested_size=intent.size,
            filled_size=0.0,
            remaining_size=intent.size,
            reason="SUBMITTED",
        )
        self._open_orders[client_order_id] = evt
        return evt

    def cancel_order(self, client_order_id: str) -> OrderEvent:
        existing = self._open_orders.pop(client_order_id, None)
        if existing is None:
            return OrderEvent(
                event_id=f"live_missing:{client_order_id}",
                source="arbibot.mock_live_execution",
                source_ts_ms=1,
                recv_wall_ts_ms=1,
                recv_monotonic_ns=1,
                order_id=client_order_id,
                status=OrderStatus.REJECTED,
                client_order_id=client_order_id,
                reason="ORDER_NOT_FOUND",
            )
        return OrderEvent(
            event_id=f"live_cancel:{client_order_id}",
            source="arbibot.mock_live_execution",
            source_ts_ms=existing.source_ts_ms,
            recv_wall_ts_ms=existing.recv_wall_ts_ms,
            recv_monotonic_ns=existing.recv_monotonic_ns,
            order_id=client_order_id,
            status=OrderStatus.CANCELLED,
            client_order_id=client_order_id,
            token_id=existing.token_id,
            requested_size=existing.requested_size,
            filled_size=0.0,
            remaining_size=existing.remaining_size,
            reason="CANCELLED",
        )

    def cancel_all(self, market_id: str | None = None) -> list[OrderEvent]:
        order_ids = sorted(self._open_orders.keys())
        return [self.cancel_order(order_id) for order_id in order_ids]

    def get_open_orders(self) -> list[OrderEvent]:
        return [self._open_orders[k] for k in sorted(self._open_orders.keys())]

    def get_order_status(self, client_order_id: str) -> OrderEvent | None:
        return self._open_orders.get(client_order_id)
