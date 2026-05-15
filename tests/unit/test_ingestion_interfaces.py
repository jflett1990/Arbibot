import asyncio
from collections.abc import AsyncIterator

from arbibot.core.events import (
    BaseEvent,
    ExternalSignal,
    PolyBookDelta,
    PolyBookSnapshot,
    PolyTrade,
    SignalDirection,
    SpotTick,
)
from arbibot.ingestion.interfaces import (
    ExternalSignalClient,
    PredictionMarketDataClient,
    SpotMarketDataClient,
)
from arbibot.ingestion.mock_clients import (
    MockExternalSignalClient,
    MockPredictionMarketDataClient,
    MockSpotMarketDataClient,
)


async def _collect(stream: AsyncIterator[BaseEvent]) -> list[BaseEvent]:
    return [event async for event in stream]


def test_mock_spot_client_yields_only_spot_events() -> None:
    events = [
        SpotTick(
            event_id="s1",
            source="spot",
            source_ts_ms=1,
            recv_wall_ts_ms=2,
            recv_monotonic_ns=3,
            symbol="BTCUSDT",
            price=1.0,
        )
    ]
    client: SpotMarketDataClient = MockSpotMarketDataClient("spot", "BTCUSDT", events)
    emitted = asyncio.run(_collect(client.events()))
    assert all(isinstance(event, SpotTick) for event in emitted)


def test_mock_prediction_client_yields_only_prediction_events() -> None:
    events = [
        PolyBookSnapshot(
            event_id="p1",
            source="pred",
            source_ts_ms=10,
            recv_wall_ts_ms=11,
            recv_monotonic_ns=12,
            market_id="m1",
            outcome="UP",
        ),
        PolyBookDelta(
            event_id="p2",
            source="pred",
            source_ts_ms=13,
            recv_wall_ts_ms=14,
            recv_monotonic_ns=15,
            market_id="m1",
            outcome="UP",
            side="BUY",
            price=0.51,
            size=5.0,
        ),
        PolyTrade(
            event_id="p3",
            source="pred",
            source_ts_ms=16,
            recv_wall_ts_ms=17,
            recv_monotonic_ns=18,
            market_id="m1",
            outcome="UP",
            side="SELL",
            price=0.49,
            size=2.0,
        ),
    ]
    client: PredictionMarketDataClient = MockPredictionMarketDataClient("pred", "m1", "UP", events)
    emitted = asyncio.run(_collect(client.events()))
    assert len(emitted) == 3


def test_mock_external_client_yields_only_external_signals() -> None:
    events = [
        ExternalSignal(
            event_id="x1",
            source="ext",
            source_ts_ms=100,
            recv_wall_ts_ms=101,
            recv_monotonic_ns=102,
            provider="tv",
            direction=SignalDirection.BULL,
            ttl_ms=1000,
        )
    ]
    client: ExternalSignalClient = MockExternalSignalClient("ext", events)
    emitted = asyncio.run(_collect(client.events()))
    assert all(isinstance(event, ExternalSignal) for event in emitted)
