from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ReplaySummary:
    total_events: int = 0
    deserialized_events: int = 0
    malformed_events: int = 0
    unknown_events: int = 0
    spot_ticks: int = 0
    spot_bars_input: int = 0
    candles_emitted: int = 0
    book_snapshots: int = 0
    book_deltas: int = 0
    orphan_book_deltas: int = 0
    poly_trades: int = 0
    external_signals: int = 0
    feature_snapshots: int = 0
    decisions_total: int = 0
    decisions_trade: int = 0
    decisions_no_trade: int = 0
    order_events_total: int = 0
    orders_filled: int = 0
    orders_partially_filled: int = 0
    orders_rejected: int = 0
    orders_cancelled: int = 0
    orders_expired_or_no_fill: int = 0
    skipped_no_book: int = 0
    max_drawdown: float | None = None
    gross_pnl: float | None = None
    net_pnl: float | None = None
