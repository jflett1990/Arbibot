from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from arbibot.core.time import now_wall_ms
from arbibot.ops.health import SystemHealth
from arbibot.ops.metrics import MetricsRegistry
from arbibot.replay.summary import ReplaySummary
from arbibot.risk.engine import RiskEngineState


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    health: SystemHealth
    metrics: dict[str, object]
    risk_state: dict[str, Any] | None
    replay_summary: dict[str, Any] | None
    generated_at_ms: int

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, default=str)


def build_runtime_status(
    health: SystemHealth,
    metrics: MetricsRegistry,
    risk_state: RiskEngineState | None = None,
    replay_summary: ReplaySummary | None = None,
    generated_at_ms: int | None = None,
) -> RuntimeStatus:
    return RuntimeStatus(
        health=health,
        metrics=metrics.snapshot(),
        risk_state=None if risk_state is None else asdict(risk_state),
        replay_summary=None if replay_summary is None else asdict(replay_summary),
        generated_at_ms=now_wall_ms() if generated_at_ms is None else generated_at_ms,
    )
