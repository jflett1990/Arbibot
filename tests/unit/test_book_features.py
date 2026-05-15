from decimal import Decimal

from arbibot.core.events import MarketSide, PolyBookDelta, PolyBookSnapshot
from arbibot.features.book import BookFeatureExtractor
from arbibot.market.book import LocalOrderBook


def _setup_book() -> LocalOrderBook:
    b = LocalOrderBook("tok")
    b.apply_snapshot(
        PolyBookSnapshot(
            event_id="s",
            source="poly",
            source_ts_ms=1000,
            recv_wall_ts_ms=1001,
            recv_monotonic_ns=1002,
            market_id="m",
            outcome="UP",
            token_id="tok",
            bids=[[0.5, 10], [0.49, 20]],
            asks=[[0.51, 15], [0.52, 30]],
        )
    )
    return b


def test_book_feature_extractor_methods() -> None:
    b = _setup_book()
    f = BookFeatureExtractor(b)
    assert f.best_bid() == Decimal("0.5")
    assert f.best_ask() == Decimal("0.51")
    assert f.mid() == Decimal("0.505")
    assert f.spread() == Decimal("0.01")
    assert f.depth_bid(1) == Decimal("10")
    assert f.depth_ask(2) == Decimal("45")
    assert f.weighted_avg_bid(Decimal("5")) is not None
    assert f.weighted_avg_ask(Decimal("5")) is not None
    assert f.imbalance(2) is not None
    assert not f.is_crossed()
    assert not f.is_empty()
    assert f.last_update_age_ms(2000) == 1000

    b2 = LocalOrderBook("tok")
    f2 = BookFeatureExtractor(b2)
    assert f2.last_update_age_ms(2000) is None

    b.apply_delta(
        PolyBookDelta(
            event_id="d",
            source="poly",
            source_ts_ms=3000,
            recv_wall_ts_ms=3001,
            recv_monotonic_ns=3002,
            market_id="m",
            outcome="UP",
            token_id="tok",
            side=MarketSide.BUY,
            price=0.53,
            size=1,
        )
    )
    assert f.is_crossed()
