from __future__ import annotations

from pathlib import Path
from typing import Any

REQUIRED = [
    "hypothesis.md",
    "hypothesis.yaml",
    "feature_spec.json",
    "replay_config.json",
    "replay_results.csv",
    "edge_summary.md",
    "failure_modes.md",
    "ai_critique.md",
    "next_experiments.md",
    "qa_report.json",
    "manifest.json",
]


def evaluate_qa(
    *,
    run_id: str,
    hypothesis_id: str,
    store_path: Path,
    event_counts: dict[str, int],
    replay_rows: int,
    gate_results_present: bool,
    edge_summary_present: bool,
    output_dir: Path,
    ai_status: str,
    promotion_decision: str,
) -> dict[str, Any]:
    blocked: list[str] = []
    if not store_path.exists():
        blocked.append("no_source_store")
    if sum(event_counts.values()) == 0:
        blocked.append("no_relevant_events")
    if replay_rows == 0:
        blocked.append("no_replay_rows")
    if not gate_results_present:
        blocked.append("gate_results_missing")
    if not edge_summary_present:
        blocked.append("edge_summary_missing")
    missing = [f for f in REQUIRED if not (output_dir / f).exists() and f != "qa_report.json"]
    if missing:
        blocked.append("required_output_files_missing:" + ",".join(missing))
    return {
        "run_id": run_id,
        "hypothesis_id": hypothesis_id,
        "source_store_path": str(store_path),
        "event_counts": event_counts,
        "missing_data_counts": {},
        "replay_status": "passed" if replay_rows else "failed",
        "feature_status": "passed" if replay_rows else "failed",
        "gate_status": "passed" if gate_results_present else "failed",
        "ai_critique_status": ai_status,
        "output_file_status": "passed" if not missing else "failed",
        "deterministic_pass": not blocked,
        "promotion_decision": promotion_decision,
        "blocked_reasons": blocked,
    }
