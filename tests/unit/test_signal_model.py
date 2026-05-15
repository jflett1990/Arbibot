from arbibot.core.events import FeatureSnapshot, SignalDirection
from arbibot.model.graph import GraphFusionModel, GraphInput
from arbibot.model.signal import (
    build_default_graph_from_snapshot,
    graph_nodes_from_feature_snapshot,
    signal_state_from_graph_result,
)


def _snapshot(**updates: object) -> FeatureSnapshot:
    base: dict[str, object] = {
        "event_id": "f1",
        "source": "x",
        "source_ts_ms": 1,
        "recv_wall_ts_ms": 2,
        "recv_monotonic_ns": 3,
        "feature_set": "phase6",
        "values": {},
    }
    base.update(updates)
    return FeatureSnapshot.model_validate(base)


def test_feature_mapping_and_default_graph_deterministic() -> None:
    s = _snapshot(return_1s=0.1, return_5s=0.2, acceleration_1s_2s=0.05, book_imbalance_3=0.3)
    nodes = graph_nodes_from_feature_snapshot(s)
    node_map = {n.name: n for n in nodes}
    assert node_map["return_1s"].value > 0
    assert node_map["book_imbalance_3"].value > 0

    s2 = _snapshot(return_1s=-0.1, return_5s=-0.2, acceleration_1s_2s=-0.05, book_imbalance_3=-0.3)
    nodes2 = graph_nodes_from_feature_snapshot(s2)
    node_map2 = {n.name: n for n in nodes2}
    assert node_map2["return_1s"].value < 0
    assert node_map2["book_imbalance_3"].value < 0

    stale = _snapshot(stale_spot=True, stale_book=True)
    stale_nodes = {n.name: n for n in graph_nodes_from_feature_snapshot(stale)}
    assert stale_nodes["stale_spot"].value < 0
    assert stale_nodes["stale_book"].value < 0

    g1 = build_default_graph_from_snapshot(_snapshot())
    g2 = build_default_graph_from_snapshot(_snapshot())
    assert g1 == g2


def test_graph_result_and_signal_state_conversion() -> None:
    s = _snapshot(return_1s=0.3, return_5s=0.2)
    graph = build_default_graph_from_snapshot(s)
    result = GraphFusionModel().run(GraphInput(graph))
    assert result.direction in {
        SignalDirection.BULL,
        SignalDirection.BEAR,
        SignalDirection.NEUTRAL,
    }

    signal = signal_state_from_graph_result(
        result,
        event_id="sig:1",
        source_ts_ms=10,
        recv_wall_ts_ms=11,
        recv_monotonic_ns=12,
    )
    assert signal.event_id == "sig:1"
    assert signal.conflict == float(result.conflict)
    assert signal.convergence == float(result.convergence)
    assert signal.bull_score == float(result.bull_score)
