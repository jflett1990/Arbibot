# Arbibot Development Plan for Codex

## Development Principle

Build the research and measurement system first. Live trading comes later, if the replay and paper results justify it.

Codex should work one phase at a time. Do not ask it to build the whole bot in one run.

## Phase 0 — Scaffold

Goal: create the project skeleton, schemas, config, time utilities, and tests.

Build:

- Python package under `src/arbibot`
- typed event schemas
- YAML config loader
- time utilities
- custom error types
- smoke tests

Acceptance:

- tests pass
- events serialize/deserialize
- malformed timestamps fail loudly
- no external API clients yet

## Phase 1 — Event Store

Goal: append-only local persistence.

Build:

- `storage/event_store.py` interface
- `storage/sqlite_store.py` implementation
- SQLite WAL mode
- deterministic replay ordering
- idempotency by event ID

Acceptance:

- append and replay work
- duplicate event behavior is explicit
- corrupted records do not crash the full replay stream

## Phase 2 — Ingestion Interfaces

Goal: define vendor-neutral contracts before touching live APIs.

Build:

- `SpotMarketDataClient`
- `PredictionMarketDataClient`
- `ExternalSignalClient`
- mock deterministic clients

Acceptance:

- consumers depend only on internal event models
- no vendor payload leaks outside adapters

## Phase 3 — Binance Ingestor

Goal: normalize BTCUSDT spot stream data.

Build:

- Binance WebSocket adapter
- fixture-driven parsing first
- reconnect handling
- stale-stream health events
- timestamp capture immediately on receipt

Acceptance:

- fixture payloads normalize correctly
- reconnect state is explicit
- handler does not do heavy blocking work

## Phase 4 — Candle Builder

Goal: deterministic 5-minute bars from ticks.

Build:

- source timestamp bucket logic
- OHLCV
- trade count
- finalized bar emission
- out-of-order tolerance

Acceptance:

- exact boundary timestamps are correct
- late ticks handled deterministically

## Phase 5 — Polymarket Book Builder

Goal: reconstruct local UP/DOWN order books.

Build:

- book snapshot handling
- price-level delta handling
- level deletion on size zero
- tick-size change handling
- weighted executable price calculation
- spread/depth/imbalance metrics

Acceptance:

- snapshots and deltas reconstruct correctly
- empty/crossed books are flagged
- weighted execution price is tested

## Phase 6 — Feature Engine

Goal: compute features for opportunity detection.

Build spot features:

- short-window returns
- realized volatility
- momentum slope
- acceleration
- distance to threshold

Build book features:

- best bid/ask
- spread
- depth
- imbalance
- stale age
- weighted executable price

Acceptance:

- deterministic fixtures produce deterministic features
- stale flags are explicit

## Phase 7 — Fair-Price Model

Goal: estimate UP/DOWN probability.

Build:

- simple lognormal proxy model
- inputs: spot, threshold, time to expiry, volatility, shrunk momentum
- probability clamps
- invalid input handling

Acceptance:

- monotonic behavior around threshold
- no NaNs or divide-by-zero
- near-expiry behavior tested

## Phase 8 — Edge and Trade Gates

Goal: produce auditable trade/no-trade decisions.

Build:

- gross edge calculation
- fee estimate
- slippage estimate
- spread cost
- latency risk
- model-error buffer
- net edge
- hard gates

Hard gates:

- stale Binance data
- stale Polymarket data
- low liquidity
- wide spread
- conflicting signal
- market too close to expiry
- daily loss cap
- unknown order state
- edge below threshold

Acceptance:

- every no-trade decision has a reason
- no edge calculation assumes top-of-book fill for larger size

## Phase 9 — Paper Execution

Goal: simulate orders pessimistically.

Build:

- paper FAK/FOK
- passive order simulation
- visible-depth fills
- future trade-through requirement for passive fills
- order events

Acceptance:

- full fill, partial fill, no fill, stale book, insufficient depth tested
- paper fills are pessimistic by default

## Phase 10 — Replay Engine

Goal: replay persisted events deterministically.

Build:

- event stream replay
- state reconstruction
- latency injection
- simulated decision/execution path
- replay summary report

Summary metrics:

- trades
- fills
- rejects
- gross PnL
- net PnL
- max drawdown
- average edge
- realized edge
- skipped-by-reason counts

Acceptance:

- same input log creates same output
- latency injection changes outcomes where expected

## Phase 11 — Risk Engine

Goal: independent veto layer.

Build:

- 0.5% risk per trade
- 2% daily loss cap
- -0.4% hard stop
- max exposure
- max open orders
- max daily traded notional
- kill switch

Acceptance:

- strong edge cannot bypass risk
- unknown order state blocks trading
- risk state is serializable

## Phase 12 — Observability

Goal: make failures diagnosable.

Build:

- structured JSON logs
- metrics registry
- health state generator
- local CLI status command

Acceptance:

- failed/no-trade states can be diagnosed from logs and metrics

## Phase 13 — Live Interface Disabled

Goal: create live execution boundary without enabling trading.

Build:

- `submit_order`
- `cancel_order`
- `cancel_all`
- `get_open_orders`
- `get_order_status`
- mock implementation
- `LIVE_TRADING_ENABLED=false` guard

Acceptance:

- live submit raises unless explicitly enabled
- no accidental live path exists

## Phase 14 — Graph Fusion

Goal: add deterministic graph signal scoring.

Build:

- config-driven nodes and edges
- bull score
- bear score
- convergence
- conflict
- confidence
- stale node decay

Acceptance:

- bull convergence tested
- bear convergence tested
- conflict suppression tested
- stale decay tested

## Phase 15 — External Adapters

Goal: add secondary context inputs.

Build:

- TradingView webhook adapter
- CryptoQuant polling interface
- TTL handling
- slow-regime flag for CryptoQuant

Acceptance:

- external signals cannot trigger trades alone
- stale/malformed payloads are tested

## Phase 16 — Live Pilot

Goal: tiny controlled live mode.

Build only after Phases 0-15 pass.

Requirements:

- `LIVE_TRADING_ENABLED=true`
- `PILOT_MODE=true`
- max order size configured
- startup confirmation
- one active market
- one active order
- FAK/FOK only
- disable on unknown order state
- disable on disconnect

Acceptance:

- pilot cannot exceed max order size
- degraded states disable trading

## Phase 17 — Passive Orders

Goal: add short-lived maker logic only if justified.

Build:

- max live time
- cancel on signal decay
- cancel on stale book
- cancel near expiry
- one replacement max
- pessimistic queue estimate

Acceptance:

- no quote chasing
- no order spam
- adverse-selection fill test exists

## First Codex Prompt

```text
Implement Phase 0 only for Arbibot.

Create core event schemas, config loader, time utilities, error types, package scaffold, and tests.

Do not implement Binance, Polymarket, TradingView, CryptoQuant, execution, or live trading.

Every event must include event_id, source, source_ts_ms, recv_wall_ts_ms, recv_monotonic_ns, and optional sequence_id.

Run tests, lint, and type checks before finishing.
```

## Rule

If Codex tries to build live trading before replay and paper execution exist, stop it.
