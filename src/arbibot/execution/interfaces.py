from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from arbibot.core.events import OrderEvent, OrderIntent


class OrderType(StrEnum):
    FAK = "FAK"
    FOK = "FOK"
    LIMIT = "LIMIT"


class ExecutionSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ExecutionClient(Protocol):
    def submit_order(self, intent: OrderIntent) -> OrderEvent:
        """Submit an order intent and return resulting order event."""

    def cancel_order(self, client_order_id: str) -> OrderEvent:
        """Cancel a single order by client order id."""

    def cancel_all(self, market_id: str | None = None) -> list[OrderEvent]:
        """Cancel all open orders, optionally scoped by market."""

    def get_open_orders(self) -> list[OrderEvent]:
        """Return current open-order events."""

    def get_order_status(self, client_order_id: str) -> OrderEvent | None:
        """Return latest known order status event for a client order id."""
