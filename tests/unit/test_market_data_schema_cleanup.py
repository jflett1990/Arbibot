from decimal import Decimal

import pytest
from pydantic import ValidationError

from arbibot.core.events import (
    BookLevel,
    BookSide,
    MarketSide,
    PolyBookDelta,
    PolyBookSnapshot,
    SpotBookTicker,
    SpotTick,
)
from arbibot.features.spot import SpotFeatureWindow
from arbibot.market.book import BookError, LocalOrderBook
from arbibot.market.candles import CandleBuilder


def _delta(**updates: object) -> PolyBookDelta:
    base = {
        "event_id": "d1",
        "source": "poly",
        "source_ts_ms": 1,
        "recv_wall_ts_ms": 2,
        "recv_monotonic_ns": 3,
        "market_id": "m",
        "outcome": "UP",
        "token_id": "tok",
        "price": 0.5,
        "size": 1.0,
    }
    base.update(updates)
    return PolyBookDelta.model_validate(base)


def test_book_side_and_legacy_side_compatibility() -> None:
    b = LocalOrderBook("tok")
    b.apply_snapshot(
        PolyBookSnapshot(
            event_id="s",
            source="x",
            source_ts_ms=1,
            recv_wall_ts_ms=2,
            recv_monotonic_ns=3,
            market_id="m",
            outcome="UP",
            token_id="tok",
            bids=[[0.4, 1]],
            asks=[[0.6, 1]],
        )
    )
    b.apply_delta(_delta(book_side=BookSide.BID, price=0.45, size=2))
    assert b.best_bid().price == Decimal("0.45")
    b.apply_delta(_delta(book_side=BookSide.ASK, price=0.55, size=2))
    assert b.best_ask().price == Decimal("0.55")
    b.apply_delta(_delta(side=MarketSide.BUY, price=0.46, size=2))
    assert b.best_bid().price == Decimal("0.46")
    b.apply_delta(_delta(side=MarketSide.SELL, price=0.54, size=2))
    assert b.best_ask().price == Decimal("0.54")
    with pytest.raises(BookError):
        b.apply_delta(_delta(side=None, book_side=None))


def test_book_level_and_ticker_behavior() -> None:
    snap = PolyBookSnapshot(
        event_id="s",
        source="x",
        source_ts_ms=1,
        recv_wall_ts_ms=2,
        recv_monotonic_ns=3,
        market_id="m",
        outcome="UP",
        token_id="tok",
        bids=[["0.4", "2"], BookLevel(price=0.39, size=1)],
        asks=[["0.6", "2"]],
    )
    assert isinstance(snap.bids[0], BookLevel)
    with pytest.raises(ValidationError):
        PolyBookSnapshot(
            event_id="s2",
            source="x",
            source_ts_ms=1,
            recv_wall_ts_ms=2,
            recv_monotonic_ns=3,
            market_id="m",
            outcome="UP",
            token_id="tok",
            bids=[[0.4]],
            asks=[],
        )

    ticker = SpotBookTicker(
        event_id="q1",
        source="binance",
        source_ts_ms=1,
        recv_wall_ts_ms=2,
        recv_monotonic_ns=3,
        symbol="BTCUSDT",
        bid_price=1,
        bid_size=0,
        ask_price=1.1,
        ask_size=0,
    )
    assert ticker.stream_event_type == "bookTicker"


def test_ticker_not_used_in_trade_windows() -> None:
    candle = CandleBuilder(interval_ms=1000)
    spot = SpotFeatureWindow("BTCUSDT")
    tick = SpotTick(
        event_id="t1",
        source="binance",
        source_ts_ms=1,
        recv_wall_ts_ms=2,
        recv_monotonic_ns=3,
        symbol="BTCUSDT",
        price=100.0,
        size=1.0,
        stream_event_type="trade",
    )
    assert candle.add_tick(tick) == []
    spot.add_tick(tick)

    quote_like = SpotTick(
        event_id="q",
        source="binance",
        source_ts_ms=2,
        recv_wall_ts_ms=3,
        recv_monotonic_ns=4,
        symbol="BTCUSDT",
        price=101.0,
        size=1.0,
        stream_event_type="bookTicker",
    )
    assert candle.add_tick(quote_like) == []
    spot.add_tick(quote_like)
    assert spot.latest_price() == Decimal("100.0")
