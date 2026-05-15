from __future__ import annotations

from decimal import Decimal

from arbibot.core.events import ExternalSignal, FeatureSnapshot, SignalDirection, SignalState
from arbibot.model.graph import GraphDefinition, GraphEdge, GraphNode, GraphSignalResult


def _signed_value(value: float | None) -> Decimal:
    if value is None:
        return Decimal("0")
    dec = Decimal(str(value))
    if dec > 1:
        return Decimal("1")
    if dec < -1:
        return Decimal("-1")
    return dec


def _binary_penalty(flag: bool | None) -> Decimal:
    return Decimal("1") if flag else Decimal("0")


def graph_nodes_from_feature_snapshot(snapshot: FeatureSnapshot) -> list[GraphNode]:
    return [
        GraphNode(
            "return_1s",
            "spot",
            SignalDirection.BULL,
            value=_signed_value(snapshot.return_1s),
        ),
        GraphNode(
            "return_5s",
            "spot",
            SignalDirection.BULL,
            value=_signed_value(snapshot.return_5s),
        ),
        GraphNode(
            "acceleration_1s_2s",
            "spot",
            SignalDirection.BULL,
            value=_signed_value(snapshot.acceleration_1s_2s),
        ),
        GraphNode(
            "book_imbalance_3",
            "book",
            SignalDirection.BULL,
            value=_signed_value(snapshot.book_imbalance_3),
        ),
        GraphNode(
            "stale_spot",
            "quality",
            SignalDirection.NEUTRAL,
            value=-_binary_penalty(snapshot.stale_spot),
        ),
        GraphNode(
            "stale_book",
            "quality",
            SignalDirection.NEUTRAL,
            value=-_binary_penalty(snapshot.stale_book),
        ),
        GraphNode(
            "book_is_crossed",
            "quality",
            SignalDirection.NEUTRAL,
            value=-_binary_penalty(snapshot.book_is_crossed),
        ),
        GraphNode(
            "book_is_empty",
            "quality",
            SignalDirection.NEUTRAL,
            value=-_binary_penalty(snapshot.book_is_empty),
        ),
    ]


def build_default_graph_from_snapshot(snapshot: FeatureSnapshot) -> GraphDefinition:
    nodes = graph_nodes_from_feature_snapshot(snapshot)
    spread_high = snapshot.book_spread is not None and snapshot.book_spread > 0.03
    nodes.append(
        GraphNode(
            "high_spread",
            "quality",
            SignalDirection.NEUTRAL,
            value=-_binary_penalty(spread_high),
        )
    )

    edges = [
        GraphEdge("stale_spot", "return_1s", Decimal("0.5")),
        GraphEdge("stale_book", "book_imbalance_3", Decimal("0.5")),
        GraphEdge("book_is_crossed", "book_imbalance_3", Decimal("0.5")),
        GraphEdge("book_is_empty", "book_imbalance_3", Decimal("0.5")),
        GraphEdge("high_spread", "book_imbalance_3", Decimal("0.5")),
        GraphEdge("return_1s", "return_5s", Decimal("0.25")),
        GraphEdge("return_5s", "acceleration_1s_2s", Decimal("0.25")),
        GraphEdge("acceleration_1s_2s", "book_imbalance_3", Decimal("0.15")),
    ]
    return GraphDefinition(nodes=nodes, edges=edges)


def signal_state_from_graph_result(
    result: GraphSignalResult,
    event_id: str,
    source_ts_ms: int,
    recv_wall_ts_ms: int,
    recv_monotonic_ns: int,
) -> SignalState:
    return SignalState(
        event_id=event_id,
        source="arbibot.graph_fusion",
        source_ts_ms=source_ts_ms,
        recv_wall_ts_ms=recv_wall_ts_ms,
        recv_monotonic_ns=recv_monotonic_ns,
        direction=result.direction,
        confidence=float(result.confidence),
        conflict=float(result.conflict),
        bull_score=float(result.bull_score),
        bear_score=float(result.bear_score),
        convergence=float(result.convergence),
    )


def external_signal_to_graph_node(
    signal: ExternalSignal,
    now_source_ts_ms: int | None = None,
) -> GraphNode:
    strength = Decimal(str(signal.strength if signal.strength is not None else 0.5))
    if strength < 0:
        strength = Decimal("0")
    if strength > 1:
        strength = Decimal("1")

    freshness = Decimal("1")
    if now_source_ts_ms is not None and signal.expires_at_ms is not None:
        freshness = Decimal("0") if now_source_ts_ms > signal.expires_at_ms else Decimal("1")

    value = strength
    if signal.direction is SignalDirection.BEAR:
        value = -strength
    elif signal.direction is SignalDirection.NEUTRAL:
        value = Decimal("0")

    key = signal.signal_name or signal.provider
    return GraphNode(
        name=f"external_signal:{signal.provider}:{key}:{signal.source_ts_ms}",
        group="external",
        direction=signal.direction,
        value=value,
        confidence=strength,
        freshness=freshness,
    )
