import pytest

from arbibot.core.errors import EventValidationError
from arbibot.core.events import SpotBar, SpotTick
from arbibot.market.candles import CandleBuilder, is_trade_like_tick


def _tick(
    event_id: str,
    ts: int,
    price: float,
    size: float,
    stream_event_type: str | None = "trade",
) -> SpotTick:
    return SpotTick(
        event_id=event_id,
        source="binance",
        source_ts_ms=ts,
        recv_wall_ts_ms=ts + 10,
        recv_monotonic_ns=ts * 1000,
        sequence_id=event_id,
        symbol="BTCUSDT",
        price=price,
        size=size,
        stream_event_type=stream_event_type,
    )


def test_one_tick_creates_open_candle() -> None:
    builder = CandleBuilder(interval_ms=1000)
    bars = builder.add_tick(_tick("t1", 100, 10, 2))
    assert bars == []


def test_same_bucket_updates_ohlcv() -> None:
    builder = CandleBuilder(interval_ms=1000)
    builder.add_tick(_tick("t1", 100, 10, 2))
    builder.add_tick(_tick("t2", 200, 12, 1))
    builder.add_tick(_tick("t3", 300, 9, 3))
    flushed = builder.flush()
    bar = flushed[0]
    assert bar.open == 10
    assert bar.high == 12
    assert bar.low == 9
    assert bar.close == 9
    assert bar.volume == 6
    assert bar.trade_count == 3


def test_multiple_buckets_emit_finalized() -> None:
    builder = CandleBuilder(interval_ms=1000, allowed_lateness_ms=0)
    assert builder.add_tick(_tick("t1", 100, 10, 1)) == []
    emitted = builder.add_tick(_tick("t2", 1200, 11, 1))
    assert len(emitted) == 1
    assert emitted[0].start_ts_ms == 0


def test_boundary_tick_goes_to_next_bucket() -> None:
    builder = CandleBuilder(interval_ms=1000, allowed_lateness_ms=0)
    builder.add_tick(_tick("t1", 999, 10, 1))
    emitted = builder.add_tick(_tick("t2", 1000, 11, 1))
    assert len(emitted) == 1
    assert emitted[0].start_ts_ms == 0
    remaining = builder.flush()
    assert remaining[0].start_ts_ms == 1000


def test_trade_filtering() -> None:
    assert is_trade_like_tick(_tick("a", 1, 1, 1, "aggTrade"))
    assert is_trade_like_tick(_tick("b", 1, 1, 1, "trade"))
    assert not is_trade_like_tick(_tick("c", 1, 1, 1, "bookTicker"))


def test_non_trade_ignored_by_default() -> None:
    builder = CandleBuilder(interval_ms=1000)
    emitted = builder.add_tick(_tick("t1", 100, 10, 1, stream_event_type="bookTicker"))
    assert emitted == []
    assert builder.flush() == []


def test_non_trade_raises_when_configured() -> None:
    builder = CandleBuilder(interval_ms=1000, ignore_non_trade_ticks=False)
    with pytest.raises(EventValidationError):
        builder.add_tick(_tick("t1", 100, 10, 1, stream_event_type="unknown"))


def test_out_of_order_within_lateness_updates() -> None:
    builder = CandleBuilder(interval_ms=1000, allowed_lateness_ms=300)
    builder.add_tick(_tick("t1", 1900, 11, 1))
    builder.add_tick(_tick("t2", 1100, 10, 2))
    bars = builder.flush()
    first = [b for b in bars if b.start_ts_ms == 1000][0]
    assert first.volume == 3


def test_too_late_tick_ignored() -> None:
    builder = CandleBuilder(interval_ms=1000, allowed_lateness_ms=0)
    builder.add_tick(_tick("t1", 100, 10, 1))
    builder.add_tick(_tick("t2", 2500, 11, 1))
    emitted = builder.add_tick(_tick("t3", 500, 12, 1))
    assert emitted == []


def test_deterministic_output_same_sequence() -> None:
    seq = [_tick("t1", 100, 10, 1), _tick("t2", 1200, 11, 2), _tick("t3", 1300, 9, 1)]
    b1 = CandleBuilder(interval_ms=1000, allowed_lateness_ms=0)
    out1: list[SpotBar] = []
    for tick in seq:
        out1.extend(b1.add_tick(tick))
    out1.extend(b1.flush())

    b2 = CandleBuilder(interval_ms=1000, allowed_lateness_ms=0)
    out2: list[SpotBar] = []
    for tick in seq:
        out2.extend(b2.add_tick(tick))
    out2.extend(b2.flush())

    assert [bar.model_dump() for bar in out1] == [bar.model_dump() for bar in out2]


def test_event_id_stable() -> None:
    builder = CandleBuilder(interval_ms=1000, allowed_lateness_ms=0)
    builder.add_tick(_tick("t1", 100, 10, 1))
    bar = builder.add_tick(_tick("t2", 1100, 11, 1))[0]
    assert bar.event_id == "bar:BTCUSDT:1000:0:1000"


def test_invalid_builder_config_and_tick_values() -> None:
    with pytest.raises(ValueError):
        CandleBuilder(interval_ms=0)
    with pytest.raises(ValueError):
        CandleBuilder(allowed_lateness_ms=-1)

    builder = CandleBuilder(interval_ms=1000)
    for bad in [
        _tick("p", 1, -1, 1),
        _tick("s", 1, 1, 0),
    ]:
        with pytest.raises(EventValidationError):
            builder.add_tick(bad)
