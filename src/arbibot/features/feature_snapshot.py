from __future__ import annotations

from decimal import Decimal

from arbibot.core.events import FeatureSnapshot
from arbibot.features.book import BookFeatureExtractor
from arbibot.features.spot import SpotFeatureWindow
from arbibot.market.book import LocalOrderBook


def _f(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def build_feature_snapshot(
    symbol: str,
    spot_window: SpotFeatureWindow,
    order_book: LocalOrderBook | None,
    now_source_ts_ms: int,
    recv_wall_ts_ms: int,
    recv_monotonic_ns: int,
    stale_spot_after_ms: int = 750,
    stale_book_after_ms: int = 1000,
) -> FeatureSnapshot:
    if now_source_ts_ms < 0:
        raise ValueError("now_source_ts_ms must be >= 0")
    if stale_spot_after_ms < 0 or stale_book_after_ms < 0:
        raise ValueError("stale thresholds must be >= 0")

    spot = spot_window.snapshot(now_source_ts_ms)
    latest_spot_ts = spot_window.latest_source_ts_ms()
    stale_spot = (
        latest_spot_ts is None
        or (now_source_ts_ms - latest_spot_ts) > stale_spot_after_ms
    )

    book_extractor: BookFeatureExtractor | None = None
    if order_book is not None:
        book_extractor = BookFeatureExtractor(order_book)

    book_age = (
        None
        if book_extractor is None
        else book_extractor.last_update_age_ms(now_source_ts_ms)
    )
    stale_book = book_age is None or book_age > stale_book_after_ms

    event_id = f"feature:{symbol}:{now_source_ts_ms}"

    return FeatureSnapshot(
        event_id=event_id,
        source="arbibot.feature_engine",
        source_ts_ms=now_source_ts_ms,
        recv_wall_ts_ms=recv_wall_ts_ms,
        recv_monotonic_ns=recv_monotonic_ns,
        feature_set="phase6",
        values={},
        symbol=symbol,
        latest_price=_f(spot["latest_price"]),
        return_250ms=_f(spot["return_250ms"]),
        return_500ms=_f(spot["return_500ms"]),
        return_1s=_f(spot["return_1s"]),
        return_2s=_f(spot["return_2s"]),
        return_5s=_f(spot["return_5s"]),
        return_10s=_f(spot["return_10s"]),
        realized_vol_5s=_f(spot["realized_vol_5s"]),
        realized_vol_30s=_f(spot["realized_vol_30s"]),
        momentum_slope_5s=_f(spot["momentum_slope_5s"]),
        acceleration_1s_2s=_f(spot["acceleration_1s_2s"]),
        book_best_bid=None if book_extractor is None else _f(book_extractor.best_bid()),
        book_best_ask=None if book_extractor is None else _f(book_extractor.best_ask()),
        book_mid=None if book_extractor is None else _f(book_extractor.mid()),
        book_spread=None if book_extractor is None else _f(book_extractor.spread()),
        book_depth_bid_3=None if book_extractor is None else _f(book_extractor.depth_bid(3)),
        book_depth_ask_3=None if book_extractor is None else _f(book_extractor.depth_ask(3)),
        book_imbalance_3=None if book_extractor is None else _f(book_extractor.imbalance(3)),
        book_is_crossed=None if book_extractor is None else book_extractor.is_crossed(),
        book_is_empty=None if book_extractor is None else book_extractor.is_empty(),
        book_last_update_age_ms=book_age,
        stale_spot=stale_spot,
        stale_book=stale_book,
    )
