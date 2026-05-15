"""Binance spot WebSocket normalization and client adapter."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import websockets

from arbibot.core.errors import EventValidationError
from arbibot.core.events import BaseEvent, SpotBookTicker, SpotTick
from arbibot.core.time import now_monotonic_ns, now_wall_ms


class BinancePayloadError(EventValidationError):
    """Raised when a Binance payload cannot be normalized."""


@dataclass(frozen=True)
class BinanceClientConfig:
    url: str = "wss://stream.binance.com:9443/stream"
    reconnect_initial_delay_ms: int = 250
    reconnect_max_delay_ms: int = 5_000
    ignore_unsupported_events: bool = True


def parse_binance_payload(
    payload: dict[str, Any],
    recv_wall_ts_ms: int,
    recv_monotonic_ns: int,
) -> SpotTick | SpotBookTicker | None:
    if "stream" in payload and "data" in payload:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BinancePayloadError("Combined stream payload must contain object data")
        return _parse_event_data(data, recv_wall_ts_ms, recv_monotonic_ns)
    return _parse_event_data(payload, recv_wall_ts_ms, recv_monotonic_ns)


def _parse_event_data(
    data: dict[str, Any],
    recv_wall_ts_ms: int,
    recv_monotonic_ns: int,
) -> SpotTick | SpotBookTicker | None:
    event_type = data.get("e")
    if event_type is None and all(k in data for k in ("b", "B", "a", "A")):
        event_type = "bookTicker"
    if event_type in {"aggTrade", "trade"}:
        symbol = _require_str(data, "s")
        price = _parse_positive_float(_require_str(data, "p"), "p")
        qty = _parse_positive_float(_require_str(data, "q"), "q")
        source_ts_ms = _extract_trade_timestamp_ms(data, event_type)
        trade_id = str(_require_int(data, "a" if event_type == "aggTrade" else "t"))
        return SpotTick(
            event_id=f"binance-{event_type}-{symbol}-{trade_id}",
            source="binance",
            source_ts_ms=source_ts_ms,
            recv_wall_ts_ms=recv_wall_ts_ms,
            recv_monotonic_ns=recv_monotonic_ns,
            sequence_id=trade_id,
            symbol=symbol,
            price=price,
            size=qty,
            trade_id=trade_id,
            stream_event_type=event_type,
        )

    if event_type == "bookTicker":
        symbol = _require_str(data, "s")
        bid_price = _parse_positive_float(_require_str(data, "b"), "b")
        ask_price = _parse_positive_float(_require_str(data, "a"), "a")
        bid_size = _parse_non_negative_float(_require_str(data, "B"), "B")
        ask_size = _parse_non_negative_float(_require_str(data, "A"), "A")
        source_ts_ms = _require_int(data, "E") if "E" in data else recv_wall_ts_ms
        return SpotBookTicker(
            event_id=f"binance-bookTicker-{symbol}-{source_ts_ms}",
            source="binance",
            source_ts_ms=source_ts_ms,
            recv_wall_ts_ms=recv_wall_ts_ms,
            recv_monotonic_ns=recv_monotonic_ns,
            symbol=symbol,
            bid_price=bid_price,
            bid_size=bid_size,
            ask_price=ask_price,
            ask_size=ask_size,
            stream_event_type="bookTicker",
        )

    return None


def _extract_trade_timestamp_ms(data: dict[str, Any], event_type: str) -> int:
    if "T" in data:
        return _require_int(data, "T")
    if "E" in data:
        return _require_int(data, "E")
    raise BinancePayloadError(f"Missing timestamp in {event_type} payload")


def _require_str(data: dict[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise BinancePayloadError(f"Missing or invalid string field: {field}")
    return value


def _require_int(data: dict[str, Any], field: str) -> int:
    value = data.get(field)
    if not isinstance(value, int) or value <= 0:
        raise BinancePayloadError(f"Missing or invalid positive integer field: {field}")
    return value


def _parse_positive_float(raw: str, field: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise BinancePayloadError(f"Invalid numeric field: {field}") from exc
    if value <= 0:
        raise BinancePayloadError(f"Numeric field must be > 0: {field}")
    return value


def _parse_non_negative_float(raw: str, field: str) -> float:
    try:
        value = float(raw)
    except ValueError as exc:
        raise BinancePayloadError(f"Invalid numeric field: {field}") from exc
    if value < 0:
        raise BinancePayloadError(f"Numeric field must be >= 0: {field}")
    return value


class BinanceSpotMarketDataClient:
    source = "binance"

    def __init__(
        self,
        symbol: str,
        streams: list[str] | None = None,
        config: BinanceClientConfig | None = None,
    ) -> None:
        self.symbol = symbol.upper()
        self.streams = streams if streams is not None else [f"{self.symbol.lower()}@aggTrade"]
        self.config = config or BinanceClientConfig()
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        self._stop_event.clear()

    async def stop(self) -> None:
        self._stop_event.set()

    def events(self) -> AsyncIterator[BaseEvent]:
        return self._events_impl()

    async def _events_impl(self) -> AsyncIterator[BaseEvent]:
        delay_ms = self.config.reconnect_initial_delay_ms
        while not self._stop_event.is_set():
            uri = f"{self.config.url}?streams={'/'.join(self.streams)}"
            try:
                async with websockets.connect(uri) as ws:
                    delay_ms = self.config.reconnect_initial_delay_ms
                    while not self._stop_event.is_set():
                        try:
                            raw_message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        except TimeoutError:
                            continue
                        payload = json.loads(raw_message)
                        if not isinstance(payload, dict):
                            raise BinancePayloadError(
                                "WebSocket message must decode to JSON object"
                            )
                        parsed = parse_binance_payload(payload, now_wall_ms(), now_monotonic_ns())
                        if parsed is None:
                            if self.config.ignore_unsupported_events:
                                continue
                            raise BinancePayloadError("Unsupported Binance event type")
                        yield parsed
            except BinancePayloadError:
                raise
            except Exception:
                if self._stop_event.is_set():
                    break
                await asyncio.sleep(delay_ms / 1000.0)
                delay_ms = min(delay_ms * 2, self.config.reconnect_max_delay_ms)
