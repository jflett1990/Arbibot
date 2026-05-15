"""SQLite append-only implementation of the EventStore interface."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path

from arbibot.core.errors import EventValidationError
from arbibot.core.events import BaseEvent
from arbibot.core.time import now_wall_ms
from arbibot.storage.event_store import EventStore, StoredEvent


class SQLiteEventStore(EventStore):
    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    source_ts_ms INTEGER NOT NULL,
                    recv_wall_ts_ms INTEGER NOT NULL,
                    recv_monotonic_ns INTEGER NOT NULL,
                    inserted_at_wall_ts_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_source_ts_ms ON events(source_ts_ms)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type)"
            )

    def close(self) -> None:
        self._conn.close()

    def append(self, event: BaseEvent) -> None:
        self.append_many([event])

    def append_many(self, events: Sequence[BaseEvent]) -> None:
        inserted_at_wall_ts_ms = now_wall_ms()
        rows = [
            (
                event.event_id,
                event.__class__.__name__,
                event.source,
                event.source_ts_ms,
                event.recv_wall_ts_ms,
                event.recv_monotonic_ns,
                inserted_at_wall_ts_ms,
                event.model_dump_json(),
            )
            for event in events
        ]
        try:
            with self._conn:
                self._conn.executemany(
                    """
                    INSERT INTO events (
                        event_id,
                        event_type,
                        source,
                        source_ts_ms,
                        recv_wall_ts_ms,
                        recv_monotonic_ns,
                        inserted_at_wall_ts_ms,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
        except sqlite3.IntegrityError as exc:
            raise EventValidationError("Duplicate event_id detected during append") from exc

    def get_event(self, event_id: str) -> StoredEvent | None:
        row = self._conn.execute(
            """
            SELECT event_id, event_type, source, source_ts_ms, recv_wall_ts_ms,
                   recv_monotonic_ns, inserted_at_wall_ts_ms, payload_json
            FROM events
            WHERE event_id = ?
            """,
            (event_id,),
        ).fetchone()
        return _row_to_stored_event(row) if row is not None else None

    def iter_events(
        self,
        start_ts_ms: int | None = None,
        end_ts_ms: int | None = None,
        event_types: Sequence[str] | None = None,
    ) -> Iterator[StoredEvent]:
        conditions: list[str] = []
        params: list[object] = []

        if start_ts_ms is not None:
            conditions.append("source_ts_ms >= ?")
            params.append(start_ts_ms)
        if end_ts_ms is not None:
            conditions.append("source_ts_ms <= ?")
            params.append(end_ts_ms)
        if event_types:
            placeholders = ", ".join("?" for _ in event_types)
            conditions.append(f"event_type IN ({placeholders})")
            params.extend(event_types)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT event_id, event_type, source, source_ts_ms, recv_wall_ts_ms,
                   recv_monotonic_ns, inserted_at_wall_ts_ms, payload_json
            FROM events
            {where_clause}
            ORDER BY source_ts_ms ASC, recv_wall_ts_ms ASC, id ASC
        """

        rows = self._conn.execute(query, tuple(params))
        for row in rows:
            mapped = _row_to_stored_event(row)
            if mapped is not None:
                yield mapped


def _row_to_stored_event(row: sqlite3.Row | None) -> StoredEvent | None:
    if row is None:
        return None
    return StoredEvent(
        event_id=str(row["event_id"]),
        event_type=str(row["event_type"]),
        source=str(row["source"]),
        source_ts_ms=int(row["source_ts_ms"]),
        recv_wall_ts_ms=int(row["recv_wall_ts_ms"]),
        recv_monotonic_ns=int(row["recv_monotonic_ns"]),
        inserted_at_wall_ts_ms=int(row["inserted_at_wall_ts_ms"]),
        payload_json=str(row["payload_json"]),
    )
