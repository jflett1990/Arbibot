"""Feature-friendly wrapper around LocalOrderBook analytics."""

from __future__ import annotations

from decimal import Decimal

from arbibot.market.book import LocalOrderBook, PriceLevel


class BookFeatureExtractor:
    def __init__(self, book: LocalOrderBook) -> None:
        self.book = book

    def best_bid(self) -> Decimal | None:
        level: PriceLevel | None = self.book.best_bid()
        return None if level is None else level.price

    def best_ask(self) -> Decimal | None:
        level: PriceLevel | None = self.book.best_ask()
        return None if level is None else level.price

    def mid(self) -> Decimal | None:
        return self.book.mid()

    def spread(self) -> Decimal | None:
        return self.book.spread()

    def depth_bid(self, levels: int = 3) -> Decimal:
        return self.book.depth("bid", levels=levels)

    def depth_ask(self, levels: int = 3) -> Decimal:
        return self.book.depth("ask", levels=levels)

    def depth_to_bid_price(self, limit_price: Decimal) -> Decimal:
        return self.book.depth_to_price("bid", limit_price)

    def depth_to_ask_price(self, limit_price: Decimal) -> Decimal:
        return self.book.depth_to_price("ask", limit_price)

    def weighted_avg_bid(self, size: Decimal) -> Decimal | None:
        return self.book.weighted_avg_price("bid", size)

    def weighted_avg_ask(self, size: Decimal) -> Decimal | None:
        return self.book.weighted_avg_price("ask", size)

    def imbalance(self, levels: int = 3) -> Decimal | None:
        return self.book.imbalance(levels)

    def is_crossed(self) -> bool:
        return self.book.is_crossed()

    def is_empty(self) -> bool:
        return self.book.is_empty()

    def last_update_age_ms(self, now_source_ts_ms: int) -> int | None:
        if now_source_ts_ms < 0:
            raise ValueError("now_source_ts_ms must be >= 0")
        if self.book.last_update_source_ts_ms is None:
            return None
        return now_source_ts_ms - self.book.last_update_source_ts_ms
