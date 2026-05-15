"""Storage interface and record types for append-only event persistence."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from arbibot.core.events import BaseEvent


@dataclass(frozen=True, slots=True)
class StoredEvent:
    event_id: str
    event_type: str
    source: str
    source_ts_ms: int
    recv_wall_ts_ms: int
    recv_monotonic_ns: int
    inserted_at_wall_ts_ms: int
    payload_json: str


class EventStore(Protocol):
    def append(self, event: BaseEvent) -> None:
        """Append a single event."""

    def append_many(self, events: Sequence[BaseEvent]) -> None:
        """Append multiple events atomically."""

    def get_event(self, event_id: str) -> StoredEvent | None:
        """Return one event by event id."""

    def iter_events(
        self,
        start_ts_ms: int | None = None,
        end_ts_ms: int | None = None,
        event_types: Sequence[str] | None = None,
    ) -> Iterator[StoredEvent]:
        """Iterate events in deterministic replay order."""
