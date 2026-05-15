from __future__ import annotations

from dataclasses import dataclass, field

from arbibot.core.events import HealthStatus


@dataclass(frozen=True, slots=True)
class HealthThresholds:
    max_clock_offset_ms: int = 100
    warn_clock_offset_ms: int = 25
    max_binance_event_age_ms: int = 750
    max_polymarket_event_age_ms: int = 1000
    max_order_api_latency_p95_ms: int = 750


@dataclass(frozen=True, slots=True)
class HealthCheckResult:
    name: str
    status: HealthStatus
    reason: str | None = None
    metadata: dict[str, str | int | float | bool | None] | None = None


@dataclass(frozen=True, slots=True)
class SystemHealth:
    status: HealthStatus
    checks: list[HealthCheckResult]
    can_consider_trade: bool
    can_submit_orders: bool
    reasons: list[str] = field(default_factory=list)


class HealthMonitor:
    def __init__(self, thresholds: HealthThresholds | None = None) -> None:
        self.thresholds = thresholds or HealthThresholds()

    def evaluate(
        self,
        *,
        clock_offset_ms: int,
        binance_event_age_ms: int,
        polymarket_event_age_ms: int,
        order_api_latency_p95_ms: int,
        unknown_order_state: bool,
        kill_switch_active: bool,
        risk_engine_disabled: bool,
        event_store_available: bool,
        market_metadata_available: bool,
    ) -> SystemHealth:
        checks: list[HealthCheckResult] = []

        if clock_offset_ms > self.thresholds.max_clock_offset_ms:
            checks.append(
                HealthCheckResult(
                    "clock_offset_ms",
                    HealthStatus.BLOCKED,
                    "CLOCK_OFFSET_MAX_EXCEEDED",
                )
            )
        elif clock_offset_ms > self.thresholds.warn_clock_offset_ms:
            checks.append(
                HealthCheckResult(
                    "clock_offset_ms",
                    HealthStatus.DEGRADED,
                    "CLOCK_OFFSET_WARN_EXCEEDED",
                )
            )
        else:
            checks.append(HealthCheckResult("clock_offset_ms", HealthStatus.HEALTHY))

        stale_binance = binance_event_age_ms > self.thresholds.max_binance_event_age_ms
        stale_poly = polymarket_event_age_ms > self.thresholds.max_polymarket_event_age_ms
        high_order_latency = (
            order_api_latency_p95_ms > self.thresholds.max_order_api_latency_p95_ms
        )

        checks.append(
            HealthCheckResult(
                "binance_event_age_ms",
                HealthStatus.BLOCKED if stale_binance else HealthStatus.HEALTHY,
                "BINANCE_STALE" if stale_binance else None,
            )
        )
        checks.append(
            HealthCheckResult(
                "polymarket_event_age_ms",
                HealthStatus.BLOCKED if stale_poly else HealthStatus.HEALTHY,
                "POLYMARKET_STALE" if stale_poly else None,
            )
        )
        checks.append(
            HealthCheckResult(
                "order_api_latency_p95_ms",
                HealthStatus.DEGRADED if high_order_latency else HealthStatus.HEALTHY,
                "ORDER_API_LATENCY_HIGH" if high_order_latency else None,
            )
        )
        checks.append(
            HealthCheckResult(
                "unknown_order_state",
                HealthStatus.BLOCKED if unknown_order_state else HealthStatus.HEALTHY,
                "UNKNOWN_ORDER_STATE" if unknown_order_state else None,
            )
        )
        checks.append(
            HealthCheckResult(
                "kill_switch_active",
                HealthStatus.BLOCKED if kill_switch_active else HealthStatus.HEALTHY,
                "KILL_SWITCH_ACTIVE" if kill_switch_active else None,
            )
        )
        checks.append(
            HealthCheckResult(
                "risk_engine_disabled",
                HealthStatus.BLOCKED if risk_engine_disabled else HealthStatus.HEALTHY,
                "RISK_ENGINE_DISABLED" if risk_engine_disabled else None,
            )
        )
        checks.append(
            HealthCheckResult(
                "event_store_available",
                HealthStatus.DEGRADED if not event_store_available else HealthStatus.HEALTHY,
                "EVENT_STORE_UNAVAILABLE" if not event_store_available else None,
            )
        )
        checks.append(
            HealthCheckResult(
                "market_metadata_available",
                HealthStatus.BLOCKED if not market_metadata_available else HealthStatus.HEALTHY,
                "MARKET_METADATA_UNAVAILABLE" if not market_metadata_available else None,
            )
        )

        reasons = [check.reason for check in checks if check.reason is not None]
        status = HealthStatus.HEALTHY
        if any(check.status is HealthStatus.BLOCKED for check in checks):
            status = HealthStatus.BLOCKED
        elif any(check.status is HealthStatus.DEGRADED for check in checks):
            status = HealthStatus.DEGRADED

        can_consider_trade = status is not HealthStatus.BLOCKED
        can_submit_orders = status is not HealthStatus.BLOCKED and not (
            unknown_order_state or kill_switch_active or risk_engine_disabled
        )
        return SystemHealth(
            status=status,
            checks=checks,
            can_consider_trade=can_consider_trade,
            can_submit_orders=can_submit_orders,
            reasons=reasons,
        )
