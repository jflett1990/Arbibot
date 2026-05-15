import json
from pathlib import Path

import pytest

from arbibot.core.events import SignalDirection
from arbibot.ingestion.tradingview_adapter import parse_tradingview_payload

FIX = Path("tests/fixtures/tradingview")


def _load(name: str) -> dict[str, object]:
    return json.loads((FIX / name).read_text())


def test_bullish_and_neutral_and_missing_source_ts() -> None:
    bull = parse_tradingview_payload(_load("bullish_alert.json"), 1000, 2000)
    assert bull.direction is SignalDirection.BULL
    assert bull.expires_at_ms == bull.source_ts_ms + 60_000

    neutral = parse_tradingview_payload(_load("neutral_alert.json"), 1000, 2000)
    assert neutral.direction is SignalDirection.NEUTRAL

    bear = parse_tradingview_payload(_load("bearish_alert_missing_source_ts.json"), 9999, 2000)
    assert bear.direction is SignalDirection.BEAR
    assert bear.source_ts_ms == 9999
    assert bear.metadata is not None
    assert bear.metadata["source_timestamp_missing"] is True


def test_alias_strength_and_validation() -> None:
    payload: dict[str, object] = {
        "symbol": "BTCUSDT",
        "indicator": "test",
        "direction": "long",
        "strength": "1.8",
        "source_ts_ms": 10,
    }
    evt = parse_tradingview_payload(payload, 100, 101)
    assert evt.direction is SignalDirection.BULL
    assert evt.strength == 1.0

    payload["direction"] = "mystery"
    evt2 = parse_tradingview_payload(payload, 100, 101)
    assert evt2.direction is SignalDirection.NEUTRAL

    with pytest.raises(ValueError):
        parse_tradingview_payload({"indicator": "x"}, 100, 101)
    with pytest.raises(ValueError):
        parse_tradingview_payload({"symbol": "BTCUSDT"}, 100, 101)
    with pytest.raises(ValueError):
        parse_tradingview_payload({"symbol": "BTCUSDT", "indicator": "x"}, 100, 101, 0)
