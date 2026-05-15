"""Deterministic mock ingestion clients for tests and local development."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from arbibot.core.errors import EventValidationError
from arbibot.core.events import (
    BaseEvent,
    ExternalSignal,
    PolyBookDelta,
    PolyBookSnapshot,
    PolyTrade,
    SpotBar,
    SpotTick,
)
from arbibot.ingestion.interfaces import (
    ExternalSignalClient,
    PredictionMarketDataClient,
    SpotMarketDataClient,
)


class _BaseMockClient:
    def __init__(self, events: Sequence[BaseEvent], delay_ms: int = 0) -> None:
        if delay_ms < 0:
            raise ValueError("delay_ms must be >= 0")
        self._events: tuple[BaseEvent, ...] = tuple(events)
        self._delay_s = delay_ms / 1000.0
        self._stopped = False
        self._started = False

    async def start(self) -> None:
        self._started = True
        self._stopped = False

    async def stop(self) -> None:
        self._stopped = True

    async def events(self) -> AsyncIterator[BaseEvent]:
        if not self._started:
            await self.start()

        for event in self._events:
            if self._stopped:
                break
            if self._delay_s > 0:
                await asyncio.sleep(self._delay_s)
            if self._stopped:
                break
            yield event


class MockSpotMarketDataClient(_BaseMockClient, SpotMarketDataClient):
    def __init__(
        self,
        source: str,
        symbol: str,
        events: Sequence[BaseEvent],
        delay_ms: int = 0,
    ) -> None:
        self.source = source
        self.symbol = symbol
        _validate_events(events, (SpotTick, SpotBar), "spot")
        super().__init__(events=events, delay_ms=delay_ms)


class MockPredictionMarketDataClient(_BaseMockClient, PredictionMarketDataClient):
    def __init__(
        self,
        source: str,
        market_id: str,
        outcome: str,
        events: Sequence[BaseEvent],
        delay_ms: int = 0,
    ) -> None:
        self.source = source
        self.market_id = market_id
        self.outcome = outcome
        _validate_events(events, (PolyBookSnapshot, PolyBookDelta, PolyTrade), "prediction")
        super().__init__(events=events, delay_ms=delay_ms)


class MockExternalSignalClient(_BaseMockClient, ExternalSignalClient):
    def __init__(self, source: str, events: Sequence[BaseEvent], delay_ms: int = 0) -> None:
        self.source = source
        _validate_events(events, (ExternalSignal,), "external")
        super().__init__(events=events, delay_ms=delay_ms)


def _validate_events(
    events: Sequence[BaseEvent], allowed_types: tuple[type[BaseEvent], ...], client_name: str
) -> None:
    for event in events:
        if not isinstance(event, allowed_types):
            allowed = ", ".join(event_type.__name__ for event_type in allowed_types)
            raise EventValidationError(
                "Invalid event type for "
                f"{client_name} client: {type(event).__name__}; "
                f"allowed: {allowed}"
            )
