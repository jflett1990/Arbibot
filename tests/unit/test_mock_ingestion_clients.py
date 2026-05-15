import asyncio

import pytest

from arbibot.core.errors import EventValidationError
from arbibot.core.events import ExternalSignal, PolyBookSnapshot, SignalDirection, SpotBar, SpotTick
from arbibot.ingestion.interfaces import persist_stream
from arbibot.ingestion.mock_clients import (
    MockExternalSignalClient,
    MockPredictionMarketDataClient,
    MockSpotMarketDataClient,
)
from arbibot.storage.sqlite_store import SQLiteEventStore


def test_mock_spot_client_rejects_prediction_event() -> None:
    with pytest.raises(EventValidationError):
        MockSpotMarketDataClient(
            source="spot",
            symbol="BTCUSDT",
            events=[
                PolyBookSnapshot(
                    event_id="p1",
                    source="pred",
                    source_ts_ms=1,
                    recv_wall_ts_ms=2,
                    recv_monotonic_ns=3,
                    market_id="m1",
                    outcome="UP",
                )
            ],
        )


def test_mock_prediction_client_rejects_spot_event() -> None:
    with pytest.raises(EventValidationError):
        MockPredictionMarketDataClient(
            source="pred",
            market_id="m1",
            outcome="UP",
            events=[
                SpotTick(
                    event_id="s1",
                    source="spot",
                    source_ts_ms=1,
                    recv_wall_ts_ms=2,
                    recv_monotonic_ns=3,
                    symbol="BTCUSDT",
                    price=1.0,
                )
            ],
        )


def test_mock_external_client_rejects_spot_event() -> None:
    with pytest.raises(EventValidationError):
        MockExternalSignalClient(
            source="ext",
            events=[
                SpotTick(
                    event_id="s1",
                    source="spot",
                    source_ts_ms=1,
                    recv_wall_ts_ms=2,
                    recv_monotonic_ns=3,
                    symbol="BTCUSDT",
                    price=1.0,
                )
            ],
        )


def test_events_emit_in_provided_order_and_delay_keeps_order() -> None:
    events = [
        SpotTick(
            event_id="s1",
            source="spot",
            source_ts_ms=1,
            recv_wall_ts_ms=2,
            recv_monotonic_ns=3,
            symbol="BTCUSDT",
            price=1.0,
        ),
        SpotBar(
            event_id="b1",
            source="spot",
            source_ts_ms=4,
            recv_wall_ts_ms=5,
            recv_monotonic_ns=6,
            symbol="BTCUSDT",
            open=1.0,
            high=2.0,
            low=0.5,
            close=1.5,
            volume=10.0,
        ),
    ]
    client = MockSpotMarketDataClient("spot", "BTCUSDT", events, delay_ms=1)
    emitted = asyncio.run(_consume_ids(client))
    assert emitted == ["s1", "b1"]


def test_stop_halts_iteration() -> None:
    events = [
        SpotTick(
            event_id="s1",
            source="spot",
            source_ts_ms=1,
            recv_wall_ts_ms=2,
            recv_monotonic_ns=3,
            symbol="BTCUSDT",
            price=1.0,
        ),
        SpotTick(
            event_id="s2",
            source="spot",
            source_ts_ms=4,
            recv_wall_ts_ms=5,
            recv_monotonic_ns=6,
            symbol="BTCUSDT",
            price=2.0,
        ),
    ]
    client = MockSpotMarketDataClient("spot", "BTCUSDT", events, delay_ms=20)
    ids = asyncio.run(_stop_and_consume(client))
    assert len(ids) <= 1


async def _consume_ids(client: MockSpotMarketDataClient) -> list[str]:
    return [event.event_id async for event in client.events()]


async def _stop_and_consume(client: MockSpotMarketDataClient) -> list[str]:
    task = asyncio.create_task(_consume_ids(client))
    await asyncio.sleep(0.01)
    await client.stop()
    return await task


def test_persist_stream_stores_events(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    try:
        events = [
            SpotTick(
                event_id="s1",
                source="spot",
                source_ts_ms=1,
                recv_wall_ts_ms=2,
                recv_monotonic_ns=3,
                symbol="BTCUSDT",
                price=1.0,
            ),
            SpotTick(
                event_id="s2",
                source="spot",
                source_ts_ms=4,
                recv_wall_ts_ms=5,
                recv_monotonic_ns=6,
                symbol="BTCUSDT",
                price=2.0,
            ),
        ]
        client = MockSpotMarketDataClient("spot", "BTCUSDT", events)
        persisted = asyncio.run(persist_stream(client, store))
        assert persisted == 2
        rows = list(store.iter_events())
        assert [row.event_id for row in rows] == ["s1", "s2"]
        assert all(row.event_type == "SpotTick" for row in rows)
    finally:
        store.close()


def test_persist_stream_limit(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    try:
        events = [
            ExternalSignal(
                event_id="x1",
                source="ext",
                source_ts_ms=1,
                recv_wall_ts_ms=2,
                recv_monotonic_ns=3,
                provider="tv",
                direction=SignalDirection.BULL,
            ),
            ExternalSignal(
                event_id="x2",
                source="ext",
                source_ts_ms=4,
                recv_wall_ts_ms=5,
                recv_monotonic_ns=6,
                provider="tv",
                direction=SignalDirection.BEAR,
            ),
        ]
        client = MockExternalSignalClient("ext", events)
        persisted = asyncio.run(persist_stream(client, store, limit=1))
        assert persisted == 1
        rows = list(store.iter_events())
        assert len(rows) == 1
        assert rows[0].event_id == "x1"
    finally:
        store.close()
