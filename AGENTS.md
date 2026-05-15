# AGENTS.md

You are building Arbibot: a local-first, event-driven research and trading system for BTC UP/DOWN 5-minute Polymarket markets.

## Primary objective

Build a deterministic measurement and simulation platform before any live trading.

The system's edge is not assumed. The system exists to measure whether repricing lag exists and whether it survives fees, spread, slippage, latency, liquidity limits, queue uncertainty, and operational failure modes.

## Hard rules

- Do not add live order placement unless the task explicitly requests it.
- Do not invent external API endpoints.
- If an external API is uncertain, define a typed interface and a mock implementation.
- All market data events must preserve source timestamp, local wall-clock receive timestamp, and monotonic receive timestamp.
- All decision logic must be replayable from persisted events.
- Every trade/no-trade decision must emit an auditable `DecisionRecord`.
- No hidden global state in trading logic.
- No blocking network calls inside the hot decision path.
- No GPU dependency.
- No cloud dependency in the core trading loop.
- No placeholder TODOs in committed code.
- Every module must include tests for success, stale data, malformed data, and boundary cases.
- Use explicit failure states instead of silent fallback behavior.
- Prefer small, composable modules over giant orchestration files.
- Default to paper trading and replay.
- Live trading must be disabled by default.

## Definition of done

Before completing any task:

- Code runs locally.
- Tests pass.
- Types pass where type checks are configured.
- Lint passes where linting is configured.
- New behavior has deterministic tests.
- External dependencies are isolated behind interfaces.
- Any assumption is documented in the changed file or task response.
- No secrets, API keys, credentials, or private account data are committed.

## Architecture discipline

Research code and production-critical code must remain separated.

Production-critical:

- event schemas
- ingestion adapters
- book builder
- candle builder
- feature engine
- fair-value model
- opportunity detector
- risk engine
- execution interfaces
- event store
- replay engine
- health/observability

Research-only:

- notebooks
- plots
- parameter sweeps
- graph visualizations
- exploratory scripts

No notebook logic may be required for production execution.

## Trading safety

Live trading may not be introduced until replay, paper execution, risk shutdown, stale-data handling, order-state reconciliation, and safe restart behavior have tests.

If an implementation cannot prove why it traded or why it refused to trade, it is wrong.
