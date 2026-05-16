from __future__ import annotations

from arbibot.apps.commands.replay import run_replay


def run_paper(
    store_path: str,
    threshold_price: str | None,
    seconds_to_expiry: str | None,
    target_size: str,
    outcome_side: str | None,
    as_json: bool,
) -> int:
    if threshold_price is None or seconds_to_expiry is None or outcome_side is None:
        print("paper requires threshold-price, seconds-to-expiry, outcome-side")
        return 1
    return run_replay(
        store_path=store_path,
        evaluate_opportunities=True,
        paper_execute=True,
        threshold_price=threshold_price,
        seconds_to_expiry=seconds_to_expiry,
        target_size=target_size,
        outcome_side=outcome_side,
        as_json=as_json,
    )
