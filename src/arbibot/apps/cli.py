from __future__ import annotations

import argparse

from arbibot.apps.commands import (
    run_paper,
    run_record_binance,
    run_replay,
    run_status,
    run_validate_config,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="arbibot")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate-config")
    v.add_argument("--config", required=True)
    v.add_argument("--json", action="store_true")

    s = sub.add_parser("status")
    s.add_argument("--config", required=True)
    s.add_argument("--json", action="store_true")

    r = sub.add_parser("replay")
    r.add_argument("--store", required=True)
    r.add_argument("--config")
    r.add_argument("--evaluate-opportunities", action="store_true")
    r.add_argument("--paper-execute", action="store_true")
    r.add_argument("--threshold-price")
    r.add_argument("--seconds-to-expiry")
    r.add_argument("--target-size", default="1")
    r.add_argument("--outcome-side", choices=["UP", "DOWN"])
    r.add_argument("--json", action="store_true")

    pa = sub.add_parser("paper")
    pa.add_argument("--store", required=True)
    pa.add_argument("--config")
    pa.add_argument("--threshold-price", required=False)
    pa.add_argument("--seconds-to-expiry", required=False)
    pa.add_argument("--target-size", default="1")
    pa.add_argument("--outcome-side", choices=["UP", "DOWN"], required=False)
    pa.add_argument("--json", action="store_true")

    rb = sub.add_parser("record-binance")
    rb.add_argument("--store", default="data/events.sqlite3")
    rb.add_argument("--symbol", default="BTCUSDT")
    rb.add_argument("--streams", default="aggTrade,trade")
    rb.add_argument("--duration-seconds", type=int)
    rb.add_argument("--max-events", type=int)
    rb.add_argument("--config")
    rb.add_argument("--json", action="store_true")
    rb.add_argument("--dry-run", action="store_true")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate-config":
        return run_validate_config(args.config, args.json)
    if args.command == "status":
        return run_status(args.config, args.json)
    if args.command == "replay":
        return run_replay(
            store_path=args.store,
            evaluate_opportunities=args.evaluate_opportunities,
            paper_execute=args.paper_execute,
            threshold_price=args.threshold_price,
            seconds_to_expiry=args.seconds_to_expiry,
            target_size=args.target_size,
            outcome_side=args.outcome_side,
            as_json=args.json,
        )
    if args.command == "paper":
        return run_paper(
            store_path=args.store,
            threshold_price=args.threshold_price,
            seconds_to_expiry=args.seconds_to_expiry,
            target_size=args.target_size,
            outcome_side=args.outcome_side,
            as_json=args.json,
        )
    if args.command == "record-binance":
        return run_record_binance(
            store_path=args.store,
            symbol=args.symbol,
            streams_csv=args.streams,
            duration_seconds=args.duration_seconds,
            max_events=args.max_events,
            as_json=args.json,
            dry_run=args.dry_run,
            config_path=args.config,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
