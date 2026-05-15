"""Deterministic candle construction from trade-like spot ticks."""

from __future__ import annotations

from dataclasses import dataclass

from arbibot.core.errors import EventValidationError
from arbibot.core.events import SpotBar, SpotTick


def is_trade_like_tick(tick: SpotTick) -> bool:
    """Return whether a tick is a trade-like market event."""
    return tick.stream_event_type in {"aggTrade", "trade"}


@dataclass
class _OpenBarState:
    symbol: str
    interval_ms: int
    start_ts_ms: int
    end_ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
    latest_recv_wall_ts_ms: int
    latest_recv_monotonic_ns: int

    def update(self, tick: SpotTick) -> None:
        price = float(tick.price)
        size = float(tick.size) if tick.size is not None else 0.0
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += size
        self.trade_count += 1
        self.latest_recv_wall_ts_ms = max(self.latest_recv_wall_ts_ms, tick.recv_wall_ts_ms)
        self.latest_recv_monotonic_ns = max(self.latest_recv_monotonic_ns, tick.recv_monotonic_ns)

    def finalize(self) -> SpotBar:
        event_id = (
            f"bar:{self.symbol}:{self.interval_ms}:{self.start_ts_ms}:{self.end_ts_ms}"
        )
        return SpotBar(
            event_id=event_id,
            source="arbibot.candle_builder",
            source_ts_ms=self.end_ts_ms,
            recv_wall_ts_ms=self.latest_recv_wall_ts_ms,
            recv_monotonic_ns=self.latest_recv_monotonic_ns,
            symbol=self.symbol,
            interval_ms=self.interval_ms,
            start_ts_ms=self.start_ts_ms,
            end_ts_ms=self.end_ts_ms,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            trade_count=self.trade_count,
        )


class CandleBuilder:
    def __init__(
        self,
        interval_ms: int = 300_000,
        allowed_lateness_ms: int = 1_000,
        ignore_non_trade_ticks: bool = True,
    ) -> None:
        if interval_ms <= 0:
            raise ValueError("interval_ms must be positive")
        if allowed_lateness_ms < 0:
            raise ValueError("allowed_lateness_ms must be >= 0")
        self.interval_ms = interval_ms
        self.allowed_lateness_ms = allowed_lateness_ms
        self.ignore_non_trade_ticks = ignore_non_trade_ticks
        self._open_bars: dict[int, _OpenBarState] = {}
        self._max_observed_source_ts_ms: int | None = None

    def add_tick(self, tick: SpotTick) -> list[SpotBar]:
        if not is_trade_like_tick(tick):
            if self.ignore_non_trade_ticks:
                return []
            raise EventValidationError(
                f"Non-trade tick not allowed: stream_event_type={tick.stream_event_type}"
            )

        self._validate_tick(tick)

        if self._max_observed_source_ts_ms is None:
            self._max_observed_source_ts_ms = tick.source_ts_ms
        else:
            self._max_observed_source_ts_ms = max(
                self._max_observed_source_ts_ms,
                tick.source_ts_ms,
            )

        finalized_before = self._finalized_boundary_start_ms()
        bucket_start = self._bucket_start_ms(tick.source_ts_ms)

        if bucket_start < finalized_before:
            return []

        state = self._open_bars.get(bucket_start)
        if state is None:
            size = tick.size
            assert size is not None
            state = _OpenBarState(
                symbol=tick.symbol,
                interval_ms=self.interval_ms,
                start_ts_ms=bucket_start,
                end_ts_ms=bucket_start + self.interval_ms,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                volume=size,
                trade_count=1,
                latest_recv_wall_ts_ms=tick.recv_wall_ts_ms,
                latest_recv_monotonic_ns=tick.recv_monotonic_ns,
            )
            self._open_bars[bucket_start] = state
        else:
            state.update(tick)

        return self._finalize_closed_bars()

    def flush(self, finalize_all: bool = True) -> list[SpotBar]:
        if not finalize_all:
            return []
        bars = [self._open_bars[start].finalize() for start in sorted(self._open_bars)]
        self._open_bars.clear()
        self._max_observed_source_ts_ms = None
        return bars

    def _bucket_start_ms(self, source_ts_ms: int) -> int:
        return (source_ts_ms // self.interval_ms) * self.interval_ms

    def _finalized_boundary_start_ms(self) -> int:
        if self._max_observed_source_ts_ms is None:
            return -1
        latest_allowed_ts = self._max_observed_source_ts_ms - self.allowed_lateness_ms
        return self._bucket_start_ms(latest_allowed_ts)

    def _finalize_closed_bars(self) -> list[SpotBar]:
        boundary_start = self._finalized_boundary_start_ms()
        finalized_starts = [start for start in self._open_bars if start < boundary_start]
        bars: list[SpotBar] = []
        for start in sorted(finalized_starts):
            bars.append(self._open_bars.pop(start).finalize())
        return bars

    def _validate_tick(self, tick: SpotTick) -> None:
        if not tick.symbol:
            raise EventValidationError("SpotTick.symbol is required")
        if tick.price <= 0:
            raise EventValidationError(f"SpotTick.price must be > 0, got {tick.price}")
        if tick.size is None or tick.size <= 0:
            raise EventValidationError(f"SpotTick.size must be > 0, got {tick.size}")
