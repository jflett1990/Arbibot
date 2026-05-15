"""Deterministic spot feature extraction from trade-like ticks."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from decimal import Decimal
from math import log, sqrt

from arbibot.core.errors import EventValidationError
from arbibot.core.events import SpotTick
from arbibot.market.candles import is_trade_like_tick


@dataclass(frozen=True, slots=True)
class _SpotPoint:
    ts_ms: int
    price: Decimal
    size: Decimal


class SpotFeatureWindow:
    def __init__(self, symbol: str, max_window_ms: int = 300_000) -> None:
        if max_window_ms <= 0:
            raise ValueError("max_window_ms must be positive")
        self.symbol = symbol
        self.max_window_ms = max_window_ms
        self._points: deque[_SpotPoint] = deque()
        self._latest_source_ts_ms: int | None = None

    def add_tick(self, tick: SpotTick) -> None:
        if not is_trade_like_tick(tick):
            return
        if tick.symbol != self.symbol:
            raise EventValidationError(
                f"SpotTick symbol mismatch: expected {self.symbol}, got {tick.symbol}"
            )
        if tick.price <= 0:
            raise EventValidationError(f"SpotTick price must be > 0, got {tick.price}")
        if tick.size is None or tick.size <= 0:
            raise EventValidationError(f"SpotTick size must be > 0, got {tick.size}")

        point = _SpotPoint(
            tick.source_ts_ms,
            Decimal(str(tick.price)),
            Decimal(str(tick.size)),
        )
        self._points.append(point)
        self._latest_source_ts_ms = max(
            self._latest_source_ts_ms or tick.source_ts_ms,
            tick.source_ts_ms,
        )
        self._prune()

    def latest_price(self) -> Decimal | None:
        if not self._points:
            return None
        return self._points[-1].price

    def return_over_ms(self, window_ms: int) -> Decimal | None:
        self._validate_window_ms(window_ms)
        if not self._points or self._latest_source_ts_ms is None:
            return None
        latest = self._points[-1]
        cutoff = self._latest_source_ts_ms - window_ms
        prior = self._find_prior(cutoff)
        if prior is None:
            return None
        return (latest.price / prior.price) - Decimal("1")

    def realized_volatility_ms(self, window_ms: int) -> Decimal | None:
        self._validate_window_ms(window_ms)
        if self._latest_source_ts_ms is None:
            return None
        cutoff = self._latest_source_ts_ms - window_ms
        points = [p for p in self._points if p.ts_ms >= cutoff]
        if len(points) < 3:
            return None
        rets: list[float] = []
        for prev, cur in zip(points, points[1:], strict=False):
            rets.append(log(float(cur.price / prev.price)))
        if len(rets) < 2:
            return None
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        return Decimal(str(sqrt(var)))

    def momentum_slope_ms(self, window_ms: int) -> Decimal | None:
        self._validate_window_ms(window_ms)
        if self._latest_source_ts_ms is None:
            return None
        cutoff = self._latest_source_ts_ms - window_ms
        points = [p for p in self._points if p.ts_ms >= cutoff]
        if len(points) < 2:
            return None
        first = points[0]
        last = points[-1]
        dt = last.ts_ms - first.ts_ms
        if dt <= 0:
            return None
        return (last.price - first.price) / Decimal(dt)

    def acceleration(self, short_ms: int = 1_000, long_ms: int = 2_000) -> Decimal | None:
        short_ret = self.return_over_ms(short_ms)
        long_ret = self.return_over_ms(long_ms)
        if short_ret is None or long_ret is None:
            return None
        return short_ret - long_ret

    def distance_to_threshold(self, threshold_price: Decimal) -> Decimal | None:
        latest = self.latest_price()
        if latest is None:
            return None
        return latest - threshold_price

    def latest_source_ts_ms(self) -> int | None:
        return self._latest_source_ts_ms

    def snapshot(self, now_source_ts_ms: int | None = None) -> dict[str, Decimal | None]:
        if now_source_ts_ms is not None and now_source_ts_ms < 0:
            raise ValueError("now_source_ts_ms must be >= 0")
        return {
            "latest_price": self.latest_price(),
            "return_250ms": self.return_over_ms(250),
            "return_500ms": self.return_over_ms(500),
            "return_1s": self.return_over_ms(1_000),
            "return_2s": self.return_over_ms(2_000),
            "return_5s": self.return_over_ms(5_000),
            "return_10s": self.return_over_ms(10_000),
            "realized_vol_5s": self.realized_volatility_ms(5_000),
            "realized_vol_30s": self.realized_volatility_ms(30_000),
            "momentum_slope_5s": self.momentum_slope_ms(5_000),
            "acceleration_1s_2s": self.acceleration(1_000, 2_000),
        }

    def _find_prior(self, cutoff_ts_ms: int) -> _SpotPoint | None:
        chosen: _SpotPoint | None = None
        for point in self._points:
            if point.ts_ms <= cutoff_ts_ms:
                chosen = point
            else:
                break
        return chosen

    def _validate_window_ms(self, window_ms: int) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")

    def _prune(self) -> None:
        if self._latest_source_ts_ms is None:
            return
        cutoff = self._latest_source_ts_ms - self.max_window_ms
        while self._points and self._points[0].ts_ms < cutoff:
            self._points.popleft()
