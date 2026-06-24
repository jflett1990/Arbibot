from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from arbibot.core.events import (
    PolyBookDelta,
    PolyBookSnapshot,
    PolyTrade,
    SpotBar,
    SpotBookTicker,
    SpotTick,
)
from arbibot.market.book import BookError, LocalOrderBook
from arbibot.research.features import RollingImpulse, build_feature_row
from arbibot.research.gates import evaluate_gates
from arbibot.research.hypothesis import ResearchHypothesis, load_hypothesis
from arbibot.research.model_client import ResearchCritiqueInput, ResearchModelClient
from arbibot.research.qa import REQUIRED, evaluate_qa
from arbibot.storage.sqlite_store import SQLiteEventStore

REPLAY_RESULT_FIELDS = [
    "decision_time_ms",
    "market_id",
    "token_id",
    "binance_price",
    "polymarket_best_bid",
    "polymarket_best_ask",
    "spread",
    "spread_bps",
    "book_age_ms",
    "impulse_return_bps",
    "estimated_fair_price",
    "observed_price",
    "raw_edge_bps",
    "cost_adjusted_edge_bps",
    "liquidity_available",
    "latency_ms",
    "missing_binance_context",
    "missing_polymarket_context",
    "gate_result",
    "gate_reasons",
]


@dataclass(frozen=True, slots=True)
class ResearchRunOptions:
    hypothesis: Path
    store: Path
    out: Path = Path("research_runs")
    from_ts: str | None = None
    to_ts: str | None = None
    max_events: int | None = None
    latency_ms: int | None = None
    fee_bps: float | None = None
    slippage_bps: float | None = None
    min_liquidity: float | None = None
    skip_ai: bool = False
    debug: bool = False


@dataclass(slots=True)
class ReplayState:
    impulse: RollingImpulse
    latency_ms: int
    fee_bps: float
    slippage_bps: float
    threshold_bps: float
    gates_cfg: dict[str, Any]
    rows: list[dict[str, Any]]
    counts: Counter[str]
    failures: Counter[str]
    malformed_events: int = 0
    orphan_book_deltas: int = 0
    book_errors: int = 0
    book: LocalOrderBook | None = None
    market_id: str | None = None
    token_id: str | None = None
    latest_price: float | None = None


def _parse_iso(v: str | None) -> int | None:
    if not v:
        return None
    return int(datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() * 1000)


def _git() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _hash(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_research(options: ResearchRunOptions) -> Path:
    hyp, hyp_error = _load_hypothesis_for_run(options.hypothesis)
    out = options.out / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{hyp.id}"
    out.mkdir(parents=True, exist_ok=True)

    state = _new_replay_state(hyp, options)
    if options.store.exists() and hyp_error is None:
        _replay_store(options, state)

    _write_packet(out, hyp, options, state, hyp_error)
    return out


def rerun_research_critique(run_dir: Path) -> str:
    packet = _load_existing_packet(run_dir)
    edge_summary = (run_dir / "edge_summary.md").read_text(encoding="utf-8")
    qa_report = json.loads((run_dir / "qa_report.json").read_text(encoding="utf-8"))
    rows = _read_replay_rows(run_dir / "replay_results.csv")
    passing = [row for row in rows if row.get("gate_result") == "pass"][:5]
    failing = [row for row in rows if row.get("gate_result") != "pass"][:5]
    failures = Counter[str]()
    for row in rows:
        for reason in str(row.get("gate_reasons") or "").split(";"):
            if reason:
                failures[reason] += 1

    critique = ResearchModelClient().generate_research_critique(
        ResearchCritiqueInput(
            hypothesis=packet["hypothesis"],
            feature_spec=packet["feature_spec"],
            edge_summary=edge_summary,
            gate_failure_counts=dict(failures),
            passing_rows=passing,
            failing_rows=failing,
            qa_report=qa_report,
        )
    )
    (run_dir / "ai_critique.md").write_text(critique.text, encoding="utf-8")
    qa_report["ai_critique_status"] = critique.status
    (run_dir / "qa_report.json").write_text(json.dumps(qa_report, indent=2), encoding="utf-8")
    _refresh_manifest_outputs(run_dir)
    return critique.status


def _load_hypothesis_for_run(path: Path) -> tuple[ResearchHypothesis, str | None]:
    try:
        return load_hypothesis(path), None
    except ValidationError as exc:
        return (
            ResearchHypothesis.model_construct(
                id="invalid", name="invalid", kind="custom", description="invalid"
            ),
            str(exc),
        )


def _new_replay_state(hyp: ResearchHypothesis, options: ResearchRunOptions) -> ReplayState:
    latency_ms = int(
        options.latency_ms
        if options.latency_ms is not None
        else (hyp.cost_assumptions or {}).get("latency_ms", 250)
    )
    fee_bps = float(
        options.fee_bps
        if options.fee_bps is not None
        else (hyp.cost_assumptions or {}).get("fee_bps", 0.0)
    )
    slippage_bps = float(
        options.slippage_bps
        if options.slippage_bps is not None
        else (hyp.cost_assumptions or {}).get("slippage_bps", 0.0)
    )
    gates_cfg = dict(getattr(hyp, "risk_gates", {}) or {})
    if options.min_liquidity is not None:
        gates_cfg["min_liquidity"] = options.min_liquidity
    return ReplayState(
        impulse=RollingImpulse(int((hyp.entry_conditions or {}).get("impulse_window_ms", 30000))),
        latency_ms=latency_ms,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        threshold_bps=float((hyp.entry_conditions or {}).get("impulse_threshold_bps", 0.0)),
        gates_cfg=gates_cfg,
        rows=[],
        counts=Counter(),
        failures=Counter(),
    )


def _replay_store(options: ResearchRunOptions, state: ReplayState) -> None:
    store = SQLiteEventStore(options.store)
    try:
        for i, stored in enumerate(
            store.iter_events(_parse_iso(options.from_ts), _parse_iso(options.to_ts))
        ):
            if options.max_events is not None and i >= options.max_events:
                break
            state.counts[stored.event_type] += 1
            try:
                data = json.loads(stored.payload_json)
                _apply_stored_event(stored.event_type, data, state)
            except BookError:
                state.book_errors += 1
                if options.debug:
                    raise
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
                state.malformed_events += 1
                if options.debug:
                    raise
    finally:
        store.close()


def _apply_stored_event(event_type: str, data: dict[str, Any], state: ReplayState) -> None:
    if event_type == "SpotTick":
        ev = SpotTick.model_validate(data)
        _observe_binance_price(ev.source_ts_ms, ev.price, state)
    elif event_type == "SpotBookTicker":
        ev = SpotBookTicker.model_validate(data)
        _observe_binance_price(ev.source_ts_ms, (ev.bid_price + ev.ask_price) / 2.0, state)
    elif event_type == "SpotBar":
        ev = SpotBar.model_validate(data)
        _observe_binance_price(ev.end_ts_ms or ev.source_ts_ms, ev.close, state)
    elif event_type == "PolyBookSnapshot":
        ev = PolyBookSnapshot.model_validate(data)
        book = LocalOrderBook(ev.token_id or f"{ev.market_id}:{ev.outcome}")
        book.apply_snapshot(ev)
        state.book = book
        state.market_id = ev.market_id
        state.token_id = book.token_id
    elif event_type == "PolyBookDelta":
        ev = PolyBookDelta.model_validate(data)
        if state.book is None or (ev.token_id and ev.token_id != state.token_id):
            state.orphan_book_deltas += 1
            return
        state.book.apply_delta(ev)
    elif event_type == "PolyTrade":
        PolyTrade.model_validate(data)


def _observe_binance_price(ts_ms: int, price: float, state: ReplayState) -> None:
    state.latest_price = price
    impulse_bps = state.impulse.add(ts_ms, price)
    if abs(impulse_bps or 0.0) < state.threshold_bps:
        return
    state.rows.append(
        _row(
            ts_ms + state.latency_ms,
            state.market_id,
            state.token_id,
            state.latest_price,
            state.book,
            impulse_bps,
            state.latency_ms,
            state.fee_bps,
            state.slippage_bps,
            state.gates_cfg,
            state.failures,
        )
    )


def _row(
    decision_time_ms: int,
    market_id: str | None,
    token_id: str | None,
    price: float | None,
    book: LocalOrderBook | None,
    imp: float | None,
    latency_ms: int,
    fee_bps: float,
    slippage_bps: float,
    gates_cfg: dict[str, Any],
    failures: Counter[str],
) -> dict[str, Any]:
    bid = book.best_bid() if book else None
    ask = book.best_ask() if book else None
    feature_row = build_feature_row(
        decision_time_ms=decision_time_ms,
        market_id=market_id,
        token_id=token_id,
        binance_price=price,
        best_bid=float(bid.price) if bid else None,
        best_ask=float(ask.price) if ask else None,
        bid_size=float(bid.size) if bid else None,
        ask_size=float(ask.size) if ask else None,
        book_ts_ms=book.last_update_source_ts_ms if book else None,
        impulse_return_bps=imp,
        latency_ms=latency_ms,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )
    row = asdict(feature_row)
    gates = evaluate_gates(row, gates_cfg)
    failed_codes = [gate.reason_code.value for gate in gates if not gate.passed]
    for code in failed_codes:
        failures[code] += 1
    row["gate_result"] = "pass" if not failed_codes else "fail"
    row["gate_reasons"] = ";".join(failed_codes)
    return row


def _write_packet(
    out: Path,
    hyp: ResearchHypothesis,
    opt: ResearchRunOptions,
    state: ReplayState,
    hyp_error: str | None,
) -> None:
    feature_spec = {
        "impulse_window_ms": state.impulse.window_ms,
        "fee_bps": state.fee_bps,
        "slippage_bps": state.slippage_bps,
        "latency_ms": state.latency_ms,
        "gates": state.gates_cfg,
    }
    replay_config = {
        "store": str(opt.store),
        "from_ts": opt.from_ts,
        "to_ts": opt.to_ts,
        "max_events": opt.max_events,
        "supported_event_types": [
            "SpotTick",
            "SpotBookTicker",
            "SpotBar",
            "PolyBookSnapshot",
            "PolyBookDelta",
            "PolyTrade",
        ],
    }
    (out / "hypothesis.yaml").write_text(
        yaml.safe_dump(hyp.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    (out / "hypothesis.md").write_text(f"# {hyp.name}\n\n{hyp.description}\n", encoding="utf-8")
    (out / "feature_spec.json").write_text(json.dumps(feature_spec, indent=2), encoding="utf-8")
    (out / "replay_config.json").write_text(json.dumps(replay_config, indent=2), encoding="utf-8")
    _write_replay_results(out / "replay_results.csv", state.rows)

    passed = [row for row in state.rows if row.get("gate_result") == "pass"]
    decision = _promotion_decision(hyp, state.rows, passed)
    summary = _edge_summary(hyp, state, passed, decision)
    (out / "edge_summary.md").write_text(summary, encoding="utf-8")
    (out / "failure_modes.md").write_text(_failure_modes(state), encoding="utf-8")
    (out / "next_experiments.md").write_text(_next_experiments(state), encoding="utf-8")

    qa_preview = {
        "run_id": out.name,
        "hypothesis_id": hyp.id,
        "event_counts": dict(state.counts),
        "malformed_events": state.malformed_events,
        "orphan_book_deltas": state.orphan_book_deltas,
    }
    ai_status = _write_ai_critique(
        out, opt.skip_ai, hyp, feature_spec, summary, state, passed, qa_preview
    )
    _write_manifest(out, opt, feature_spec | replay_config)
    qa = evaluate_qa(
        run_id=out.name,
        hypothesis_id=hyp.id,
        store_path=opt.store,
        event_counts=dict(state.counts),
        replay_rows=len(state.rows),
        gate_results_present=bool(state.rows),
        edge_summary_present=True,
        output_dir=out,
        ai_status=ai_status,
        promotion_decision=decision,
    )
    qa["missing_data_counts"] = {
        "malformed_events": state.malformed_events,
        "orphan_book_deltas": state.orphan_book_deltas,
        "book_errors": state.book_errors,
    }
    if hyp_error:
        qa["blocked_reasons"].append("hypothesis_schema_invalid")
        qa["hypothesis_validation_error"] = hyp_error
        qa["deterministic_pass"] = False
    (out / "qa_report.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
    _refresh_manifest_outputs(out)


def _write_replay_results(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0].keys()) if rows else REPLAY_RESULT_FIELDS
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _promotion_decision(
    hyp: ResearchHypothesis, rows: list[dict[str, Any]], passed: list[dict[str, Any]]
) -> str:
    min_passing = int((hyp.promotion_criteria or {}).get("min_passing_rows", 10))
    min_median_edge = float(
        (hyp.promotion_criteria or {}).get("min_median_cost_adjusted_edge_bps", 0)
    )
    edges = sorted(
        float(row["cost_adjusted_edge_bps"])
        for row in passed
        if row.get("cost_adjusted_edge_bps") is not None
    )
    median_edge = edges[len(edges) // 2] if edges else None
    if len(passed) >= min_passing and median_edge is not None and median_edge >= min_median_edge:
        return "promote_to_more_replay"
    if not rows or not passed:
        return "reject"
    return "revise"


def _edge_summary(
    hyp: ResearchHypothesis, state: ReplayState, passed: list[dict[str, Any]], decision: str
) -> str:
    raw_edges = _distribution([row.get("raw_edge_bps") for row in state.rows])
    net_edges = _distribution([row.get("cost_adjusted_edge_bps") for row in state.rows])
    best = _representative_rows(state.rows, reverse=True)
    worst = _representative_rows(state.rows, reverse=False)
    return (
        f"# Edge Summary\n\nHypothesis: {hyp.description}\n\n"
        f"Dataset window: replayed persisted events in configured timestamp bounds.\n\n"
        f"Event counts by source/type: {dict(state.counts)}\n\n"
        f"Candidate signals: {len(state.rows)}\n\n"
        f"Passing gates: {len(passed)}\n\n"
        f"Raw edge distribution: {raw_edges}\n\n"
        f"Cost-adjusted edge distribution: {net_edges}\n\n"
        f"Best examples: {best}\n\n"
        f"Worst examples: {worst}\n\n"
        f"Failure reasons ranked by frequency: {state.failures.most_common()}\n\n"
        f"Promotion criteria met: {decision == 'promote_to_more_replay'}\n\n"
        f"Decision: `{decision}`\n"
    )


def _distribution(values: list[Any]) -> dict[str, float | int | None]:
    nums = sorted(float(value) for value in values if value is not None and value != "")
    if not nums:
        return {"count": 0, "min": None, "median": None, "max": None}
    return {"count": len(nums), "min": nums[0], "median": nums[len(nums) // 2], "max": nums[-1]}


def _representative_rows(rows: list[dict[str, Any]], *, reverse: bool) -> list[dict[str, Any]]:
    ranked = sorted(
        (row for row in rows if row.get("cost_adjusted_edge_bps") is not None),
        key=lambda row: float(row["cost_adjusted_edge_bps"]),
        reverse=reverse,
    )
    return [
        {
            "decision_time_ms": row.get("decision_time_ms"),
            "market_id": row.get("market_id"),
            "token_id": row.get("token_id"),
            "cost_adjusted_edge_bps": row.get("cost_adjusted_edge_bps"),
            "gate_result": row.get("gate_result"),
            "gate_reasons": row.get("gate_reasons"),
        }
        for row in ranked[:3]
    ]


def _failure_modes(state: ReplayState) -> str:
    observed = "\n".join(f"- {code}: {count}" for code, count in state.failures.most_common())
    if not observed:
        observed = "- no gate failures observed in generated candidate rows"
    return (
        "# Failure Modes\n\n"
        "## Observed gate failures\n\n"
        f"{observed}\n\n"
        "## Standard replay risks to inspect\n\n"
        "- insufficient sample size\n"
        "- stale Polymarket book\n"
        "- wide spread\n"
        "- missing side of book\n"
        "- edge erased by costs\n"
        "- signal arrives too late\n"
        "- liquidity unavailable\n"
        "- candidate frequency too low\n"
        "- likely overfit threshold\n"
        "- replay data incomplete\n"
    )


def _next_experiments(state: ReplayState) -> str:
    frequency = "low candidate frequency" if len(state.rows) < 10 else "candidate frequency present"
    return (
        "# Next Experiments\n\n"
        f"Current deterministic assessment: {frequency}.\n\n"
        "1. Replay a larger contiguous data window with the same parameters.\n"
        "2. Stress latency, fees, slippage, queue risk, and minimum liquidity.\n"
        "3. Add negative-control windows without Binance impulses.\n"
    )


def _write_ai_critique(
    out: Path,
    skip_ai: bool,
    hyp: ResearchHypothesis,
    feature_spec: dict[str, Any],
    summary: str,
    state: ReplayState,
    passed: list[dict[str, Any]],
    qa_preview: dict[str, Any],
) -> str:
    if skip_ai:
        (out / "ai_critique.md").write_text("AI critique skipped by --skip-ai.\n", encoding="utf-8")
        return "skipped_by_flag"
    critique = ResearchModelClient().generate_research_critique(
        ResearchCritiqueInput(
            hypothesis=hyp.model_dump(mode="json"),
            feature_spec=feature_spec,
            edge_summary=summary,
            gate_failure_counts=dict(state.failures),
            passing_rows=passed[:5],
            failing_rows=[row for row in state.rows if row.get("gate_result") != "pass"][:5],
            qa_report=qa_preview,
        )
    )
    (out / "ai_critique.md").write_text(critique.text, encoding="utf-8")
    return critique.status


def _write_manifest(out: Path, opt: ResearchRunOptions, config: dict[str, Any]) -> None:
    manifest = {
        "run_id": out.name,
        "created_timestamp": out.name.split("_")[0],
        "git_commit_hash": _git(),
        "hypothesis_file_path": str(opt.hypothesis),
        "output_files": REQUIRED,
        "config": config,
        "model_provider_config": ResearchModelClient().config.redacted(),
        "source_store_sha256": _hash(opt.store),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _refresh_manifest_outputs(run_dir: Path) -> None:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["output_files"] = sorted(path.name for path in run_dir.iterdir() if path.is_file())
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _load_existing_packet(run_dir: Path) -> dict[str, Any]:
    required = ["hypothesis.yaml", "feature_spec.json", "edge_summary.md", "qa_report.json"]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"research packet is missing required files: {', '.join(missing)}")
    return {
        "hypothesis": yaml.safe_load((run_dir / "hypothesis.yaml").read_text(encoding="utf-8")),
        "feature_spec": json.loads((run_dir / "feature_spec.json").read_text(encoding="utf-8")),
    }


def _read_replay_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def event_store_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    try:
        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                "SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY event_type"
            ).fetchall()
    except sqlite3.Error as exc:
        return {"exists": True, "error": str(exc)}
    return {"exists": True, "event_counts": dict(rows)}
