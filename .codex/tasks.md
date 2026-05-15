# Codex Task Queue

Work through these tasks in order. Do not skip ahead.

## Task 000 — Scaffold

Build core schemas, config loader, time utilities, error types, and tests.

## Task 001 — Event Store

Implement append-only SQLite WAL event storage with deterministic replay ordering.

## Task 002 — Ingestion Interfaces

Define vendor-neutral market-data client interfaces and deterministic mock clients.

## Task 003 — Binance Ingestor

Implement Binance WebSocket normalization from fixture payloads first, then live stream support.

## Task 004 — Candle Builder

Build deterministic 5-minute bars from source timestamps.

## Task 005 — Polymarket Book Builder

Implement local book reconstruction from snapshots and deltas.

## Task 006 — Feature Engine

Compute spot, momentum, volatility, liquidity, and stale-data features.

## Task 007 — Fair-Price Model

Implement simple lognormal proxy model for UP/DOWN probability.

## Task 008 — Edge and Gates

Compute net edge and emit auditable trade/no-trade decisions.

## Task 009 — Paper Execution

Simulate pessimistic FAK/FOK and passive fills.

## Task 010 — Replay Engine

Replay persisted events deterministically with latency injection.

## Task 011 — Risk Engine

Implement position sizing, exposure caps, daily stop, hard stop, and kill switch.

## Task 012 — Observability

Add structured logs, metrics, health state, and local status output.

## Task 013 — Live Interface Disabled

Create live execution interface with hard disabled-by-default guard.

## Task 014 — Graph Fusion

Implement deterministic graph signal fusion.

## Task 015 — External Adapters

Add TradingView webhook and CryptoQuant slow-regime adapters.

## Task 016 — Live Pilot

Implement tiny live pilot mode with explicit unlock requirements.

## Task 017 — Passive Orders

Add short-lived passive maker logic only after taker path validation.
