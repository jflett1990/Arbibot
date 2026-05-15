from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from decimal import Decimal, InvalidOperation

from arbibot.core.events import ExternalSignal, SignalDirection
from arbibot.ingestion.interfaces import ExternalSignalClient

_BULL = {"bull", "bullish", "buy", "long", "up"}
_BEAR = {"bear", "bearish", "sell", "short", "down"}
_NEUTRAL = {"neutral", "flat", "none"}


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


def normalize_direction(value: str | None) -> SignalDirection:
    if value is None:
        return SignalDirection.NEUTRAL
    normalized = value.strip().lower()
    if normalized in _BULL:
        return SignalDirection.BULL
    if normalized in _BEAR:
        return SignalDirection.BEAR
    if normalized in _NEUTRAL:
        return SignalDirection.NEUTRAL
    return SignalDirection.NEUTRAL


def normalize_strength(value: object | None, default: Decimal = Decimal("0.5")) -> Decimal:
    if value is None:
        return default
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("strength must be numeric") from exc
    if dec < 0:
        return Decimal("0")
    if dec > 1:
        return Decimal("1")
    return dec


def _coerce_source_ts(payload: dict[str, object], recv_wall_ts_ms: int) -> tuple[int, bool]:
    raw = payload.get("source_ts_ms", payload.get("timestamp"))
    if raw is None:
        return recv_wall_ts_ms, True
    try:
        value = _coerce_int(raw, "source timestamp")
    except (TypeError, ValueError) as exc:
        raise ValueError("source timestamp must be int-like") from exc
    if value <= 0:
        raise ValueError("source timestamp must be positive")
    return value, False


def parse_tradingview_payload(
    payload: dict[str, object],
    recv_wall_ts_ms: int,
    recv_monotonic_ns: int,
    default_ttl_ms: int = 60_000,
) -> ExternalSignal:
    if recv_wall_ts_ms <= 0 or recv_monotonic_ns <= 0:
        raise ValueError("receive timestamps must be positive")
    if default_ttl_ms <= 0:
        raise ValueError("default_ttl_ms must be > 0")

    symbol = str(payload.get("symbol", "")).strip()
    if not symbol:
        raise ValueError("symbol is required")

    indicator = str(payload.get("indicator", "")).strip()
    message = str(payload.get("message", "")).strip()
    if not indicator and not message:
        raise ValueError("indicator or message is required")

    source_ts_ms, ts_missing = _coerce_source_ts(payload, recv_wall_ts_ms)
    direction_raw = payload.get("direction")
    direction = normalize_direction(direction_raw if isinstance(direction_raw, str) else None)
    strength = normalize_strength(payload.get("strength"))
    ttl_ms = default_ttl_ms
    signal_name = indicator or message
    timeframe = str(payload.get("timeframe", "")).strip() or None
    strategy = str(payload.get("strategy", "")).strip() or None

    metadata: dict[str, str | int | float | bool | None] = {
        "message": message or None,
        "strategy": strategy,
        "source_timestamp_missing": ts_missing,
        "context_only": True,
        "hot_path_trigger": False,
    }

    return ExternalSignal(
        event_id=f"external:tradingview:{symbol}:{signal_name}:{source_ts_ms}",
        source="tradingview",
        source_ts_ms=source_ts_ms,
        recv_wall_ts_ms=recv_wall_ts_ms,
        recv_monotonic_ns=recv_monotonic_ns,
        provider="TradingView",
        direction=direction,
        strength=float(strength),
        ttl_ms=ttl_ms,
        symbol=symbol,
        signal_name=signal_name,
        timeframe=timeframe,
        expires_at_ms=source_ts_ms + ttl_ms,
        metadata=metadata,
    )


class TradingViewSignalClient(ExternalSignalClient):
    source = "tradingview"

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
            yield parse_tradingview_payload(
                payload,
                recv_wall_ts_ms=recv_wall_ts_ms,
                recv_monotonic_ns=recv_monotonic_ns,
                default_ttl_ms=_ttl_from_payload(payload.get("ttl_ms"), 60_000),
            )
