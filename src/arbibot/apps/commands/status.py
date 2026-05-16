from __future__ import annotations

import json
from pathlib import Path

from arbibot.core.config import load_config
from arbibot.ops.health import HealthMonitor
from arbibot.ops.metrics import MetricsRegistry
from arbibot.ops.status import build_runtime_status


def run_status(config_path: str, as_json: bool, generated_at_ms: int | None = None) -> int:
    try:
        load_config(Path(config_path))
    except Exception as exc:  # noqa: BLE001
        if as_json:
            print(json.dumps({"ok": False, "error": str(exc)}))
        else:
            print(f"Status failed: {exc}")
        return 1

    health = HealthMonitor().evaluate(
        clock_offset_ms=0,
        binance_event_age_ms=0,
        polymarket_event_age_ms=0,
        order_api_latency_p95_ms=0,
        unknown_order_state=False,
        kill_switch_active=False,
        risk_engine_disabled=False,
        event_store_available=True,
        market_metadata_available=True,
    )
    metrics = MetricsRegistry()
    status = build_runtime_status(health, metrics, generated_at_ms=generated_at_ms)
    if as_json:
        print(status.to_json())
    else:
        print(f"health={status.health.status} can_submit={status.health.can_submit_orders}")
    return 0
