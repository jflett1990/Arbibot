import json
from pathlib import Path

import pytest

from arbibot.core.events import SignalDirection
from arbibot.ingestion.cryptoquant_adapter import parse_cryptoquant_metric
from arbibot.model.signal import external_signal_to_graph_node

FIX = Path("tests/fixtures/cryptoquant")


def _load(name: str) -> dict[str, object]:
    return json.loads((FIX / name).read_text())


def test_cryptoquant_direction_mapping_and_metadata() -> None:
    high = parse_cryptoquant_metric(_load("exchange_inflow_high_z.json"), 1000, 2000)
    low = parse_cryptoquant_metric(_load("exchange_inflow_low_z.json"), 1000, 2000)
    neutral = parse_cryptoquant_metric(_load("neutral_metric.json"), 1000, 2000)

    assert high.direction is SignalDirection.BEAR
    assert low.direction is SignalDirection.BULL
    assert neutral.direction is SignalDirection.NEUTRAL
    assert high.metadata is not None
    assert high.metadata["slow_context"] is True
    assert high.metadata["hot_path_trigger"] is False
    assert high.metadata["revision_risk"] is True


def test_overrides_validation_and_expiry() -> None:
    payload = _load("neutral_metric.json")
    payload["direction"] = "buy"
    evt = parse_cryptoquant_metric(payload, 1000, 2000)
    assert evt.direction is SignalDirection.BULL
    assert evt.expires_at_ms == evt.source_ts_ms + 300_000

    with pytest.raises(ValueError):
        parse_cryptoquant_metric({"value": 1}, 1000, 2000)
    with pytest.raises(ValueError):
        parse_cryptoquant_metric({"metric": "m"}, 1000, 2000)
    with pytest.raises(ValueError):
        parse_cryptoquant_metric({"metric": "m", "value": 1}, 1000, 2000, 0)


def test_external_signal_to_graph_node() -> None:
    bull = parse_cryptoquant_metric(_load("exchange_inflow_low_z.json"), 1000, 2000)
    bear = parse_cryptoquant_metric(_load("exchange_inflow_high_z.json"), 1000, 2000)
    neutral = parse_cryptoquant_metric(_load("neutral_metric.json"), 1000, 2000)

    bn = external_signal_to_graph_node(bull, now_source_ts_ms=bull.source_ts_ms)
    br = external_signal_to_graph_node(bear, now_source_ts_ms=bear.source_ts_ms)
    nt = external_signal_to_graph_node(
        neutral,
        now_source_ts_ms=neutral.expires_at_ms or neutral.source_ts_ms,
    )

    assert bn.direction is SignalDirection.BULL
    assert br.direction is SignalDirection.BEAR
    assert nt.direction is SignalDirection.NEUTRAL

    expired = external_signal_to_graph_node(
        neutral,
        now_source_ts_ms=(neutral.expires_at_ms or 0) + 1,
    )
    assert expired.freshness == 0
    assert bn.name.startswith("external_signal:")
