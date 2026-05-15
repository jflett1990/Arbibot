from arbibot.core.events import PolyBookSnapshot, SpotTick
from arbibot.features.feature_snapshot import build_feature_snapshot
from arbibot.features.spot import SpotFeatureWindow
from arbibot.market.book import LocalOrderBook


def _tick(ts: int, price: float) -> SpotTick:
    return SpotTick(
        event_id=f"t{ts}",
        source="binance",
        source_ts_ms=ts,
        recv_wall_ts_ms=ts + 1,
        recv_monotonic_ns=ts + 2,
        symbol="BTCUSDT",
        price=price,
        size=1.0,
        stream_event_type="trade",
    )


def test_feature_snapshot_with_and_without_book_and_staleness() -> None:
    spot = SpotFeatureWindow("BTCUSDT")
    spot.add_tick(_tick(1000, 100))
    spot.add_tick(_tick(2000, 110))

    snap_no_book = build_feature_snapshot(
        symbol="BTCUSDT",
        spot_window=spot,
        order_book=None,
        now_source_ts_ms=2100,
        recv_wall_ts_ms=3000,
        recv_monotonic_ns=4000,
    )
    assert snap_no_book.latest_price == 110.0
    assert snap_no_book.stale_spot is False
    assert snap_no_book.stale_book is True

    book = LocalOrderBook("tok")
    book.apply_snapshot(
        PolyBookSnapshot(
            event_id="s",
            source="poly",
            source_ts_ms=2050,
            recv_wall_ts_ms=2051,
            recv_monotonic_ns=2052,
            market_id="m",
            outcome="UP",
            token_id="tok",
            bids=[[0.5, 10]],
            asks=[[0.51, 10]],
        )
    )
    snap = build_feature_snapshot(
        symbol="BTCUSDT",
        spot_window=spot,
        order_book=book,
        now_source_ts_ms=2100,
        recv_wall_ts_ms=3000,
        recv_monotonic_ns=4000,
    )
    assert snap.stale_spot is False
    assert snap.stale_book is False
    assert snap.book_best_bid == 0.5
    assert snap.event_id == "feature:BTCUSDT:2100"

    stale = build_feature_snapshot(
        symbol="BTCUSDT",
        spot_window=spot,
        order_book=book,
        now_source_ts_ms=5000,
        recv_wall_ts_ms=3000,
        recv_monotonic_ns=4000,
    )
    assert stale.stale_spot is True
    assert stale.stale_book is True
