import pytest

from arbibot.core.errors import EventValidationError
from arbibot.core.time import event_age_ms, now_monotonic_ns, now_wall_ms, validate_timestamp_ms


def test_event_age_ms_calculates_correctly() -> None:
    assert event_age_ms(1000, now_ms=1250) == 250


def test_invalid_timestamp_raises() -> None:
    with pytest.raises(EventValidationError):
        validate_timestamp_ms(0, "source_ts_ms")


def test_now_functions_return_positive_ints() -> None:
    wall_ms = now_wall_ms()
    mono_ns = now_monotonic_ns()
    assert isinstance(wall_ms, int)
    assert isinstance(mono_ns, int)
    assert wall_ms > 0
    assert mono_ns > 0
