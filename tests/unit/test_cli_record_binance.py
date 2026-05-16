import asyncio
import json
from collections.abc import AsyncIterator

from arbibot.apps.cli import main
from arbibot.apps.commands.record_binance import record_events
from arbibot.core.events import SpotTick
from arbibot.storage.sqlite_store import SQLiteEventStore


class MockSpotClient:
    source = "binance"

    def __init__(self, events: list[SpotTick], symbol: str = "BTCUSDT") -> None:
        self.symbol = symbol
        self._events = events
        self._stop = False

    async def start(self) -> None:
        self._stop = False

    async def stop(self) -> None:
        self._stop = True

    async def events(self) -> AsyncIterator[SpotTick]:
        for event in self._events:
            if self._stop:
                break
            await asyncio.sleep(0)
            yield event


def _tick(idx: int) -> SpotTick:
    return SpotTick(
        event_id=f"tick-{idx}",
        source="binance",
        source_ts_ms=1_000 + idx,
        recv_wall_ts_ms=2_000 + idx,
        recv_monotonic_ns=3_000 + idx,
        sequence_id=str(idx),
        symbol="BTCUSDT",
        price=60_000.0 + idx,
        size=0.1,
        trade_id=str(idx),
        stream_event_type="trade",
    )


def test_record_binance_dry_run_writes_nothing(tmp_path, capsys) -> None:
    db = tmp_path / "events.sqlite3"
    rc = main(["record-binance", "--store", str(db), "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["stopped_reason"] == "DRY_RUN"
    assert payload["events_recorded"] == 0
    store = SQLiteEventStore(db)
    assert list(store.iter_events()) == []
    store.close()


def test_record_binance_invalid_stream_exits_nonzero(capsys) -> None:
    rc = main(["record-binance", "--streams", "aggTrade,depthUpdate", "--dry-run"])
    output = capsys.readouterr().out
    assert rc == 1
    assert "Unsupported stream" in output


def test_record_events_max_events_persists_exact_n(tmp_path) -> None:
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    client = MockSpotClient([_tick(1), _tick(2), _tick(3), _tick(4)])
    summary = asyncio.run(
        record_events(
            client,
            store,
            max_events=3,
            duration_seconds=None,
            store_path=str(tmp_path / "events.sqlite3"),
            symbol="BTCUSDT",
            streams=["trade"],
        )
    )
    events = list(store.iter_events())
    store.close()
    assert summary.events_recorded == 3
    assert summary.stopped_reason.value == "MAX_EVENTS_REACHED"
    assert len(events) == 3


def test_record_events_duration_reached(tmp_path) -> None:
    class SlowMockClient(MockSpotClient):
        async def events(self) -> AsyncIterator[SpotTick]:
            idx = 0
            while idx < 20 and not self._stop:
                idx += 1
                await asyncio.sleep(0.03)
                yield _tick(idx)

    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    client = SlowMockClient([])
    summary = asyncio.run(
        record_events(
            client,
            store,
            duration_seconds=0.05,
            max_events=None,
            store_path=str(tmp_path / "events.sqlite3"),
            symbol="BTCUSDT",
            streams=["trade"],
        )
    )
    store.close()
    assert summary.stopped_reason.value == "DURATION_REACHED"


def test_record_binance_json_output_and_human_output(monkeypatch, tmp_path, capsys) -> None:
    class FakeClient(MockSpotClient):
        def __init__(self, symbol: str, streams: list[str], config=None) -> None:  # noqa: ANN001
            del config
            super().__init__([_tick(1), _tick(2)], symbol=symbol)
            self.streams = streams

    monkeypatch.setattr(
        "arbibot.apps.commands.record_binance.BinanceSpotMarketDataClient",
        FakeClient,
    )

    db = tmp_path / "events.sqlite3"
    rc = main(["record-binance", "--store", str(db), "--max-events", "2", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["events_recorded"] == 2

    db2 = tmp_path / "events2.sqlite3"
    rc2 = main(["record-binance", "--store", str(db2), "--max-events", "2"])
    out2 = capsys.readouterr().out
    assert rc2 == 0
    assert "events_recorded=2" in out2


def test_record_events_cancelled_reports_interrupted(tmp_path) -> None:
    async def run() -> str:
        store = SQLiteEventStore(tmp_path / "events.sqlite3")
        client = MockSpotClient([_tick(1), _tick(2), _tick(3)])
        task = asyncio.create_task(
            record_events(
                client,
                store,
                store_path=str(tmp_path / "events.sqlite3"),
                symbol="BTCUSDT",
                streams=["trade"],
            )
        )
        await asyncio.sleep(0)
        task.cancel()
        summary = await task
        store.close()
        return summary.stopped_reason.value

    assert asyncio.run(run()) == "INTERRUPTED"
