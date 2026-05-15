import pytest

from arbibot.replay.latency_model import LatencyConfig, adjusted_event_time, apply_delay_ms


def test_latency_config_validation() -> None:
    LatencyConfig()
    with pytest.raises(ValueError):
        LatencyConfig(data_delay_ms=-1)


def test_apply_delay_ms() -> None:
    assert apply_delay_ms(1000, 5) == 1005
    with pytest.raises(ValueError):
        apply_delay_ms(1, -1)


def test_adjusted_event_time() -> None:
    assert adjusted_event_time(123, 7) == 130
