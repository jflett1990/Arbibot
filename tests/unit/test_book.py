from decimal import Decimal

import pytest

from arbibot.core.events import MarketSide, PolyBookDelta, PolyBookSnapshot
from arbibot.market.book import BookError, LocalOrderBook


def _snapshot(
    token_id: str = "tok-1",
    bids: list[list[float]] | None = None,
    asks: list[list[float]] | None = None,
    tick_size: float | None = None,
) -> PolyBookSnapshot:
    return PolyBookSnapshot(
        event_id="s1",
        source="poly",
        source_ts_ms=1000,
        recv_wall_ts_ms=1010,
        recv_monotonic_ns=1020,
        sequence_id="10",
        market_id="m1",
        outcome="UP",
        token_id=token_id,
        tick_size=tick_size,
        bids=[[0.45, 100], [0.44, 50]] if bids is None else bids,
        asks=[[0.55, 80], [0.56, 40]] if asks is None else asks,
    )


def _delta(
    side: MarketSide,
    price: float,
    size: float,
    token_id: str = "tok-1",
    tick_size: float | None = None,
) -> PolyBookDelta:
    return PolyBookDelta(
        event_id="d1",
        source="poly",
        source_ts_ms=2000,
        recv_wall_ts_ms=2010,
        recv_monotonic_ns=2020,
        sequence_id="11",
        market_id="m1",
        outcome="UP",
        token_id=token_id,
        side=side,
        price=price,
        size=size,
        tick_size=tick_size,
    )


def test_snapshot_replaces_existing_book_and_best_prices() -> None:
    book = LocalOrderBook("tok-1")
    book.apply_snapshot(_snapshot())
    assert book.best_bid() is not None
    assert book.best_bid().price == Decimal("0.45")
    assert book.best_ask().price == Decimal("0.55")
    assert book.mid() == Decimal("0.50")
    assert book.spread() == Decimal("0.10")

    book.apply_snapshot(_snapshot(bids=[[0.40, 10]], asks=[[0.60, 20]]))
    assert book.best_bid().price == Decimal("0.4")
    assert book.best_ask().price == Decimal("0.6")


def test_empty_book_behavior() -> None:
    book = LocalOrderBook("tok-1")
    book.apply_snapshot(_snapshot(bids=[], asks=[]))
    assert book.is_empty()
    assert book.best_bid() is None
    assert book.best_ask() is None
    assert book.mid() is None
    assert book.spread() is None
    assert book.imbalance() is None


@pytest.mark.parametrize(
    "bids,asks",
    [([[0.45, 0]], [[0.55, 1]]), ([[0.45, -1]], [[0.55, 1]]), ([[0, 1]], [[0.55, 1]])],
)
def test_snapshot_invalid_levels_raise(bids: list[list[float]], asks: list[list[float]]) -> None:
    book = LocalOrderBook("tok-1")
    with pytest.raises(BookError):
        book.apply_snapshot(_snapshot(bids=bids, asks=asks))


def test_snapshot_token_mismatch_raises() -> None:
    book = LocalOrderBook("tok-1")
    with pytest.raises(BookError):
        book.apply_snapshot(_snapshot(token_id="tok-2"))


def test_delta_insert_update_delete_and_missing_delete() -> None:
    book = LocalOrderBook("tok-1")
    book.apply_snapshot(_snapshot())

    book.apply_delta(_delta(MarketSide.BUY, 0.46, 25))
    assert book.best_bid().price == Decimal("0.46")

    book.apply_delta(_delta(MarketSide.SELL, 0.55, 120))
    assert book.best_ask().size == Decimal("120")

    book.apply_delta(_delta(MarketSide.BUY, 0.46, 0))
    assert book.best_bid().price == Decimal("0.45")

    book.apply_delta(_delta(MarketSide.BUY, 0.99, 0))
    assert book.best_bid().price == Decimal("0.45")


def test_delta_validation_and_ordering() -> None:
    book = LocalOrderBook("tok-1")
    book.apply_snapshot(_snapshot())

    with pytest.raises(BookError):
        book.apply_delta(_delta(MarketSide.BUY, 0.45, -1))
    with pytest.raises(BookError):
        book.apply_delta(_delta(MarketSide.BUY, 0, 1))
    with pytest.raises(BookError):
        book.apply_delta(_delta(MarketSide.BUY, 0.45, 1, token_id="tok-2"))

    book.apply_delta(_delta(MarketSide.BUY, 0.43, 10))
    book.apply_delta(_delta(MarketSide.BUY, 0.47, 10))
    bids = [level.price for level in book._ordered_ladder("bid")]
    assert bids == sorted(bids, reverse=True)


def test_analytics_depth_weighted_avg_imbalance_crossed() -> None:
    book = LocalOrderBook("tok-1")
    book.apply_snapshot(
        _snapshot(
            bids=[[0.50, 10], [0.49, 20], [0.48, 30]],
            asks=[[0.51, 10], [0.52, 20], [0.53, 30]],
        )
    )

    assert book.depth("bid", levels=2) == Decimal("30")
    assert book.depth("ask") == Decimal("60")
    assert book.depth_to_price("bid", Decimal("0.49")) == Decimal("30")
    assert book.depth_to_price("ask", Decimal("0.52")) == Decimal("30")

    wap_buy = book.weighted_avg_price("ask", Decimal("15"))
    assert wap_buy == Decimal("0.5133333333333333333333333333")
    assert book.weighted_avg_price("ask", Decimal("1000")) is None

    imbalance = book.imbalance(levels=2)
    assert imbalance == Decimal("0")

    book.apply_delta(_delta(MarketSide.BUY, 0.55, 1))
    assert book.is_crossed()


def test_tick_size_validation() -> None:
    book = LocalOrderBook("tok-1")
    book.apply_snapshot(_snapshot(tick_size=0.01))
    book.apply_delta(_delta(MarketSide.BUY, 0.47, 1))
    with pytest.raises(BookError):
        book.apply_delta(_delta(MarketSide.BUY, 0.471, 1))

    no_tick_book = LocalOrderBook("tok-1")
    no_tick_book.apply_snapshot(_snapshot(tick_size=None))
    no_tick_book.apply_delta(_delta(MarketSide.BUY, 0.471, 1))
    assert no_tick_book.best_bid().price == Decimal("0.471")


def test_deterministic_repeated_updates_no_decimal_drift() -> None:
    book1 = LocalOrderBook("tok-1")
    book2 = LocalOrderBook("tok-1")
    snapshot = _snapshot()
    book1.apply_snapshot(snapshot)
    book2.apply_snapshot(snapshot)

    for _ in range(100):
        book1.apply_delta(_delta(MarketSide.BUY, 0.45, 100.1))
        book2.apply_delta(_delta(MarketSide.BUY, 0.45, 100.1))

    assert book1.best_bid().size == book2.best_bid().size
    assert book1.depth("bid") == book2.depth("bid")
