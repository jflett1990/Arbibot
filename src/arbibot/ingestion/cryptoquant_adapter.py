from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from decimal import Decimal, InvalidOperation

from arbibot.core.events import ExternalSignal, SignalDirection
from arbibot.ingestion.interfaces import ExternalSignalClient
from arbibot.ingestion.tradingview_adapter import normalize_direction, normalize_strength


def _coerce_int(value: object, name: str) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be int-like") from exc


def _ttl_from_payload(value: object, default_ttl_ms: int) -> int:
    if value is None:
        return default_ttl_ms
    ttl = _coerce_int(value, "ttl_ms")
    if ttl <= 0:
        raise ValueError("ttl_ms must be > 0")
    return ttl


def _to_decimal(value: object, name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be numeric") from exc


def parse_cryptoquant_metric(
    payload: dict[str, object],
    recv_wall_ts_ms: int,
    recv_monotonic_ns: int,
    default_ttl_ms: int = 300_000,
) -> ExternalSignal:
    if recv_wall_ts_ms <= 0 or recv_monotonic_ns <= 0:
        raise ValueError("receive timestamps must be positive")
    if default_ttl_ms <= 0:
        raise ValueError("default_ttl_ms must be > 0")

    metric = str(payload.get("metric", "")).strip()
    if not metric:
        raise ValueError("metric is required")

    if "value" not in payload:
        raise ValueError("value is required")
    value = _to_decimal(payload["value"], "value")
    z_raw = payload.get("z_score")
    z_score = None if z_raw is None else _to_decimal(z_raw, "z_score")

    source_raw = payload.get("source_ts_ms", payload.get("timestamp"))
    if source_raw is None:
        source_ts_ms = recv_wall_ts_ms
        source_missing = True
    else:
        source_ts_ms = _coerce_int(source_raw, "source timestamp")
        if source_ts_ms <= 0:
            raise ValueError("source timestamp must be positive")
        source_missing = False

    direction_raw = payload.get("direction")
    direction = normalize_direction(direction_raw if isinstance(direction_raw, str) else None)
    if direction_raw is None and z_score is not None and "inflow" in metric.lower():
        if z_score >= 1:
            direction = SignalDirection.BEAR
        elif z_score <= -1:
            direction = SignalDirection.BULL
        else:
            direction = SignalDirection.NEUTRAL

    strength = normalize_strength(payload.get("strength"), default=Decimal("0.5"))
    asset = str(payload.get("asset", "BTC")).strip() or "BTC"
    interval = str(payload.get("interval", "")).strip() or None

    metadata: dict[str, str | int | float | bool | None] = {
        "asset": asset,
        "interval": interval,
        "exchange": str(payload.get("exchange", "")).strip() or None,
        "regime": str(payload.get("regime", "")).strip() or None,
        "metric_value": float(value),
        "z_score": None if z_score is None else float(z_score),
        "slow_context": True,
        "hot_path_trigger": False,
        "revision_risk": True,
        "source_timestamp_missing": source_missing,
        "context_only": True,
    }

    ttl_ms = default_ttl_ms
    return ExternalSignal(
        event_id=f"external:cryptoquant:{metric}:{asset}:{source_ts_ms}",
        source="cryptoquant",
        source_ts_ms=source_ts_ms,
        recv_wall_ts_ms=recv_wall_ts_ms,
        recv_monotonic_ns=recv_monotonic_ns,
        provider="CryptoQuant",
        direction=direction,
        strength=float(strength),
        ttl_ms=ttl_ms,
        symbol=asset,
        signal_name=metric,
        timeframe=interval,
        expires_at_ms=source_ts_ms + ttl_ms,
        metadata=metadata,
    )


class CryptoQuantSignalClient(ExternalSignalClient):
    source = "cryptoquant"

    def __init__(self, payloads: Sequence[dict[str, object]]) -> None:
        self._payloads = list(payloads)
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def events(self) -> AsyncIterator[ExternalSignal]:
        for payload in self._payloads:
            if not self._running:
                break
            recv_wall_ts_ms = payload.get("recv_wall_ts_ms")
            recv_monotonic_ns = payload.get("recv_monotonic_ns")
            if not isinstance(recv_wall_ts_ms, int) or not isinstance(recv_monotonic_ns, int):
                raise ValueError("payload must include recv_wall_ts_ms and recv_monotonic_ns")
            yield parse_cryptoquant_metric(
                payload,
                recv_wall_ts_ms=recv_wall_ts_ms,
                recv_monotonic_ns=recv_monotonic_ns,
                default_ttl_ms=_ttl_from_payload(payload.get("ttl_ms"), 300_000),
            )
