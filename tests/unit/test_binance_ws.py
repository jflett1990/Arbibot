import json
from pathlib import Path

import pytest

from arbibot.core.events import SpotTick
from arbibot.ingestion.binance_ws import (
    BinancePayloadError,
    BinanceSpotMarketDataClient,
    parse_binance_payload,
)
from arbibot.ingestion.interfaces import SpotMarketDataClient

FIXTURE_DIR = Path("tests/fixtures/binance")


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_parse_agg_trade_fixture_to_spot_tick() -> None:
    payload = _load("agg_trade.json")
    tick = parse_binance_payload(payload, recv_wall_ts_ms=1_000_000, recv_monotonic_ns=200)
    assert isinstance(tick, SpotTick)
    assert tick.source == "binance"
    assert tick.symbol == "BTCUSDT"
    assert tick.price == 68250.12
    assert tick.size == 0.015
    assert tick.sequence_id == "91234567"
    assert tick.trade_id == "91234567"
    assert tick.stream_event_type == "aggTrade"
    assert tick.source_ts_ms == 1710000000100


def test_parse_trade_fixture_to_spot_tick() -> None:
    payload = _load("trade.json")
    tick = parse_binance_payload(payload, recv_wall_ts_ms=1_000_001, recv_monotonic_ns=201)
    assert isinstance(tick, SpotTick)
    assert tick.sequence_id == "8123456"
    assert tick.trade_id == "8123456"
    assert tick.stream_event_type == "trade"


def test_parse_book_ticker_fixture_is_ignored_without_quote_schema() -> None:
    payload = _load("book_ticker.json")
    tick = parse_binance_payload(payload, recv_wall_ts_ms=10, recv_monotonic_ns=11)
    assert tick is None


def test_invalid_missing_price_fails() -> None:
    payload = _load("agg_trade.json")
    data = payload["data"]
    assert isinstance(data, dict)
    data.pop("p")
    with pytest.raises(BinancePayloadError):
        parse_binance_payload(payload, recv_wall_ts_ms=1, recv_monotonic_ns=2)


def test_invalid_missing_quantity_fails() -> None:
    payload = _load("trade.json")
    data = payload["data"]
    assert isinstance(data, dict)
    data.pop("q")
    with pytest.raises(BinancePayloadError):
        parse_binance_payload(payload, recv_wall_ts_ms=1, recv_monotonic_ns=2)


def test_missing_timestamp_fails() -> None:
    payload = _load("trade.json")
    data = payload["data"]
    assert isinstance(data, dict)
    data.pop("T")
    data.pop("E")
    with pytest.raises(BinancePayloadError):
        parse_binance_payload(payload, recv_wall_ts_ms=1, recv_monotonic_ns=2)


def test_injected_receive_timestamps_preserved() -> None:
    payload = _load("agg_trade.json")
    tick = parse_binance_payload(payload, recv_wall_ts_ms=999, recv_monotonic_ns=888)
    assert isinstance(tick, SpotTick)
    assert tick.recv_wall_ts_ms == 999
    assert tick.recv_monotonic_ns == 888


def test_unsupported_event_type_handled_explicitly() -> None:
    payload: dict[str, object] = {
        "stream": "btcusdt@depth",
        "data": {"e": "depthUpdate", "E": 1, "s": "BTCUSDT"},
    }
    parsed = parse_binance_payload(payload, recv_wall_ts_ms=10, recv_monotonic_ns=20)
    assert parsed is None


def test_client_satisfies_spot_protocol() -> None:
    client: SpotMarketDataClient = BinanceSpotMarketDataClient(symbol="BTCUSDT")
    assert client.source == "binance"
    assert client.symbol == "BTCUSDT"


def test_stop_halts_client_loop_without_network() -> None:
    client = BinanceSpotMarketDataClient(symbol="BTCUSDT")
    import asyncio

    asyncio.run(client.start())
    asyncio.run(client.stop())
