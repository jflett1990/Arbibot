from arbibot.core.events import HealthStatus
from arbibot.ops.health import HealthMonitor


def _eval(**kwargs: int | bool):
    monitor = HealthMonitor()
    return monitor.evaluate(
        clock_offset_ms=int(kwargs.get("clock_offset_ms", 0)),
        binance_event_age_ms=int(kwargs.get("binance_event_age_ms", 0)),
        polymarket_event_age_ms=int(kwargs.get("polymarket_event_age_ms", 0)),
        order_api_latency_p95_ms=int(kwargs.get("order_api_latency_p95_ms", 10)),
        unknown_order_state=bool(kwargs.get("unknown_order_state", False)),
        kill_switch_active=bool(kwargs.get("kill_switch_active", False)),
        risk_engine_disabled=bool(kwargs.get("risk_engine_disabled", False)),
        event_store_available=bool(kwargs.get("event_store_available", True)),
        market_metadata_available=bool(kwargs.get("market_metadata_available", True)),
    )


def test_health_all_healthy() -> None:
    s = _eval()
    assert s.status is HealthStatus.HEALTHY
    assert s.can_consider_trade is True


def test_clock_warn_degraded_and_clock_blocked() -> None:
    assert _eval(clock_offset_ms=30).status is HealthStatus.DEGRADED
    assert _eval(clock_offset_ms=130).status is HealthStatus.BLOCKED


def test_stale_and_blockers() -> None:
    assert _eval(binance_event_age_ms=900).status is HealthStatus.BLOCKED
    assert _eval(polymarket_event_age_ms=1200).status is HealthStatus.BLOCKED
    assert _eval(unknown_order_state=True).status is HealthStatus.BLOCKED
    assert _eval(kill_switch_active=True).status is HealthStatus.BLOCKED
    assert _eval(risk_engine_disabled=True).status is HealthStatus.BLOCKED
    assert _eval(market_metadata_available=False).status is HealthStatus.BLOCKED


def test_reasons_accumulate() -> None:
    s = _eval(clock_offset_ms=130, binance_event_age_ms=999, kill_switch_active=True)
    assert len(s.reasons) >= 3
