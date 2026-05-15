from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from math import isfinite

from arbibot.core.events import SignalDirection


class GraphError(ValueError):
    """Raised when graph construction or execution fails validation."""


@dataclass(frozen=True, slots=True)
class GraphNode:
    name: str
    group: str
    direction: SignalDirection
    value: Decimal = Decimal("0")
    confidence: Decimal = Decimal("1")
    freshness: Decimal = Decimal("1")


@dataclass(frozen=True, slots=True)
class GraphEdge:
    source: str
    target: str
    weight: Decimal


@dataclass(frozen=True, slots=True)
class GraphDefinition:
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class GraphInput:
    definition: GraphDefinition


@dataclass(frozen=True, slots=True)
class GraphSignalResult:
    direction: SignalDirection
    bull_score: Decimal
    bear_score: Decimal
    convergence: Decimal
    conflict: Decimal
    confidence: Decimal
    node_scores: dict[str, Decimal] = field(default_factory=dict)


class GraphFusionModel:
    def run(self, graph_input: GraphInput) -> GraphSignalResult:
        graph = graph_input.definition
        self._validate_graph(graph)

        if not graph.nodes:
            return GraphSignalResult(
                direction=SignalDirection.NEUTRAL,
                bull_score=Decimal("0"),
                bear_score=Decimal("0"),
                convergence=Decimal("0"),
                conflict=Decimal("0"),
                confidence=Decimal("0"),
                node_scores={},
            )

        base_scores: dict[str, Decimal] = {}
        accum: dict[str, Decimal] = {node.name: Decimal("0") for node in graph.nodes}
        node_map: dict[str, GraphNode] = {node.name: node for node in graph.nodes}

        for node in graph.nodes:
            base_scores[node.name] = node.value * node.confidence * node.freshness

        for edge in graph.edges:
            accum[edge.target] += base_scores[edge.source] * edge.weight

        node_scores = {
            node.name: base_scores[node.name] + accum[node.name] for node in graph.nodes
        }

        bull_score = sum(
            (
                max(score, Decimal("0"))
                for name, score in node_scores.items()
                if node_map[name].direction is SignalDirection.BULL
            ),
            start=Decimal("0"),
        )
        bear_score = sum(
            (
                max(score, Decimal("0"))
                for name, score in node_scores.items()
                if node_map[name].direction is SignalDirection.BEAR
            ),
            start=Decimal("0"),
        )

        if bull_score == 0 and bear_score == 0:
            conflict = Decimal("0")
            convergence = Decimal("0")
        else:
            hi: Decimal = max(bull_score, bear_score)
            lo: Decimal = min(bull_score, bear_score)
            conflict = lo / hi
            convergence = abs(bull_score - bear_score) / (bull_score + bear_score)

        confidence = self._clamp(convergence * (Decimal("1") - conflict))

        direction = SignalDirection.NEUTRAL
        if bull_score > bear_score and confidence > 0:
            direction = SignalDirection.BULL
        elif bear_score > bull_score and confidence > 0:
            direction = SignalDirection.BEAR

        return GraphSignalResult(
            direction=direction,
            bull_score=bull_score,
            bear_score=bear_score,
            convergence=convergence,
            conflict=conflict,
            confidence=confidence,
            node_scores=node_scores,
        )

    def _validate_graph(self, graph: GraphDefinition) -> None:
        names: set[str] = set()
        for node in graph.nodes:
            if not node.name.strip():
                raise GraphError("node name must be non-empty")
            if node.name in names:
                raise GraphError(f"duplicate node name: {node.name}")
            names.add(node.name)
            self._validate_range("node.value", node.value, Decimal("-1"), Decimal("1"))
            self._validate_range("node.confidence", node.confidence, Decimal("0"), Decimal("1"))
            self._validate_range("node.freshness", node.freshness, Decimal("0"), Decimal("1"))

        edge_set: set[tuple[str, str]] = set()
        for edge in graph.edges:
            if edge.source not in names:
                raise GraphError(f"edge source does not exist: {edge.source}")
            if edge.target not in names:
                raise GraphError(f"edge target does not exist: {edge.target}")
            if not isfinite(float(edge.weight)):
                raise GraphError("edge weight must be finite")
            key = (edge.source, edge.target)
            if key in edge_set:
                raise GraphError(f"duplicate edge: {edge.source}->{edge.target}")
            edge_set.add(key)

    def _validate_range(self, name: str, value: Decimal, low: Decimal, high: Decimal) -> None:
        if value < low or value > high:
            raise GraphError(f"{name} must be within [{low}, {high}]")

    def _clamp(self, value: Decimal) -> Decimal:
        if value < 0:
            return Decimal("0")
        if value > 1:
            return Decimal("1")
        return value
