from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GateCode(StrEnum):
    MAX_SPREAD_BPS = "MAX_SPREAD_BPS"
    MIN_LIQUIDITY = "MIN_LIQUIDITY"
    MAX_BOOK_AGE_MS = "MAX_BOOK_AGE_MS"
    MIN_RAW_EDGE_BPS = "MIN_RAW_EDGE_BPS"
    MIN_COST_ADJUSTED_EDGE_BPS = "MIN_COST_ADJUSTED_EDGE_BPS"
    MAX_LATENCY_MS = "MAX_LATENCY_MS"
    REQUIRED_BOTH_SIDES_PRESENT = "REQUIRED_BOTH_SIDES_PRESENT"
    NO_MISSING_BINANCE_CONTEXT = "NO_MISSING_BINANCE_CONTEXT"
    NO_MISSING_POLYMARKET_CONTEXT = "NO_MISSING_POLYMARKET_CONTEXT"


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    reason_code: GateCode
    explanation: str
    measured_value: float | bool | None
    threshold: float | bool | None


def _gate(
    passed: bool,
    code: GateCode,
    measured: float | bool | None,
    threshold: float | bool | None,
    ok: str,
    bad: str,
) -> GateResult:
    return GateResult(passed, code, ok if passed else bad, measured, threshold)


def evaluate_gates(
    row: dict[str, float | int | str | bool | None], thresholds: dict[str, float | int | bool]
) -> list[GateResult]:
    spread = row.get("spread_bps")
    liq = row.get("liquidity_available")
    age = row.get("book_age_ms")
    raw = row.get("raw_edge_bps")
    net = row.get("cost_adjusted_edge_bps")
    latency = row.get("latency_ms")
    bid = row.get("polymarket_best_bid")
    ask = row.get("polymarket_best_ask")
    binance = row.get("binance_price")
    missing_poly = bid is None or ask is None
    out = [
        _gate(
            spread is not None and float(spread) <= float(thresholds.get("max_spread_bps", 500)),
            GateCode.MAX_SPREAD_BPS,
            None if spread is None else float(spread),
            float(thresholds.get("max_spread_bps", 500)),
            "spread within threshold",
            "spread missing or too wide",
        ),
        _gate(
            liq is not None and float(liq) >= float(thresholds.get("min_liquidity", 0)),
            GateCode.MIN_LIQUIDITY,
            None if liq is None else float(liq),
            float(thresholds.get("min_liquidity", 0)),
            "liquidity sufficient",
            "liquidity missing or too low",
        ),
        _gate(
            age is not None and float(age) <= float(thresholds.get("max_book_age_ms", 1000)),
            GateCode.MAX_BOOK_AGE_MS,
            None if age is None else float(age),
            float(thresholds.get("max_book_age_ms", 1000)),
            "book fresh",
            "book stale or missing",
        ),
        _gate(
            raw is not None and float(raw) >= float(thresholds.get("min_raw_edge_bps", 0)),
            GateCode.MIN_RAW_EDGE_BPS,
            None if raw is None else float(raw),
            float(thresholds.get("min_raw_edge_bps", 0)),
            "raw edge sufficient",
            "raw edge missing or too low",
        ),
        _gate(
            net is not None
            and float(net) >= float(thresholds.get("min_cost_adjusted_edge_bps", 0)),
            GateCode.MIN_COST_ADJUSTED_EDGE_BPS,
            None if net is None else float(net),
            float(thresholds.get("min_cost_adjusted_edge_bps", 0)),
            "cost-adjusted edge sufficient",
            "cost-adjusted edge missing or too low",
        ),
        _gate(
            latency is not None and float(latency) <= float(thresholds.get("max_latency_ms", 1000)),
            GateCode.MAX_LATENCY_MS,
            None if latency is None else float(latency),
            float(thresholds.get("max_latency_ms", 1000)),
            "latency within threshold",
            "latency missing or too high",
        ),
        _gate(
            not missing_poly,
            GateCode.REQUIRED_BOTH_SIDES_PRESENT,
            not missing_poly,
            True,
            "both sides present",
            "missing bid or ask",
        ),
        _gate(
            binance is not None,
            GateCode.NO_MISSING_BINANCE_CONTEXT,
            binance is not None,
            True,
            "Binance context present",
            "missing Binance context",
        ),
        _gate(
            not missing_poly,
            GateCode.NO_MISSING_POLYMARKET_CONTEXT,
            not missing_poly,
            True,
            "Polymarket context present",
            "missing Polymarket context",
        ),
    ]
    return out
