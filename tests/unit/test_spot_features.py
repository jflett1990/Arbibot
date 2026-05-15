from decimal import Decimal

import pytest

from arbibot.core.errors import EventValidationError
from arbibot.core.events import SpotTick
from arbibot.features.spot import SpotFeatureWindow


def _tick(
    ts: int, price: float, size: float, typ: str | None = "trade", sym: str = "BTCUSDT"
) -> SpotTick:
    return SpotTick(
        event_id=f"t-{ts}",
        source="binance",
        source_ts_ms=ts,
        recv_wall_ts_ms=ts + 1,
        recv_monotonic_ns=ts + 2,
        symbol=sym,
        price=price,
        size=size,
        stream_event_type=typ,
    )


def test_spot_features_core_behaviors() -> None:
    w = SpotFeatureWindow("BTCUSDT", max_window_ms=10_000)
    w.add_tick(_tick(1000, 100, 1, "bookTicker"))
    assert w.latest_price() is None

    w.add_tick(_tick(1000, 100, 1))
    w.add_tick(_tick(2000, 110, 1))
    assert w.latest_price() == Decimal("110.0")
    assert w.return_over_ms(1000) == Decimal("0.1")
    assert w.return_over_ms(5000) is None
    assert w.realized_volatility_ms(1000) is None

    w.add_tick(_tick(3000, 121, 1))
    assert w.realized_volatility_ms(3000) is not None
    assert w.momentum_slope_ms(3000) > 0
    assert w.acceleration(1000, 2000) is not None
    assert w.distance_to_threshold(Decimal("120")) == Decimal("1.0")


def test_spot_validation_and_pruning() -> None:
    with pytest.raises(ValueError):
        SpotFeatureWindow("BTCUSDT", max_window_ms=0)

    w = SpotFeatureWindow("BTCUSDT", max_window_ms=1000)
    with pytest.raises(EventValidationError):
        w.add_tick(_tick(1000, 100, 1, sym="ETHUSDT"))
    with pytest.raises(EventValidationError):
        w.add_tick(_tick(1000, 0, 1))
    with pytest.raises(EventValidationError):
        w.add_tick(_tick(1000, 100, 0))
    with pytest.raises(ValueError):
        w.return_over_ms(0)

    w.add_tick(_tick(1000, 100, 1))
    w.add_tick(_tick(2500, 101, 1))
    w.add_tick(_tick(3500, 102, 1))
    assert w.latest_source_ts_ms() == 3500
    assert w.return_over_ms(2500) is None
