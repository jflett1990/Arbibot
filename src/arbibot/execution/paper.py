from __future__ import annotations

from decimal import Decimal

from arbibot.core.events import OrderEvent, OrderIntent, OrderStatus
from arbibot.execution.interfaces import ExecutionSide, OrderType
from arbibot.market.book import LocalOrderBook


class PaperExecutionEngine:
    def __init__(
        self,
        allow_partial_fak: bool = True,
        allow_immediate_limit_cross: bool = False,
        fee_rate: Decimal = Decimal("0"),
        slippage_buffer: Decimal = Decimal("0"),
    ) -> None:
        self.allow_partial_fak = allow_partial_fak
        self.allow_immediate_limit_cross = allow_immediate_limit_cross
        self.fee_rate = fee_rate
        self.slippage_buffer = slippage_buffer

    def execute_buy(self, intent: OrderIntent, book: LocalOrderBook) -> list[OrderEvent]:
        if not intent.client_order_id:
            return [self._event(intent, OrderStatus.REJECTED, reason="MISSING_CLIENT_ORDER_ID")]
        if intent.side != ExecutionSide.BUY.value:
            return [self._event(intent, OrderStatus.REJECTED, reason="UNSUPPORTED_SIDE")]
        if intent.token_id != book.token_id:
            return [self._event(intent, OrderStatus.REJECTED, reason="TOKEN_MISMATCH")]
        if intent.size is None or intent.size <= 0:
            return [self._event(intent, OrderStatus.REJECTED, reason="INVALID_SIZE")]
        if intent.price_limit is None or intent.price_limit <= 0:
            return [self._event(intent, OrderStatus.REJECTED, reason="INVALID_PRICE_LIMIT")]

        typ = intent.order_type
        if typ not in {OrderType.FAK.value, OrderType.FOK.value, OrderType.LIMIT.value}:
            return [self._event(intent, OrderStatus.REJECTED, reason="UNSUPPORTED_ORDER_TYPE")]

        if typ == OrderType.LIMIT.value and not self.allow_immediate_limit_cross:
            return [self._event(intent, OrderStatus.SUBMITTED, reason="LIMIT_ACCEPTED_UNFILLED")]

        limit = Decimal(str(intent.price_limit))
        req_size = Decimal(str(intent.size))
        fillable = self._compute_fill(book, limit, req_size)
        if fillable["filled_size"] == 0:
            return [self._event(intent, OrderStatus.CANCELLED, reason="NO_FILL")]

        if typ == OrderType.FOK.value and fillable["filled_size"] < req_size:
            return [self._event(intent, OrderStatus.CANCELLED, reason="FOK_INSUFFICIENT_DEPTH")]

        if (
            typ == OrderType.FAK.value
            and fillable["filled_size"] < req_size
            and not self.allow_partial_fak
        ):
            return [self._event(intent, OrderStatus.CANCELLED, reason="FAK_PARTIAL_DISABLED")]

        status = (
            OrderStatus.FILLED
            if fillable["filled_size"] == req_size
            else OrderStatus.PARTIALLY_FILLED
        )
        return [
            self._event(
                intent,
                status,
                reason="FILLED" if status is OrderStatus.FILLED else "PARTIAL_FILL_EXPIRED",
                filled_size=fillable["filled_size"],
                avg_fill_price=fillable["avg_fill_price"],
            )
        ]

    def _compute_fill(
        self,
        book: LocalOrderBook,
        price_limit: Decimal,
        size: Decimal,
    ) -> dict[str, Decimal]:
        rem = size
        filled = Decimal("0")
        notional = Decimal("0")
        for level in book._ordered_ladder("ask"):
            if level.price > price_limit:
                continue
            take = min(level.size, rem)
            filled += take
            notional += take * level.price
            rem -= take
            if rem <= 0:
                break
        avg = Decimal("0") if filled == 0 else notional / filled
        return {"filled_size": filled, "avg_fill_price": avg}

    def _event(
        self,
        intent: OrderIntent,
        status: OrderStatus,
        reason: str,
        filled_size: Decimal = Decimal("0"),
        avg_fill_price: Decimal = Decimal("0"),
    ) -> OrderEvent:
        requested = Decimal(str(intent.size))
        remaining = requested - filled_size
        gross = filled_size * avg_fill_price
        fee = gross * self.fee_rate
        metadata: dict[str, str | int | float | bool | None] = {
            "gross_notional": float(gross),
            "fee": float(fee),
            "slippage_buffer": float(self.slippage_buffer),
            "requested_size": float(requested),
            "filled_size": float(filled_size),
            "avg_fill_price": float(avg_fill_price),
            "remaining_size": float(remaining),
        }
        eid = (
            f"order:{intent.client_order_id}:{status.value}:"
            f"{intent.source_ts_ms}:{float(filled_size)}"
        )
        return OrderEvent(
            event_id=eid,
            source="arbibot.paper_execution",
            source_ts_ms=intent.source_ts_ms,
            recv_wall_ts_ms=intent.recv_wall_ts_ms,
            recv_monotonic_ns=intent.recv_monotonic_ns,
            order_id=intent.client_order_id or "",
            status=status,
            client_order_id=intent.client_order_id,
            token_id=intent.token_id,
            requested_size=float(requested),
            filled_size=float(filled_size),
            avg_fill_price=float(avg_fill_price) if filled_size > 0 else None,
            remaining_size=float(remaining),
            reason=reason,
            metadata=metadata,
        )
