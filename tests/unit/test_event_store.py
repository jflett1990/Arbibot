import sqlite3

import pytest

from arbibot.core.errors import EventValidationError
from arbibot.core.events import SpotBar, SpotTick
from arbibot.storage.sqlite_store import SQLiteEventStore


def _tick(event_id: str, source_ts_ms: int, recv_wall_ts_ms: int) -> SpotTick:
    return SpotTick(
        event_id=event_id,
        source="binance",
        source_ts_ms=source_ts_ms,
        recv_wall_ts_ms=recv_wall_ts_ms,
        recv_monotonic_ns=source_ts_ms * 1000,
        symbol="BTCUSDT",
        price=70000.0,
        size=0.1,
    )


def test_schema_created_on_init(tmp_path: pytest.TempPathFactory) -> None:
    db = tmp_path / "events.sqlite3"
    store = SQLiteEventStore(db)
    try:
        with sqlite3.connect(db) as conn:
            table = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='events'"
            ).fetchone()
            assert table is not None
    finally:
        store.close()


def test_append_and_get_event(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    try:
        event = _tick("e1", 1000, 1100)
        store.append(event)
        loaded = store.get_event("e1")
        assert loaded is not None
        assert loaded.event_id == "e1"
        assert loaded.event_type == "SpotTick"
        assert loaded.source_ts_ms == 1000
    finally:
        store.close()


def test_append_many_stores_multiple(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    try:
        store.append_many([_tick("e1", 1000, 1100), _tick("e2", 1001, 1101)])
        assert store.get_event("e1") is not None
        assert store.get_event("e2") is not None
    finally:
        store.close()


def test_duplicate_event_id_raises(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    try:
        store.append(_tick("e1", 1000, 1100))
        with pytest.raises(EventValidationError):
            store.append(_tick("e1", 1001, 1101))
    finally:
        store.close()


def test_iter_events_deterministic_ordering(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    try:
        events = [
            _tick("e3", 1000, 1102),
            _tick("e1", 900, 1200),
            _tick("e2", 1000, 1101),
        ]
        store.append_many(events)
        ids = [event.event_id for event in store.iter_events()]
        assert ids == ["e1", "e2", "e3"]
    finally:
        store.close()


def test_iter_events_filters(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    try:
        bar = SpotBar(
            event_id="b1",
            source="binance",
            source_ts_ms=2000,
            recv_wall_ts_ms=2100,
            recv_monotonic_ns=2000000,
            symbol="BTCUSDT",
            open=1,
            high=2,
            low=0.5,
            close=1.5,
            volume=10,
        )
        store.append_many([_tick("e1", 1000, 1100), _tick("e2", 1500, 1600), bar])

        assert [e.event_id for e in store.iter_events(start_ts_ms=1200)] == ["e2", "b1"]
        assert [e.event_id for e in store.iter_events(end_ts_ms=1500)] == ["e1", "e2"]
        assert [e.event_id for e in store.iter_events(event_types=["SpotBar"])] == ["b1"]
    finally:
        store.close()


def test_persists_after_reopen(tmp_path: pytest.TempPathFactory) -> None:
    db_path = tmp_path / "events.sqlite3"
    store = SQLiteEventStore(db_path)
    store.append(_tick("e1", 1000, 1100))
    store.close()

    reopened = SQLiteEventStore(db_path)
    try:
        loaded = reopened.get_event("e1")
        assert loaded is not None
        assert loaded.event_id == "e1"
    finally:
        reopened.close()


def test_payload_json_contains_original_fields(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    try:
        event = _tick("e1", 1000, 1100)
        store.append(event)
        loaded = store.get_event("e1")
        assert loaded is not None
        assert '"event_id":"e1"' in loaded.payload_json
        assert '"symbol":"BTCUSDT"' in loaded.payload_json
    finally:
        store.close()


def test_invalid_manual_row_does_not_crash_unrelated_reads(
    tmp_path: pytest.TempPathFactory,
) -> None:
    db_path = tmp_path / "events.sqlite3"
    store = SQLiteEventStore(db_path)
    try:
        store.append(_tick("ok1", 1000, 1100))
    finally:
        store.close()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO events (
                event_id, event_type, source, source_ts_ms, recv_wall_ts_ms,
                recv_monotonic_ns, inserted_at_wall_ts_ms, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("bad1", "SpotTick", "binance", 9999, 9999, 9999, 9999, "{"),
        )
        conn.commit()

    reopened = SQLiteEventStore(db_path)
    try:
        loaded = reopened.get_event("ok1")
        assert loaded is not None
        assert loaded.event_id == "ok1"
    finally:
        reopened.close()
