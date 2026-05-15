# Arbibot System Design

## 1. Executive Summary

Arbibot is a local-first, CPU-only research and trading architecture for BTC UP/DOWN 5-minute Polymarket markets.

The edge is not general BTC prediction. The edge, if it exists, is temporary repricing lag between Binance BTC spot movement and delayed adjustment in Polymarket's CLOB/order book.

The system must first measure whether lag exists after realistic frictions:

- spread
- fees
- slippage
- latency
- queue uncertainty
- liquidity limits
- stale data
- operational failures

Live trading is not part of the MVP.

## 2. Feasibility Verdict

Structurally plausible, but fragile.

Short-horizon prediction markets can lag fast spot markets because they have different participants, latency paths, liquidity profiles, and repricing behavior. That does not mean the lag is tradable. A small apparent edge can disappear after order submission latency, spread, taker cost, queue priority, adverse selection, and thin depth.

Treat these claims as hypotheses, not assumptions:

- sub-100ms execution
- 1000+ orders per second
- 0.3% to 0.8% captured per trade

The realistic operating target for a local retail machine is not consistent sub-100ms full-loop trading. Internal compute should be milliseconds or less; external network/API/order acknowledgement can dominate and may land in the 250ms-1500ms range.

## 3. Core Assumptions

- Runs locally on one machine.
- CPU-only in the hot path.
- No cloud dependency in the core loop.
- Binance BTCUSDT is primary reference data.
- Polymarket CLOB/order book is the traded venue.
- TradingView and CryptoQuant are secondary context/suppression inputs, not primary triggers.
- Replay and paper simulation must come before live execution.
- Live trading is disabled by default.

## 4. Major Components

### Market Registry

Discovers and validates the active BTC UP/DOWN 5-minute market.

Responsibilities:

- condition ID
- token IDs
- outcome mapping
- tick size
- minimum order size
- fee schedule
- market close time
- resolution rule metadata

Trading must be blocked if required metadata is missing.

### Binance Ingestor

Consumes Binance BTCUSDT WebSocket events.

Outputs normalized events:

- `SpotTick`
- `SpotBar`
- `SpotMicroMove`

Each event must preserve source timestamp, local receive wall timestamp, and monotonic receive timestamp.

### Polymarket Book Ingestor

Consumes Polymarket market data.

Maintains local order books for UP/DOWN tokens:

- bids
- asks
- best bid
- best ask
- mid
- spread
- depth at tick bands
- imbalance
- last trade
- last update age

### External Signal Layer

TradingView and CryptoQuant enter through adapters.

TradingView:

- webhook input
- short TTL
- source timestamp preferred
- cannot trigger trades alone

CryptoQuant:

- slow regime context
- not hot path
- cannot trigger trades alone

### Feature Engine

Computes rolling features from spot, book, external, and health state.

### Fair-Price Model

Estimates UP/DOWN probability from:

- current BTC price
- market threshold
- time to expiry
- short-window volatility
- heavily shrunk momentum

This model is a proxy, not alpha proof.

### Graph Fusion Engine

A deterministic sparse graph model with approximately 100 nodes and 180 edges.

Nodes represent signal atoms. Edges represent influence. Output is bull/bear convergence, conflict, direction, and confidence.

No visual force graph belongs in the production hot path.

### Opportunity Detector

Determines whether the market is stale relative to expected fair probability and whether the edge survives execution costs.

### Risk Engine

Independent veto layer. Strong signals cannot bypass risk.

### Execution Engine

Disabled for MVP. Later supports:

- FAK/FOK taker orders
- short-lived passive orders only after validation
- cancellation
- reconciliation
- unknown order state blocking

### Event Store

Append-only local event store. SQLite WAL for MVP.

All raw events, features, decisions, orders, fills, cancels, and risk events must be replayable.

### Replay Engine

Reconstructs system state from event logs and simulates decisions/fills with latency injection.

### Observability

Structured logs, metrics, health checks, and audit trail.

## 5. Data Flow

```text
Binance WS -> Spot Events -> Feature Engine -> Fair Price Model

Polymarket WS -> Book Builder -> Feature Engine -> Executable Price/Depth

TradingView/CryptoQuant -> External Signal Adapters -> Graph Fusion

Feature Snapshot -> Graph Fusion -> Opportunity Detector -> Risk Engine -> Execution/Paper Engine

All Events -> Event Store -> Replay/Backtest/Analysis
```

## 6. Timestamp Discipline

Every event must include:

- `source_ts_ms`
- `recv_wall_ts_ms`
- `recv_monotonic_ns`
- optional `sequence_id`

Use source time for market ordering. Use monotonic time for latency measurement. Use wall time for logs and human review.

Block trading when:

- Binance data age exceeds threshold
- Polymarket book age exceeds threshold
- clock drift is unsafe
- reconnect gap has not been reconciled

## 7. Feature Set

### Spot Features

- returns: 250ms, 500ms, 1s, 2s, 5s, 10s
- realized volatility: 5s, 30s, 5m
- momentum slope
- acceleration
- distance to threshold
- threshold-cross velocity
- current price percentile in 5-minute candle

### Book Features

- best bid/ask for UP/DOWN
- midpoint
- spread
- depth at 1/2/3/5 ticks
- weighted executable price for target size
- imbalance
- last trade direction
- book update frequency
- underreaction residual
- stale-book age

### External Features

TradingView:

- direction
- strength
- timeframe
- TTL-adjusted confidence
- conflict count

CryptoQuant:

- inflow/outflow regime
- netflow z-score
- reserve change regime
- freshness/slow-context flag

## 8. Graph Model

Node groups:

- spot momentum
- short-term volatility
- market threshold state
- Polymarket book state
- liquidity quality
- external context
- latency/health
- risk state
- market structure

Node fields:

- value in [-1, 1]
- confidence in [0, 1]
- freshness in [0, 1]
- direction: BULL, BEAR, NEUTRAL

Edge message:

```text
message = edge_weight * source_value * source_confidence * source_freshness
```

Output:

- bull score
- bear score
- convergence
- conflict
- final direction
- confidence

Conflicting bull/bear evidence suppresses trading.

## 9. Opportunity Detection

A repricing lag opportunity exists only when all are true:

- Binance move materially changes estimated fair probability.
- Polymarket executable price has not adjusted enough.
- Net edge is positive after friction.
- Liquidity is sufficient for target size.
- Primary data is fresh.
- Signal convergence is high.
- Conflict is low.
- Risk state allows trading.

Net edge:

```text
net_edge = fair_probability
         - executable_price
         - fee_cost
         - slippage_cost
         - spread_cost
         - latency_risk
         - queue_uncertainty
         - model_error_buffer
```

Default no-trade thresholds:

- no trade if net edge below minimum
- no trade if spread too wide
- no trade if depth below target multiple
- no trade in final seconds before resolution unless specifically validated
- no trade during stale data or unknown order state

## 10. Execution Design

MVP uses paper execution only.

Later execution modes:

### FAK/FOK Taker

Used for large fleeting edges. Pays spread and consumes depth.

### Short-Lived Passive Maker

Only after taker path is validated. Requires timeout, cancel rules, queue modeling, and adverse-selection tracking.

Execution protections:

- one live order per market in MVP
- max attempts per opportunity
- local token bucket
- no quote chasing
- cancel stale passive orders
- block on unknown order state
- reconcile after reconnect

## 11. Risk Management

Default rules:

- risk per trade: 0.5%
- daily loss cap: 2%
- hard stop: -0.4%
- max market exposure
- max open orders
- max daily traded notional
- liquidity filters
- contradictory-signal suppression
- kill switch

Risk engine must be independent from model and execution.

## 12. Latency Budget

Target local compute budget:

- event normalization: 0.1-2ms after packet arrival
- feature calculation: under 1ms
- graph scoring: under 1ms
- decision/gating: under 1ms

External budget is not fully controllable:

- network transit
- API gateway behavior
- Cloudflare/throttling
- order acknowledgement
- venue state propagation

Sub-100ms full-loop should not be assumed.

## 13. Backtesting and Validation

Use event-driven replay. Candle-only backtests are invalid for this strategy.

Replay must include:

- Binance ticks
- Polymarket snapshots/deltas
- market metadata
- external signals
- latency injection
- pessimistic fill modeling
- fee modeling
- slippage modeling
- queue uncertainty

Validation methods:

- walk-forward testing
- ablation tests
- simple threshold vs graph fusion
- no-latency vs realistic latency
- perfect-fill vs pessimistic-fill
- live paper vs replay comparison

## 14. Observability

Required logs:

- raw market events
- feature snapshots
- signal states
- decision records
- gate failures
- order lifecycle
- fills
- cancels
- rejects
- reconnects
- risk shutdowns

Required metrics:

- event age
- processing latency
- order latency
- fill rate
- partial fill rate
- slippage
- gate blocks by reason
- PnL
- exposure
- stale data count

## 15. Security and Compliance

- No secrets in repo.
- No real API keys in tests.
- Use `.env` or local secret storage.
- Separate paper/live config.
- Live trading disabled by default.
- Human confirmation required for pilot mode.
- Check exchange/API terms, account eligibility, and jurisdiction before live trading.

## 16. Known Failure Modes

At minimum, implementation must handle:

1. false edge detection
2. bad Binance data
3. stale Polymarket book
4. stale TradingView signal
5. CryptoQuant misuse
6. queue-position fantasy
7. liquidity vanishing
8. slippage exceeding edge
9. latency spike
10. API throttling
11. exchange disconnect
12. unknown order state
13. partial fill
14. overtrading
15. model drift
16. resolution-source mismatch
17. tick/min-size rejection
18. market-close distortion
19. complement-pricing trap
20. local machine failure

## 17. Bottom Line

Build the measurement machine first. The architecture is feasible. The alpha is unproven.
