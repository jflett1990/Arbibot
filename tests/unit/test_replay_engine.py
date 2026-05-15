from decimal import Decimal

import pytest

from arbibot.core.events import PolyBookDelta, PolyBookSnapshot, SpotTick
from arbibot.opportunity.edge import OutcomeSide
from arbibot.replay.engine import ReplayConfig, ReplayEngine
from arbibot.storage.sqlite_store import SQLiteEventStore


def _tick(i: int, ts: int, price: float = 70000.0) -> SpotTick:
    return SpotTick(
        event_id=f"t{i}",
        source="binance",
        source_ts_ms=ts,
        recv_wall_ts_ms=ts + 10,
        recv_monotonic_ns=ts * 1000,
        symbol="BTCUSDT",
        price=price,
        size=0.2,
        stream_event_type="trade",
    )


def _snapshot(ts: int) -> PolyBookSnapshot:
    return PolyBookSnapshot(
        event_id="s1",
        source="poly",
        source_ts_ms=ts,
        recv_wall_ts_ms=ts + 1,
        recv_monotonic_ns=ts + 2,
        market_id="m",
        outcome="UP",
        token_id="tok",
        bids=[[0.45, 10]],
        asks=[[0.46, 20]],
    )


def _delta(ts: int) -> PolyBookDelta:
    return PolyBookDelta(
        event_id="d1",
        source="poly",
        source_ts_ms=ts,
        recv_wall_ts_ms=ts + 1,
        recv_monotonic_ns=ts + 2,
        market_id="m",
        outcome="UP",
        token_id="tok",
        side="SELL",
        price=0.47,
        size=12,
    )


def test_replay_deterministic_and_counts(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "e.sqlite")
    try:
        store.append_many([_tick(1, 1000), _tick(2, 2000), _snapshot(1500), _delta(2500)])
        cfg = ReplayConfig()
        r1 = ReplayEngine(store, cfg).run()
        r2 = ReplayEngine(store, cfg).run()
        assert [c.event_id for c in r1.candles] == [c.event_id for c in r2.candles]
        assert r1.summary.spot_ticks == 2
        assert r1.summary.book_snapshots == 1
        assert r1.summary.book_deltas == 1
        assert r1.summary.feature_snapshots == 2
        assert r1.decisions == []
    finally:
        store.close()


def test_orphan_delta_unknown_and_malformed_handling(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "e.sqlite")
    try:
        store.append(_tick(1, 1000))
        # orphan delta
        store.append(
            PolyBookDelta(
                event_id="od",
                source="poly",
                source_ts_ms=900,
                recv_wall_ts_ms=901,
                recv_monotonic_ns=902,
                market_id="m",
                outcome="UP",
                token_id="unknown",
                side="SELL",
                price=0.5,
                size=1,
            )
        )
        insert_sql = (
            "INSERT INTO events ("
            "event_id,event_type,source,source_ts_ms,recv_wall_ts_ms,"
            "recv_monotonic_ns,inserted_at_wall_ts_ms,payload_json"
            ") VALUES (?,?,?,?,?,?,?,?)"
        )
        with store._conn:  # noqa: SLF001
            store._conn.execute(
                insert_sql,
                ("u1", "UnknownType", "x", 3000, 3001, 3002, 3003, "{}"),
            )
            store._conn.execute(
                insert_sql,
                ("m1", "SpotTick", "x", 3004, 3005, 3006, 3007, "{"),
            )
        result = ReplayEngine(store, ReplayConfig()).run()
        assert result.summary.orphan_book_deltas == 1
        assert result.summary.unknown_events == 1
        assert result.summary.malformed_events == 1
    finally:
        store.close()


def test_strict_deserialization_raises(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "e.sqlite")
    try:
        store.append(_tick(1, 1000))
        insert_sql = (
            "INSERT INTO events ("
            "event_id,event_type,source,source_ts_ms,recv_wall_ts_ms,"
            "recv_monotonic_ns,inserted_at_wall_ts_ms,payload_json"
            ") VALUES (?,?,?,?,?,?,?,?)"
        )
        with store._conn:  # noqa: SLF001
            store._conn.execute(
                insert_sql,
                ("m1", "SpotTick", "x", 3004, 3005, 3006, 3007, "{"),
            )
        with pytest.raises(ValueError):
            ReplayEngine(store, ReplayConfig(strict_deserialization=True)).run()
    finally:
        store.close()


def test_evaluate_and_paper_execute_paths(tmp_path: pytest.TempPathFactory) -> None:
    store = SQLiteEventStore(tmp_path / "e.sqlite")
    try:
        store.append_many([_snapshot(900), _tick(1, 1000, 100.0), _tick(2, 6000, 120.0)])
        cfg = ReplayConfig(
            evaluate_opportunities=True,
            paper_execute=True,
            threshold_price=Decimal("90"),
            seconds_to_expiry=Decimal("300"),
            outcome_side=OutcomeSide.UP,
            target_size=Decimal("1"),
            model_error_buffer=Decimal("0"),
        )
        result = ReplayEngine(store, cfg).run()
        assert result.summary.decisions_total == len(result.feature_snapshots)
        assert all(d.event_id.startswith("replay_decision:") for d in result.decisions)
        trade_decisions = [d for d in result.decisions if d.action.value == "TRADE"]
        assert len(result.order_events) <= len(trade_decisions)
        for order in result.order_events:
            assert order.client_order_id is not None
            assert order.client_order_id.startswith("paper:replay_decision:")
    finally:
        store.close()
