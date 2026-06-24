from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResearchFeatureRow:
    decision_time_ms: int
    market_id: str | None
    token_id: str | None
    binance_price: float | None
    polymarket_best_bid: float | None
    polymarket_best_ask: float | None
    spread: float | None
    spread_bps: float | None
    book_age_ms: int | None
    impulse_return_bps: float | None
    estimated_fair_price: float | None
    observed_price: float | None
    raw_edge_bps: float | None
    cost_adjusted_edge_bps: float | None
    liquidity_available: float | None
    latency_ms: int
    missing_binance_context: bool
    missing_polymarket_context: bool


class RollingImpulse:
    def __init__(self, window_ms: int) -> None:
        if window_ms <= 0:
            raise ValueError("window_ms must be positive")
        self.window_ms = window_ms
        self._ticks: deque[tuple[int, float]] = deque()

    def add(self, ts_ms: int, price: float) -> float | None:
        if price <= 0:
            raise ValueError("price must be positive")
        self._ticks.append((ts_ms, price))
        cutoff = ts_ms - self.window_ms
        while len(self._ticks) > 1 and self._ticks[0][0] < cutoff:
            self._ticks.popleft()
        if len(self._ticks) < 2:
            return None
        first = self._ticks[0][1]
        return (price / first - 1.0) * 10_000.0


def estimate_fair_price(impulse_return_bps: float | None) -> float | None:
    if impulse_return_bps is None:
        return None
    return max(0.0, min(1.0, 0.5 + impulse_return_bps / 20_000.0))


def build_feature_row(
    *,
    decision_time_ms: int,
    market_id: str | None,
    token_id: str | None,
    binance_price: float | None,
    best_bid: float | None,
    best_ask: float | None,
    bid_size: float | None,
    ask_size: float | None,
    book_ts_ms: int | None,
    impulse_return_bps: float | None,
    latency_ms: int,
    fee_bps: float,
    slippage_bps: float,
) -> ResearchFeatureRow:
    spread = best_ask - best_bid if best_bid is not None and best_ask is not None else None
    observed = best_ask if best_ask is not None else best_bid
    fair = estimate_fair_price(impulse_return_bps)
    raw_edge = (fair - observed) * 10_000.0 if fair is not None and observed is not None else None
    net = raw_edge - fee_bps - slippage_bps if raw_edge is not None else None
    mid = (best_bid + best_ask) / 2.0 if best_bid is not None and best_ask is not None else None
    spread_bps = spread / mid * 10_000.0 if spread is not None and mid and mid > 0 else None
    liq = (
        min(bid_size or 0.0, ask_size or 0.0)
        if best_bid is not None and best_ask is not None
        else None
    )
    age = decision_time_ms - book_ts_ms if book_ts_ms is not None else None
    return ResearchFeatureRow(
        decision_time_ms,
        market_id,
        token_id,
        binance_price,
        best_bid,
        best_ask,
        spread,
        spread_bps,
        age,
        impulse_return_bps,
        fair,
        observed,
        raw_edge,
        net,
        liq,
        latency_ms,
        binance_price is None,
        best_bid is None or best_ask is None,
    )
