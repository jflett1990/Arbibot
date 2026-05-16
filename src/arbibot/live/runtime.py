from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LivePilotRuntimeState:
    session_id: str
    started_at_ms: int
    orders_submitted: int = 0
    disabled: bool = False
    disable_reasons: list[str] = field(default_factory=list)
    last_decision_event_id: str | None = None
    last_client_order_id: str | None = None

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must be non-empty")
        if self.started_at_ms <= 0:
            raise ValueError("started_at_ms must be positive")

    def can_submit_more(self, max_orders_per_session: int) -> bool:
        if max_orders_per_session < 0:
            raise ValueError("max_orders_per_session must be nonnegative")
        return self.orders_submitted < max_orders_per_session

    def mark_order_submitted(self, client_order_id: str, decision_event_id: str) -> None:
        self.orders_submitted += 1
        self.last_client_order_id = client_order_id
        self.last_decision_event_id = decision_event_id

    def disable(self, reason: str) -> None:
        if reason not in self.disable_reasons:
            self.disable_reasons.append(reason)
        self.disabled = True

    def reset_session(self, new_session_id: str, started_at_ms: int) -> None:
        if not new_session_id.strip():
            raise ValueError("new_session_id must be non-empty")
        if started_at_ms <= 0:
            raise ValueError("started_at_ms must be positive")
        self.session_id = new_session_id
        self.started_at_ms = started_at_ms
        self.orders_submitted = 0
        self.disabled = False
        self.disable_reasons = []
        self.last_decision_event_id = None
        self.last_client_order_id = None
