from __future__ import annotations

from decimal import Decimal

from arbibot.core.events import DecisionAction, DecisionRecord, OrderEvent, OrderIntent, OrderStatus
from arbibot.execution.interfaces import ExecutionClient
from arbibot.execution.live import MockLiveExecutionClient
from arbibot.live.runtime import LivePilotRuntimeState
from arbibot.live.unlock import LivePilotUnlockConfig, validate_live_pilot_unlock
from arbibot.ops.health import SystemHealth
from arbibot.risk.engine import RiskEngine

MISSING_ORDER_INTENT = "MISSING_ORDER_INTENT"
MAX_ORDERS_REACHED = "MAX_ORDERS_REACHED"
RUNTIME_DISABLED = "RUNTIME_DISABLED"
UNSAFE_EXECUTION_CLIENT = "UNSAFE_EXECUTION_CLIENT"
SUBMIT_BLOCKED = "SUBMIT_BLOCKED"
SUBMIT_FAILED = "SUBMIT_FAILED"


class LivePilotRunner:
    def __init__(
        self,
        unlock_config: LivePilotUnlockConfig,
        execution_client: ExecutionClient,
        risk_engine: RiskEngine,
        runtime_state: LivePilotRuntimeState,
    ) -> None:
        self.unlock_config = unlock_config
        self.execution_client = execution_client
        self.risk_engine = risk_engine
        self.runtime_state = runtime_state

    def maybe_submit_decision(
        self,
        decision_record: DecisionRecord,
        order_intent: OrderIntent | None,
        health: SystemHealth,
        event_store_available: bool,
        market_metadata_available: bool,
    ) -> OrderEvent | None:
        if decision_record.action is not DecisionAction.TRADE:
            return None
        if self.runtime_state.disabled:
            self.runtime_state.disable(RUNTIME_DISABLED)
            return None
        if order_intent is None:
            self.runtime_state.disable(MISSING_ORDER_INTENT)
            return None
        if not self.runtime_state.can_submit_more(self.unlock_config.max_orders_per_session):
            self.runtime_state.disable(MAX_ORDERS_REACHED)
            return None
        if self.unlock_config.allow_mock_execution_only and not isinstance(
            self.execution_client, MockLiveExecutionClient
        ):
            self.runtime_state.disable(UNSAFE_EXECUTION_CLIENT)
            return None
        if order_intent.price_limit is None or order_intent.size is None:
            self.runtime_state.disable(SUBMIT_FAILED)
            return None

        risk_result = self.risk_engine.check_new_order(
            price=self._to_decimal(order_intent.price_limit),
            size=self._to_decimal(order_intent.size),
        )
        unlock = validate_live_pilot_unlock(
            config=self.unlock_config,
            health=health,
            risk_allowed=risk_result.allowed,
            event_store_available=event_store_available,
            market_metadata_available=market_metadata_available,
        )
        if not unlock.unlocked:
            for reason in unlock.reasons:
                self.runtime_state.disable(reason)
            self.runtime_state.disable(SUBMIT_BLOCKED)
            return None

        order_event = self.execution_client.submit_order(order_intent)
        if order_event.status is OrderStatus.SUBMITTED:
            self.runtime_state.mark_order_submitted(
                order_intent.client_order_id or "",
                decision_record.event_id,
            )
        self.risk_engine.apply_order_event(order_event)
        return order_event

    @staticmethod
    def _to_decimal(value: float) -> Decimal:
        return Decimal(str(value))
