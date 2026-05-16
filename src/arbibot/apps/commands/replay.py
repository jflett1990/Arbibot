from __future__ import annotations

import json
from dataclasses import asdict
from decimal import Decimal

from arbibot.opportunity.edge import OutcomeSide
from arbibot.replay.engine import ReplayConfig, ReplayEngine
from arbibot.storage.sqlite_store import SQLiteEventStore


def run_replay(
    store_path: str,
    evaluate_opportunities: bool,
    paper_execute: bool,
    threshold_price: str | None,
    seconds_to_expiry: str | None,
    target_size: str,
    outcome_side: str | None,
    as_json: bool,
) -> int:
    if paper_execute and not evaluate_opportunities:
        print("paper-execute requires --evaluate-opportunities")
        return 1
    if evaluate_opportunities and (
        threshold_price is None or seconds_to_expiry is None or outcome_side is None
    ):
        print("evaluate-opportunities requires threshold-price, seconds-to-expiry, outcome-side")
        return 1

    try:
        cfg = ReplayConfig(
            evaluate_opportunities=evaluate_opportunities,
            paper_execute=paper_execute,
            threshold_price=None if threshold_price is None else Decimal(threshold_price),
            seconds_to_expiry=None if seconds_to_expiry is None else Decimal(seconds_to_expiry),
            target_size=Decimal(target_size),
            outcome_side=None if outcome_side is None else OutcomeSide[outcome_side],
        )
        store = SQLiteEventStore(store_path)
    except Exception as exc:  # noqa: BLE001
        print(f"Replay setup failed: {exc}")
        return 1

    try:
        result = ReplayEngine(store, cfg).run()
    except Exception as exc:  # noqa: BLE001
        print(f"Replay runtime failed: {exc}")
        return 2
    finally:
        store.close()

    summary = asdict(result.summary)
    if as_json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(f"Replay completed total_events={result.summary.total_events}")
    return 0
