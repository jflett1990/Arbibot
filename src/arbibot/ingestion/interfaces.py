"""Vendor-neutral ingestion interfaces for internal event streaming."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from arbibot.core.events import BaseEvent
from arbibot.storage.event_store import EventStore


class SpotMarketDataClient(Protocol):
    source: str
    symbol: str

    async def start(self) -> None:
        """Start the client lifecycle."""

    async def stop(self) -> None:
        """Stop the client lifecycle."""

    def events(self) -> AsyncIterator[BaseEvent]:
        """Yield normalized spot-market events."""


class PredictionMarketDataClient(Protocol):
    source: str
    market_id: str
    outcome: str

    async def start(self) -> None:
        """Start the client lifecycle."""

    async def stop(self) -> None:
        """Stop the client lifecycle."""

    def events(self) -> AsyncIterator[BaseEvent]:
        """Yield normalized prediction-market events."""


class ExternalSignalClient(Protocol):
    source: str

    async def start(self) -> None:
        """Start the client lifecycle."""

    async def stop(self) -> None:
        """Stop the client lifecycle."""

    def events(self) -> AsyncIterator[BaseEvent]:
        """Yield normalized external signal events."""


class EventStreamClient(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def events(self) -> AsyncIterator[BaseEvent]: ...


async def persist_stream(
    client: EventStreamClient,
    store: EventStore,
    limit: int | None = None,
) -> int:
    """Consume a client stream and append events to a store.

    Returns the number of persisted events.
    """
    if limit is not None and limit < 0:
        raise ValueError("limit must be >= 0")

    count = 0
    await client.start()
    try:
        async for event in client.events():
            store.append(event)
            count += 1
            if limit is not None and count >= limit:
                break
    finally:
        await client.stop()
    return count
