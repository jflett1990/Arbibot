from __future__ import annotations

import argparse
from pathlib import Path

from arbibot.apps.commands import (
    run_paper,
    run_record_binance,
    run_replay,
    run_research_critique,
    run_research_init,
    run_research_inspect,
    run_research_list,
    run_research_run,
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

    research = sub.add_parser("research")
    rsub = research.add_subparsers(dest="research_command", required=True)
    ri = rsub.add_parser("init")
    ri.add_argument("--name", required=True)
    ri.add_argument("--out", default="research/hypotheses")
    ri.add_argument(
        "--kind",
        default="impulse_lag",
        choices=[
            "impulse_lag",
            "order_book_dislocation",
            "spread_compression",
            "external_signal_confirmation",
            "custom",
        ],
    )
    rr = rsub.add_parser("run")
    rr.add_argument("--hypothesis", required=True)
    rr.add_argument("--store", required=True)
    rr.add_argument("--out", default="research_runs")
    rr.add_argument("--from-ts")
    rr.add_argument("--to-ts")
    rr.add_argument("--max-events", type=int)
    rr.add_argument("--latency-ms", type=int)
    rr.add_argument("--fee-bps", type=float)
    rr.add_argument("--slippage-bps", type=float)
    rr.add_argument("--min-liquidity", type=float)
    rr.add_argument("--skip-ai", action="store_true")
    rr.add_argument("--debug", action="store_true")
    rc = rsub.add_parser("critique")
    rc.add_argument("--run", required=True)
    rl = rsub.add_parser("list")
    rl.add_argument("--out", default="research_runs")
    rins = rsub.add_parser("inspect")
    rins.add_argument("--run", required=True)

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
    if args.command == "research":
        if args.research_command == "init":
            return run_research_init(args.name, args.out, args.kind)
        if args.research_command == "run":
            return run_research_run(
                hypothesis=Path(args.hypothesis),
                store=Path(args.store),
                out=Path(args.out),
                from_ts=args.from_ts,
                to_ts=args.to_ts,
                max_events=args.max_events,
                latency_ms=args.latency_ms,
                fee_bps=args.fee_bps,
                slippage_bps=args.slippage_bps,
                min_liquidity=args.min_liquidity,
                skip_ai=args.skip_ai,
                debug=args.debug,
            )
        if args.research_command == "critique":
            return run_research_critique(args.run)
        if args.research_command == "list":
            return run_research_list(args.out)
        if args.research_command == "inspect":
            return run_research_inspect(args.run)
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
