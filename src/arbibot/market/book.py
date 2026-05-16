"""Deterministic local order-book reconstruction for prediction-market tokens."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from arbibot.core.errors import EventValidationError
from arbibot.core.events import BookLevel, BookSide, MarketSide, PolyBookDelta, PolyBookSnapshot


class BookError(EventValidationError):
    """Raised when local order-book operations fail validation."""


@dataclass(frozen=True, slots=True)
class PriceLevel:
    price: Decimal
    size: Decimal


class LocalOrderBook:
    def __init__(self, token_id: str) -> None:
        if not token_id:
            raise BookError("token_id must not be empty")
        self.token_id = token_id
        self.bids: dict[Decimal, Decimal] = {}
        self.asks: dict[Decimal, Decimal] = {}
        self.last_update_source_ts_ms: int | None = None
        self.last_update_recv_wall_ts_ms: int | None = None
        self.last_update_recv_monotonic_ns: int | None = None
        self.sequence_id: str | None = None
        self.tick_size: Decimal | None = None

    def apply_snapshot(self, event: PolyBookSnapshot) -> None:
        self._validate_token(event.token_id)
        snapshot_tick_size = self._coerce_optional_decimal(event.tick_size)
        if snapshot_tick_size is not None and snapshot_tick_size <= 0:
            raise BookError(f"tick_size must be > 0, got {snapshot_tick_size}")

        bids = self._levels_to_map(event.bids, allow_zero_size=False, tick_size=snapshot_tick_size)
        asks = self._levels_to_map(event.asks, allow_zero_size=False, tick_size=snapshot_tick_size)

        self.bids = bids
        self.asks = asks
        self.tick_size = snapshot_tick_size if snapshot_tick_size is not None else self.tick_size
        self._update_meta(
            event.source_ts_ms,
            event.recv_wall_ts_ms,
            event.recv_monotonic_ns,
            event.sequence_id,
        )

    def apply_delta(self, event: PolyBookDelta) -> None:
        self._validate_token(event.token_id)
        if event.price <= 0:
            raise BookError(f"Delta price must be > 0, got {event.price}")
        if event.size < 0:
            raise BookError(f"Delta size must be >= 0, got {event.size}")

        if event.tick_size is not None:
            tick_size = self._coerce_decimal(event.tick_size, "tick_size")
            if tick_size <= 0:
                raise BookError(f"tick_size must be > 0, got {tick_size}")
            self.tick_size = tick_size

        price = self._coerce_decimal(event.price, "price")
        size = self._coerce_decimal(event.size, "size")

        if not self.price_conforms_to_tick(price):
            raise BookError(f"Price {price} does not conform to tick_size {self.tick_size}")

        resolved = event.book_side
        if resolved is None:
            if event.side is MarketSide.BUY:
                resolved = BookSide.BID
            elif event.side is MarketSide.SELL:
                resolved = BookSide.ASK
            else:
                raise BookError("Delta requires book_side or legacy side")

        if resolved is BookSide.BID:
            book = self.bids
        elif resolved is BookSide.ASK:
            book = self.asks
        else:
            raise BookError(f"Invalid book side: {resolved}")

        if size == 0:
            book.pop(price, None)
        else:
            book[price] = size

        self._update_meta(
            event.source_ts_ms,
            event.recv_wall_ts_ms,
            event.recv_monotonic_ns,
            event.sequence_id,
        )

    def price_conforms_to_tick(self, price: Decimal) -> bool:
        if self.tick_size is None:
            return True
        if self.tick_size <= 0:
            return False
        ratio = price / self.tick_size
        return ratio == ratio.to_integral_value()

    def best_bid(self) -> PriceLevel | None:
        if not self.bids:
            return None
        price = max(self.bids)
        return PriceLevel(price=price, size=self.bids[price])

    def best_ask(self) -> PriceLevel | None:
        if not self.asks:
            return None
        price = min(self.asks)
        return PriceLevel(price=price, size=self.asks[price])

    def mid(self) -> Decimal | None:
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return (bid.price + ask.price) / Decimal("2")

    def spread(self) -> Decimal | None:
        bid = self.best_bid()
        ask = self.best_ask()
        if bid is None or ask is None:
            return None
        return ask.price - bid.price

    def depth(self, side: Literal["bid", "ask"], levels: int | None = None) -> Decimal:
        ladder = self._ordered_ladder(side)
        if levels is not None:
            ladder = ladder[:levels]
        return sum((level.size for level in ladder), start=Decimal("0"))

    def depth_to_price(self, side: Literal["bid", "ask"], limit_price: Decimal) -> Decimal:
        total = Decimal("0")
        for level in self._ordered_ladder(side):
            if side == "bid" and level.price < limit_price:
                continue
            if side == "ask" and level.price > limit_price:
                continue
            total += level.size
        return total

    def weighted_avg_price(self, side: Literal["bid", "ask"], size: Decimal) -> Decimal | None:
        if size <= 0:
            raise BookError(f"size must be > 0, got {size}")
        remaining = size
        notional = Decimal("0")

        for level in self._ordered_ladder(side):
            take = min(level.size, remaining)
            notional += take * level.price
            remaining -= take
            if remaining == 0:
                return notional / size
        return None

    def imbalance(self, levels: int = 3) -> Decimal | None:
        bid_depth = self.depth("bid", levels=levels)
        ask_depth = self.depth("ask", levels=levels)
        denom = bid_depth + ask_depth
        if denom == 0:
            return None
        return (bid_depth - ask_depth) / denom

    def is_crossed(self) -> bool:
        bid = self.best_bid()
        ask = self.best_ask()
        return bid is not None and ask is not None and bid.price >= ask.price

    def is_empty(self) -> bool:
        return not self.bids and not self.asks

    def _ordered_ladder(self, side: Literal["bid", "ask"]) -> list[PriceLevel]:
        if side == "bid":
            return [
                PriceLevel(price, self.bids[price])
                for price in sorted(self.bids, reverse=True)
            ]
        if side == "ask":
            return [PriceLevel(price, self.asks[price]) for price in sorted(self.asks)]
        raise BookError(f"Invalid side: {side}")

    def _levels_to_map(
        self,
        levels: list[BookLevel],
        allow_zero_size: bool,
        tick_size: Decimal | None,
    ) -> dict[Decimal, Decimal]:
        result: dict[Decimal, Decimal] = {}
        for raw in levels:
            price = self._coerce_decimal(raw.price, "price")
            size = self._coerce_decimal(raw.size, "size")
            if price <= 0:
                raise BookError(f"Snapshot price must be > 0, got {price}")
            if size < 0:
                raise BookError(f"Snapshot size must be >= 0, got {size}")
            if size == 0 and not allow_zero_size:
                raise BookError("Snapshot size must be > 0")
            if tick_size is not None:
                prev_tick = self.tick_size
                self.tick_size = tick_size
                is_valid_tick = self.price_conforms_to_tick(price)
                self.tick_size = prev_tick
                if not is_valid_tick:
                    raise BookError(f"Price {price} does not conform to tick_size {tick_size}")
            result[price] = size
        return result

    def _validate_token(self, event_token_id: str | None) -> None:
        if event_token_id is None or not event_token_id.strip():
            raise BookError("Event token_id is required")
        if event_token_id != self.token_id:
            raise BookError(f"Token mismatch: expected {self.token_id}, got {event_token_id}")

    def _update_meta(
        self,
        source_ts_ms: int,
        recv_wall_ts_ms: int,
        recv_monotonic_ns: int,
        sequence_id: str | None,
    ) -> None:
        self.last_update_source_ts_ms = source_ts_ms
        self.last_update_recv_wall_ts_ms = recv_wall_ts_ms
        self.last_update_recv_monotonic_ns = recv_monotonic_ns
        self.sequence_id = sequence_id

    def _coerce_decimal(self, value: float | int | str, field_name: str) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception as exc:  # noqa: BLE001
            raise BookError(f"Invalid decimal {field_name}: {value}") from exc

    def _coerce_optional_decimal(self, value: float | None) -> Decimal | None:
        if value is None:
            return None
        return self._coerce_decimal(value, "tick_size")
