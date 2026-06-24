from __future__ import annotations

import json
from pathlib import Path

from arbibot.research.hypothesis import HypothesisKind, write_hypothesis_template
from arbibot.research.runner import ResearchRunOptions, run_research


def run_research_init(name: str, out: str, kind: str) -> int:
    path = write_hypothesis_template(name, out, HypothesisKind(kind))
    print(path)
    return 0


def run_research_run(**kwargs: object) -> int:
    path = run_research(ResearchRunOptions(**kwargs))  # type: ignore[arg-type]
    print(path)
    return 0


def run_research_list(out: str) -> int:
    base = Path(out)
    rows = []
    for d in sorted(base.glob("*")):
        qa = d / "qa_report.json"
        if d.is_dir() and qa.exists():
            data = json.loads(qa.read_text(encoding="utf-8"))
            rows.append(
                f"{d.name}\t{data.get('hypothesis_id')}\t{data.get('deterministic_pass')}\t{data.get('promotion_decision')}"
            )
    print("\n".join(rows))
    return 0


def run_research_inspect(run: str) -> int:
    d = Path(run)
    for name in ["edge_summary.md", "qa_report.json"]:
        p = d / name
        if p.exists():
            print(p.read_text(encoding="utf-8"))
    return 0


def run_research_critique(run: str) -> int:
    # Deterministic critique is always present; AI rerun is intentionally conservative here.
    d = Path(run)
    if not d.exists():
        print(f"research run not found: {d}")
        return 1
    print(d / "ai_critique.md")
    return 0
