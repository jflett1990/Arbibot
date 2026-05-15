# Arbibot

Local-first research and execution architecture for measuring and, only if validated, trading repricing lag in BTC UP/DOWN 5-minute Polymarket markets.

This repository is intentionally documentation-first. The system must prove that a measurable edge exists before live trading code is allowed to exist. The core thesis is not "predict Bitcoin." The thesis is narrower: detect temporary lag between Binance BTC spot movement and Polymarket CLOB repricing, then trade only when the expected edge survives spread, fees, slippage, latency, queue uncertainty, and risk limits.

## Current repo state

This is the initial scaffold for Codex-driven development. It includes:

- `AGENTS.md` — hard operating contract for Codex and coding agents.
- `docs/SYSTEM_DESIGN.md` — full architecture and engineering design.
- `docs/DEVELOPMENT_PLAN.md` — staged Codex implementation plan.
- `docs/TOOLS_AND_SKILLS.md` — required APIs, local tools, skills, and operational constraints.
- `.codex/tasks.md` — ordered task queue for Codex.
- `.codex/guardrails.md` — specific things Codex must not build prematurely.
- `.github/workflows/ci.yml` — starter CI for lint/type/test once code exists.
- `pyproject.toml` — Python project configuration.
- `configs/*.yaml` — safe default configs with live trading disabled.

## Non-negotiable premise

Live trading is not part of the MVP.

The MVP is:

1. Record Binance spot events.
2. Record Polymarket order book events.
3. Normalize timestamps.
4. Persist every event.
5. Replay deterministically.
6. Simulate fills pessimistically.
7. Measure whether repricing lag survives real frictions.

Only after that should live execution be added, and even then only in tiny pilot mode.

## Proposed stack

- Python 3.11+ for MVP and research.
- `asyncio` for ingestion.
- `pydantic` for schemas.
- SQLite WAL for append-only event storage.
- Optional DuckDB/Parquet exports for research.
- `pytest`, `ruff`, `mypy` for quality gates.
- No GPU dependency.
- No cloud dependency in the core loop.

## Suggested setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Safety stance

This system should default to paper mode. Live trading requires explicit config, tested order-state reconciliation, hard risk gates, and a working kill switch.

If a future implementation cannot explain every trade/no-trade decision from persisted records, it is not production-ready.
