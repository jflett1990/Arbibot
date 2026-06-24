from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from arbibot.core.events import PolyBookSnapshot, SpotTick
from arbibot.market.book import LocalOrderBook
from arbibot.research.features import RollingImpulse, build_feature_row
from arbibot.research.gates import evaluate_gates
from arbibot.research.hypothesis import ResearchHypothesis, load_hypothesis
from arbibot.research.model_client import ResearchCritiqueInput, ResearchModelClient
from arbibot.research.qa import evaluate_qa
from arbibot.storage.sqlite_store import SQLiteEventStore


def _parse_iso(v: str | None) -> int | None:
    if not v:
        return None
    return int(datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp() * 1000)


def _git() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def _hash(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


class ResearchRunOptions:
    def __init__(
        self,
        hypothesis: Path,
        store: Path,
        out: Path = Path("research_runs"),
        from_ts: str | None = None,
        to_ts: str | None = None,
        max_events: int | None = None,
        latency_ms: int | None = None,
        fee_bps: float | None = None,
        slippage_bps: float | None = None,
        min_liquidity: float | None = None,
        skip_ai: bool = False,
        debug: bool = False,
    ) -> None:
        self.hypothesis = hypothesis
        self.store = store
        self.out = out
        self.from_ts = from_ts
        self.to_ts = to_ts
        self.max_events = max_events
        self.latency_ms = latency_ms
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.min_liquidity = min_liquidity
        self.skip_ai = skip_ai
        self.debug = debug


def run_research(options: ResearchRunOptions) -> Path:
    try:
        hyp = load_hypothesis(options.hypothesis)
        hyp_error = None
    except ValidationError as exc:
        hyp = ResearchHypothesis.model_construct(
            id="invalid", name="invalid", kind="custom", description="invalid"
        )
        hyp_error = str(exc)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{ts}_{hyp.id}"
    out = options.out / run_id
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    gates_cfg = dict(getattr(hyp, "risk_gates", {}) or {})
    if options.min_liquidity is not None:
        gates_cfg["min_liquidity"] = options.min_liquidity
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
    window = (
        int((hyp.entry_conditions or {}).get("impulse_window_ms", 30000))
        if hyp_error is None
        else 30000
    )
    threshold = (
        float((hyp.entry_conditions or {}).get("impulse_threshold_bps", 0.0))
        if hyp_error is None
        else 0.0
    )
    impulse = RollingImpulse(window)
    book: LocalOrderBook | None = None
    market_id = None
    token_id = None
    latest_price = None
    if options.store.exists() and hyp_error is None:
        store = SQLiteEventStore(options.store)
        for i, stored in enumerate(
            store.iter_events(_parse_iso(options.from_ts), _parse_iso(options.to_ts))
        ):
            if options.max_events is not None and i >= options.max_events:
                break
            counts[stored.event_type] += 1
            data = json.loads(stored.payload_json)
            if stored.event_type == "SpotTick":
                ev = SpotTick.model_validate(data)
                latest_price = ev.price
                imp = impulse.add(ev.source_ts_ms, ev.price)
                if abs(imp or 0.0) >= threshold:
                    rows.append(
                        _row(
                            ev.source_ts_ms + latency_ms,
                            market_id,
                            token_id,
                            latest_price,
                            book,
                            imp,
                            latency_ms,
                            fee_bps,
                            slippage_bps,
                            gates_cfg,
                            failures,
                        )
                    )
            elif stored.event_type == "PolyBookSnapshot":
                ev = PolyBookSnapshot.model_validate(data)
                book = LocalOrderBook(ev.token_id or "unknown")
                book.apply_snapshot(ev)
                market_id = ev.market_id
                token_id = book.token_id
        store.close()
    _write_packet(
        out,
        hyp,
        options,
        rows,
        counts,
        failures,
        gates_cfg,
        latency_ms,
        fee_bps,
        slippage_bps,
        hyp_error,
    )
    return out


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
    r = build_feature_row(
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
    d = asdict(r)
    gates = evaluate_gates(d, gates_cfg)
    bad = [g.reason_code.value for g in gates if not g.passed]
    for b in bad:
        failures[b] += 1
    d["gate_result"] = "pass" if not bad else "fail"
    d["gate_reasons"] = ";".join(bad)
    return d


def _write_packet(
    out: Path,
    hyp: ResearchHypothesis,
    opt: ResearchRunOptions,
    rows: list[dict[str, Any]],
    counts: Counter[str],
    failures: Counter[str],
    gates_cfg: dict[str, Any],
    latency_ms: int,
    fee_bps: float,
    slippage_bps: float,
    hyp_error: str | None,
) -> None:
    (out / "hypothesis.yaml").write_text(
        __import__("yaml").safe_dump(hyp.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
    )
    (out / "hypothesis.md").write_text(f"# {hyp.name}\n\n{hyp.description}\n", encoding="utf-8")
    feature_spec = {
        "impulse_window_ms": (hyp.entry_conditions or {}).get("impulse_window_ms", 30000),
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "latency_ms": latency_ms,
        "gates": gates_cfg,
    }
    (out / "feature_spec.json").write_text(json.dumps(feature_spec, indent=2), encoding="utf-8")
    replay_config = {
        "store": str(opt.store),
        "from_ts": opt.from_ts,
        "to_ts": opt.to_ts,
        "max_events": opt.max_events,
    }
    (out / "replay_config.json").write_text(json.dumps(replay_config, indent=2), encoding="utf-8")
    fields = (
        list(rows[0].keys())
        if rows
        else [
            "decision_time_ms",
            "market_id",
            "token_id",
            "binance_price",
            "polymarket_best_bid",
            "polymarket_best_ask",
            "spread",
            "book_age_ms",
            "impulse_return_bps",
            "estimated_fair_price",
            "observed_price",
            "raw_edge_bps",
            "cost_adjusted_edge_bps",
            "liquidity_available",
            "gate_result",
            "gate_reasons",
        ]
    )
    with (out / "replay_results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    passed = [r for r in rows if r.get("gate_result") == "pass"]
    edges = [
        r["cost_adjusted_edge_bps"] for r in rows if r.get("cost_adjusted_edge_bps") is not None
    ]
    decision = (
        "promote_to_more_replay"
        if len(passed) >= int((hyp.promotion_criteria or {}).get("min_passing_rows", 10))
        else ("reject" if not passed else "revise")
    )
    summary = (
        f"# Edge Summary\n\nHypothesis: {hyp.description}\n\n"
        f"Event counts: {dict(counts)}\n\n"
        f"Candidate signals: {len(rows)}\n\n"
        f"Passing gates: {len(passed)}\n\n"
        f"Cost-adjusted edge count: {len(edges)}\n\n"
        f"Failure reasons: {dict(failures)}\n\n"
        f"Promotion criteria met: {decision == 'promote_to_more_replay'}\n\n"
        f"Decision: `{decision}`\n"
    )
    (out / "edge_summary.md").write_text(summary, encoding="utf-8")
    (out / "failure_modes.md").write_text(
        (
            "# Failure Modes\n\n"
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
        ),
        encoding="utf-8",
    )
    (out / "next_experiments.md").write_text(
        (
            "# Next Experiments\n\n"
            "1. Replay a larger contiguous data window.\n"
            "2. Stress latency, fees, slippage, queue risk, and minimum liquidity.\n"
            "3. Add negative-control windows without Binance impulses.\n"
        ),
        encoding="utf-8",
    )
    ai_status = "skipped_by_flag" if opt.skip_ai else "pending"
    if not opt.skip_ai:
        crit = ResearchModelClient().generate_research_critique(
            ResearchCritiqueInput(
                hypothesis=hyp.model_dump(mode="json"),
                feature_spec=feature_spec,
                edge_summary=summary,
                gate_failure_counts=dict(failures),
                passing_rows=passed[:5],
                failing_rows=[r for r in rows if r.get("gate_result") != "pass"][:5],
                qa_report={},
            )
        )
        ai_status = crit.status
        (out / "ai_critique.md").write_text(crit.text, encoding="utf-8")
    else:
        (out / "ai_critique.md").write_text("AI critique skipped by --skip-ai.\n", encoding="utf-8")
    qa = evaluate_qa(
        run_id=out.name,
        hypothesis_id=hyp.id,
        store_path=opt.store,
        event_counts=dict(counts),
        replay_rows=len(rows),
        gate_results_present=bool(rows),
        edge_summary_present=True,
        output_dir=out,
        ai_status=ai_status,
        promotion_decision=decision,
    )
    if hyp_error:
        qa["blocked_reasons"].append("hypothesis_schema_invalid")
        qa["deterministic_pass"] = False
    (out / "qa_report.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")
    manifest = {
        "run_id": out.name,
        "created_timestamp": out.name.split("_")[0],
        "git_commit_hash": _git(),
        "hypothesis_file_path": str(opt.hypothesis),
        "output_files": sorted(p.name for p in out.iterdir()),
        "config": feature_spec | replay_config,
        "model_provider_config": ResearchModelClient().config.redacted(),
        "source_store_sha256": _hash(opt.store),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
