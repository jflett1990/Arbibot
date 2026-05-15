# Tools and Skills Required

## 1. Local Development Tools

Required:

- Python 3.11+
- Git
- GitHub CLI (`gh`)
- SQLite
- Terminal environment

Recommended:

- `uv` or `pip-tools` for faster dependency workflows
- `direnv` for local environment loading
- OS-level NTP/clock sync
- DuckDB for research queries over exported events

## 2. Python Libraries

Core MVP:

- `pydantic` for event schemas
- `PyYAML` for config
- `websockets` for market streams
- `httpx` for REST adapters
- `orjson` for fast JSON serialization
- `numpy` for features and graph scoring
- `pandas` for research exports
- `duckdb` for replay analysis
- `pytest` for tests
- `ruff` for linting
- `mypy` for type checks

Do not add heavyweight ML frameworks to the hot path.

## 3. External Systems

### Binance

Use Binance WebSocket data for BTCUSDT spot movement.

Responsibilities:

- ingest ticks/trades/book ticker
- timestamp immediately on receipt
- normalize to internal events
- handle reconnects and staleness

Binance is data-only for this system. Do not build a Binance order execution layer.

### Polymarket

Use Polymarket market data for order book state and eventual order execution.

Responsibilities:

- active market discovery
- token ID and market metadata retrieval
- book snapshot/delta ingestion
- user/order stream when live mode exists
- order submission only after live pilot phase

If an endpoint or payload is uncertain, create a typed interface and fixture-driven adapter. Do not invent behavior.

### TradingView

Use TradingView as a secondary context/suppression signal via webhook.

Rules:

- must have TTL
- must preserve received timestamp
- source timestamp optional but preferred
- cannot trigger trades alone

### CryptoQuant

Use CryptoQuant as slow regime context only.

Rules:

- not hot path
- not sub-minute trigger
- stale/revised data risk must be modeled
- cannot trigger trades alone

## 4. Codex Usage Pattern

Codex should receive one phase at a time.

Good task shape:

```text
Implement Phase N only.
Touch only these modules.
Add these tests.
Do not implement live trading.
Run tests/lint/types.
Report assumptions and changed files.
```

Bad task shape:

```text
Build the whole bot.
Make it production-ready.
Add live trading.
Optimize it.
```

That prompt will produce a glittering swamp.

## 5. Agent Files

Required:

- `AGENTS.md`: top-level project contract for Codex and coding agents.
- `.codex/tasks.md`: ordered implementation queue.
- `.codex/guardrails.md`: hard prohibitions and safety rules.

Optional later:

- `.codex/review_checklist.md`
- `.codex/replay_validation.md`
- `.codex/live_trading_unlock.md`

## 6. Operational Skills Needed

Engineering skills:

- event-driven architecture
- WebSocket ingestion
- timestamp normalization
- local order book reconstruction
- deterministic replay
- simulation and pessimistic fill modeling
- risk-gated execution design
- structured logging and metrics

Quant/research skills:

- market microstructure skepticism
- binary-outcome fair-value modeling
- latency-aware backtesting
- walk-forward validation
- ablation testing
- overfit detection

Trading operations skills:

- rate-limit handling
- partial-fill handling
- stale quote suppression
- exposure management
- kill-switch design
- safe restart behavior

## 7. Hardware / Runtime Assumptions

MVP:

- single local machine
- CPU only
- wired internet preferred
- no cloud dependency
- no GPU

Production pilot:

- prevent system sleep
- use stable network
- monitor clock drift
- keep logs local and backed up

## 8. Security Requirements

- Never commit `.env`.
- Never log secrets.
- Use separate paper/live config.
- Default live trading to false.
- Require explicit startup confirmation for pilot mode.
- Add kill switch before live order support.

## 9. Quality Gates

Before live pilot:

- deterministic replay passes
- paper execution passes pessimistic fill tests
- order-state reconciliation is tested
- risk shutdown is tested
- stale-data behavior is tested
- live trading disabled-by-default tests pass
- secrets are excluded from repo

## 10. What Not to Build Yet

Do not build these until evidence justifies them:

- dashboard polish
- ML training stack
- graph visualization UI
- multi-market scaling
- passive maker quoting
- auto-optimization
- cloud deployment
- any order-spam mechanism
- live trading without explicit pilot guardrails
