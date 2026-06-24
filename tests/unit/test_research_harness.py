import json
from pathlib import Path

import pytest

from arbibot.apps.cli import main
from arbibot.core.events import PolyBookSnapshot, SpotTick
from arbibot.research.features import RollingImpulse, build_feature_row
from arbibot.research.gates import GateCode, evaluate_gates
from arbibot.research.hypothesis import HypothesisKind, load_hypothesis, write_hypothesis_template
from arbibot.research.model_client import (
    ModelClientConfig,
    ResearchCritiqueInput,
    ResearchModelClient,
)
from arbibot.research.qa import evaluate_qa
from arbibot.storage.sqlite_store import SQLiteEventStore


def _store(path: Path) -> None:
    s = SQLiteEventStore(path)
    base = 1_700_000_000_000
    s.append(
        PolyBookSnapshot(
            event_id="b1",
            source="polymarket",
            source_ts_ms=base,
            recv_wall_ts_ms=base,
            recv_monotonic_ns=1,
            market_id="m",
            outcome="UP",
            token_id="t",
            bids=[[0.50, 10]],
            asks=[[0.51, 10]],
        )
    )
    s.append(
        SpotTick(
            event_id="s1",
            source="binance",
            source_ts_ms=base + 1000,
            recv_wall_ts_ms=base + 1000,
            recv_monotonic_ns=2,
            symbol="BTCUSDT",
            price=100.0,
        )
    )
    s.append(
        SpotTick(
            event_id="s2",
            source="binance",
            source_ts_ms=base + 31_000,
            recv_wall_ts_ms=base + 31_000,
            recv_monotonic_ns=3,
            symbol="BTCUSDT",
            price=101.0,
        )
    )
    s.close()


def test_hypothesis_yaml_validates(tmp_path):
    p = write_hypothesis_template("impulse lag test", tmp_path, HypothesisKind.IMPULSE_LAG)
    assert load_hypothesis(p).id == "impulse_lag_test"


def test_invalid_hypothesis_fails_loudly(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("id: x\n", encoding="utf-8")
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        load_hypothesis(p)


def test_research_init_cli(tmp_path, capsys):
    assert main(["research", "init", "--name", "abc", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "abc.yaml").exists()


def test_feature_calculations_and_costs():
    imp = RollingImpulse(30_000)
    assert imp.add(1000, 100.0) is None
    assert round(imp.add(31_000, 101.0) or 0, 2) == 100.0
    row = build_feature_row(
        decision_time_ms=2000,
        market_id="m",
        token_id="t",
        binance_price=1,
        best_bid=0.50,
        best_ask=0.51,
        bid_size=2,
        ask_size=3,
        book_ts_ms=1000,
        impulse_return_bps=100,
        latency_ms=10,
        fee_bps=2,
        slippage_bps=3,
    )
    assert row.cost_adjusted_edge_bps == pytest.approx(row.raw_edge_bps - 5)


def test_gates_structured_and_stale():
    row = {
        "spread_bps": 10,
        "liquidity_available": 1,
        "book_age_ms": 2000,
        "raw_edge_bps": 5,
        "cost_adjusted_edge_bps": 4,
        "latency_ms": 1,
        "polymarket_best_bid": 0.5,
        "polymarket_best_ask": 0.51,
        "binance_price": 1,
    }
    results = evaluate_gates(row, {"max_book_age_ms": 1000})
    stale = [r for r in results if r.reason_code is GateCode.MAX_BOOK_AGE_MS][0]
    assert not stale.passed and stale.measured_value == 2000


def test_qa_missing_and_valid(tmp_path):
    missing = evaluate_qa(
        run_id="r",
        hypothesis_id="h",
        store_path=tmp_path / "no.db",
        event_counts={},
        replay_rows=0,
        gate_results_present=False,
        edge_summary_present=False,
        output_dir=tmp_path,
        ai_status="skipped",
        promotion_decision="reject",
    )
    assert not missing["deterministic_pass"]
    (tmp_path / "x.db").write_text("x")
    valid = evaluate_qa(
        run_id="r",
        hypothesis_id="h",
        store_path=tmp_path / "x.db",
        event_counts={"SpotTick": 1},
        replay_rows=1,
        gate_results_present=True,
        edge_summary_present=True,
        output_dir=tmp_path,
        ai_status="skipped_missing_model_config",
        promotion_decision="revise",
    )
    assert valid["replay_status"] == "passed"


def test_model_client_skips_and_redacts(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ARBIBOT_RESEARCH_MODEL", raising=False)
    c = ResearchModelClient(ModelClientConfig.from_env())
    out = c.generate_research_critique(
        ResearchCritiqueInput(
            hypothesis={},
            feature_spec={},
            edge_summary="",
            gate_failure_counts={},
            passing_rows=[],
            failing_rows=[],
            qa_report={},
        )
    )
    assert out.status == "skipped_missing_model_config"
    assert (
        "api_key" not in json.dumps(c.config.redacted()).lower()
        or "api_key_configured" in c.config.redacted()
    )


def test_deterministic_research_run_cli(tmp_path, capsys):
    hyp = write_hypothesis_template("impulse lag test", tmp_path, HypothesisKind.IMPULSE_LAG)
    db = tmp_path / "events.sqlite3"
    _store(db)
    rc = main(
        [
            "research",
            "run",
            "--hypothesis",
            str(hyp),
            "--store",
            str(db),
            "--out",
            str(tmp_path / "runs"),
            "--skip-ai",
        ]
    )
    assert rc == 0
    out = Path(capsys.readouterr().out.strip())
    assert (out / "manifest.json").exists()
    qa = json.loads((out / "qa_report.json").read_text())
    assert qa["replay_status"] == "passed"
