from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LatencyConfig:
    data_delay_ms: int = 0
    decision_delay_ms: int = 0
    order_submit_delay_ms: int = 0
    cancel_delay_ms: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "data_delay_ms",
            "decision_delay_ms",
            "order_submit_delay_ms",
            "cancel_delay_ms",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be >= 0")


def apply_delay_ms(ts_ms: int, delay_ms: int) -> int:
    if delay_ms < 0:
        raise ValueError("delay_ms must be >= 0")
    return ts_ms + delay_ms


def adjusted_event_time(source_ts_ms: int, data_delay_ms: int) -> int:
    return apply_delay_ms(source_ts_ms, data_delay_ms)
