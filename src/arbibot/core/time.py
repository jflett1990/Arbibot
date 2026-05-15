"""Time utilities for deterministic event age and timestamp validation."""

from __future__ import annotations

import time

from arbibot.core.errors import EventValidationError


def now_wall_ms() -> int:
    """Return current wall-clock time in milliseconds since epoch."""
    return int(time.time() * 1000)


def now_monotonic_ns() -> int:
    """Return current monotonic clock time in nanoseconds."""
    return time.monotonic_ns()


def validate_timestamp_ms(value: int, field_name: str) -> None:
    """Validate that a millisecond timestamp is a positive integer."""
    if value <= 0:
        raise EventValidationError(f"{field_name} must be a positive integer, got {value}")


def event_age_ms(source_ts_ms: int, now_ms: int | None = None) -> int:
    """Return event age in milliseconds as now - source timestamp."""
    validate_timestamp_ms(source_ts_ms, "source_ts_ms")
    effective_now_ms = now_wall_ms() if now_ms is None else now_ms
    validate_timestamp_ms(effective_now_ms, "now_ms")
    return effective_now_ms - source_ts_ms
