from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from arbibot.ingestion.binance_ws import BinanceSpotMarketDataClient
from arbibot.ingestion.interfaces import SpotMarketDataClient
from arbibot.storage.event_store import EventStore
from arbibot.storage.sqlite_store import SQLiteEventStore

SUPPORTED_STREAMS = frozenset({"aggTrade", "trade", "bookTicker"})


class RecordStopReason(StrEnum):
    MAX_EVENTS_REACHED = "MAX_EVENTS_REACHED"
    DURATION_REACHED = "DURATION_REACHED"
    INTERRUPTED = "INTERRUPTED"
    CLIENT_STOPPED = "CLIENT_STOPPED"
    ERROR = "ERROR"
    DRY_RUN = "DRY_RUN"


@dataclass(frozen=True, slots=True)
class RecordSummary:
    source: str
    symbol: str
    streams: list[str]
    store_path: str
    events_recorded: int
    started_at_ms: int
    ended_at_ms: int
    duration_ms: int
    stopped_reason: RecordStopReason
    errors_count: int


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


def _parse_streams(raw_streams: str) -> list[str]:
    streams = [part.strip() for part in raw_streams.split(",") if part.strip()]
    if not streams:
        raise ValueError("streams must contain at least one stream")
    unknown = [stream for stream in streams if stream not in SUPPORTED_STREAMS]
    if unknown:
        supported = ", ".join(sorted(SUPPORTED_STREAMS))
        raise ValueError(
            f"Unsupported stream(s): {', '.join(unknown)}. Supported streams: {supported}"
        )
    return streams


async def record_events(
    client: SpotMarketDataClient,
    store: EventStore,
    *,
    max_events: int | None = None,
    duration_seconds: int | None = None,
    store_path: str,
    symbol: str,
    streams: list[str],
) -> RecordSummary:
    if max_events is not None and max_events < 0:
        raise ValueError("max_events must be >= 0")
    if duration_seconds is not None and duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")

    started_at_ms = _now_ms()
    deadline_ms = None if duration_seconds is None else started_at_ms + (duration_seconds * 1000)
    events_recorded = 0
    errors_count = 0
    reason = RecordStopReason.CLIENT_STOPPED

    await client.start()
    try:
        async for event in client.events():
            now_ms = _now_ms()
            if deadline_ms is not None and now_ms >= deadline_ms:
                reason = RecordStopReason.DURATION_REACHED
                break
            store.append(event)
            events_recorded += 1
            if max_events is not None and events_recorded >= max_events:
                reason = RecordStopReason.MAX_EVENTS_REACHED
                break
        else:
            reason = RecordStopReason.CLIENT_STOPPED
    except asyncio.CancelledError:
        reason = RecordStopReason.INTERRUPTED
    except KeyboardInterrupt:
        reason = RecordStopReason.INTERRUPTED
    except Exception:
        errors_count += 1
        reason = RecordStopReason.ERROR
    finally:
        await client.stop()

    ended_at_ms = _now_ms()
    return RecordSummary(
        source=client.source,
        symbol=symbol,
        streams=streams,
        store_path=store_path,
        events_recorded=events_recorded,
        started_at_ms=started_at_ms,
        ended_at_ms=ended_at_ms,
        duration_ms=max(0, ended_at_ms - started_at_ms),
        stopped_reason=reason,
        errors_count=errors_count,
    )


def run_record_binance(
    store_path: str,
    symbol: str,
    streams_csv: str,
    duration_seconds: int | None,
    max_events: int | None,
    as_json: bool,
    dry_run: bool,
    config_path: str | None = None,
) -> int:
    del config_path
    try:
        streams = _parse_streams(streams_csv)
    except ValueError as exc:
        print(f"record-binance validation failed: {exc}")
        return 1

    if dry_run:
        now = _now_ms()
        summary = RecordSummary(
            source="binance",
            symbol=symbol.upper(),
            streams=streams,
            store_path=store_path,
            events_recorded=0,
            started_at_ms=now,
            ended_at_ms=now,
            duration_ms=0,
            stopped_reason=RecordStopReason.DRY_RUN,
            errors_count=0,
        )
        _print_summary(summary, as_json=as_json)
        return 0

    if duration_seconds is None and max_events is None and not as_json:
        print(
            "Warning: no --duration-seconds or --max-events set; "
            "recording will run until interrupted."
        )

    normalized_symbol = symbol.upper()
    stream_names = [f"{normalized_symbol.lower()}@{stream}" for stream in streams]

    store = SQLiteEventStore(Path(store_path))
    client = BinanceSpotMarketDataClient(symbol=normalized_symbol, streams=stream_names)
    try:
        summary = asyncio.run(
            record_events(
                client,
                store,
                max_events=max_events,
                duration_seconds=duration_seconds,
                store_path=store_path,
                symbol=normalized_symbol,
                streams=streams,
            )
        )
    except KeyboardInterrupt:
        now = _now_ms()
        summary = RecordSummary(
            source="binance",
            symbol=normalized_symbol,
            streams=streams,
            store_path=store_path,
            events_recorded=0,
            started_at_ms=now,
            ended_at_ms=now,
            duration_ms=0,
            stopped_reason=RecordStopReason.INTERRUPTED,
            errors_count=0,
        )
    finally:
        store.close()

    _print_summary(summary, as_json=as_json)
    return 0 if summary.stopped_reason is not RecordStopReason.ERROR else 2


def _print_summary(summary: RecordSummary, *, as_json: bool) -> None:
    payload = asdict(summary)
    payload["stopped_reason"] = summary.stopped_reason.value
    if as_json:
        print(json.dumps(payload, sort_keys=True))
        return
    print(
        "Recorded Binance events "
        f"events_recorded={summary.events_recorded} "
        f"source={summary.source} "
        f"symbol={summary.symbol} "
        f"streams={','.join(summary.streams)} "
        f"duration_ms={summary.duration_ms} "
        f"stopped_reason={summary.stopped_reason.value} "
        f"errors_count={summary.errors_count}"
    )
