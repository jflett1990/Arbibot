from decimal import Decimal

import pytest

from arbibot.core.events import SignalDirection
from arbibot.model.graph import (
    GraphDefinition,
    GraphEdge,
    GraphError,
    GraphFusionModel,
    GraphInput,
    GraphNode,
)


def _run(nodes: list[GraphNode], edges: list[GraphEdge] | None = None):
    model = GraphFusionModel()
    return model.run(GraphInput(GraphDefinition(nodes=nodes, edges=edges or [])))


def test_empty_graph_neutral_zero() -> None:
    r = _run([])
    assert r.direction is SignalDirection.NEUTRAL
    assert r.bull_score == 0
    assert r.bear_score == 0


def test_validation_errors() -> None:
    with pytest.raises(GraphError):
        _run([GraphNode("x", "g", SignalDirection.BULL), GraphNode("x", "g", SignalDirection.BEAR)])
    with pytest.raises(GraphError):
        _run([GraphNode("a", "g", SignalDirection.BULL)], [GraphEdge("z", "a", Decimal("1"))])
    with pytest.raises(GraphError):
        _run([GraphNode("a", "g", SignalDirection.BULL)], [GraphEdge("a", "z", Decimal("1"))])
    with pytest.raises(GraphError):
        _run([GraphNode("a", "g", SignalDirection.BULL, value=Decimal("2"))])
    with pytest.raises(GraphError):
        _run([GraphNode("a", "g", SignalDirection.BULL, confidence=Decimal("2"))])
    with pytest.raises(GraphError):
        _run([GraphNode("a", "g", SignalDirection.BULL, freshness=Decimal("2"))])
    with pytest.raises(GraphError):
        _run(
            [GraphNode("a", "g", SignalDirection.BULL)],
            [GraphEdge("a", "a", Decimal("NaN"))],
        )


def test_message_passing_and_direction_logic() -> None:
    bull = GraphNode("b", "g", SignalDirection.BULL, value=Decimal("0.5"))
    bear = GraphNode("s", "g", SignalDirection.BEAR, value=Decimal("0.2"))
    r = _run([bull, bear])
    assert r.direction is SignalDirection.BULL

    r2 = _run([GraphNode("s", "g", SignalDirection.BEAR, value=Decimal("0.8"))])
    assert r2.direction is SignalDirection.BEAR

    equal = _run([
        GraphNode("b", "g", SignalDirection.BULL, value=Decimal("0.5")),
        GraphNode("s", "g", SignalDirection.BEAR, value=Decimal("0.5")),
    ])
    assert equal.direction is SignalDirection.NEUTRAL
    assert equal.conflict == 1

    stale = _run([
        GraphNode(
            "b",
            "g",
            SignalDirection.BULL,
            value=Decimal("1"),
            freshness=Decimal("0.2"),
        )
    ])
    assert stale.bull_score == Decimal("0.2")

    msg = _run(
        [
            GraphNode("src", "g", SignalDirection.NEUTRAL, value=Decimal("1")),
            GraphNode("tgt", "g", SignalDirection.BULL, value=Decimal("0")),
        ],
        [GraphEdge("src", "tgt", Decimal("0.5"))],
    )
    assert msg.node_scores["tgt"] == Decimal("0.5")
    assert msg.bull_score == Decimal("0.5")
