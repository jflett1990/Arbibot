import json
from decimal import Decimal

from arbibot.ops.health import HealthMonitor
from arbibot.ops.metrics import MetricsRegistry
from arbibot.ops.status import build_runtime_status
from arbibot.replay.summary import ReplaySummary
from arbibot.risk.engine import RiskEngineState


def test_runtime_status_contents_and_json() -> None:
    health = HealthMonitor().evaluate(
        clock_offset_ms=0,
        binance_event_age_ms=0,
        polymarket_event_age_ms=0,
        order_api_latency_p95_ms=10,
        unknown_order_state=False,
        kill_switch_active=False,
        risk_engine_disabled=False,
        event_store_available=True,
        market_metadata_available=True,
    )
    metrics = MetricsRegistry()
    metrics.increment("events_total", 2)
    risk = RiskEngineState(realized_daily_pnl=Decimal("3"))
    replay = ReplaySummary(total_events=5)
    status = build_runtime_status(
        health=health,
        metrics=metrics,
        risk_state=risk,
        replay_summary=replay,
        generated_at_ms=123,
    )
    assert status.generated_at_ms == 123
    assert status.metrics["counters"]["events_total"] == 2
    assert status.risk_state is not None
    assert status.replay_summary is not None

    payload = json.loads(status.to_json())
    assert payload["generated_at_ms"] == 123
    assert payload["health"]["status"] == "HEALTHY"
