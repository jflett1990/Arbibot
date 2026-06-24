# Research Sprint Harness

Arbibot's research harness turns BTC/Polymarket repricing-lag ideas into falsifiable local replay experiments. It does **not** trade live, sign orders, handle wallets, or place exchange orders.

## Setup

```bash
python -m arbibot research init --name impulse_lag_test
python -m arbibot research run --hypothesis research/hypotheses/impulse_lag_test.yaml --store data/session.sqlite --skip-ai
python -m arbibot research inspect --run research_runs/<run_id>
```

## Bedrock/OpenAI-compatible critique

AI critique is optional. The intended default provider is Amazon Bedrock through an OpenAI-compatible endpoint:

```bash
export OPENAI_BASE_URL="https://bedrock-mantle.us-east-1.api.aws/v1"
export OPENAI_API_KEY="<amazon-bedrock-api-key>"
export ARBIBOT_RESEARCH_MODEL="<bedrock-model-id-or-configured-model-name>"
```

If credentials are missing, replay and QA still run and `qa_report.json` records `skipped_missing_model_config`.

## Hypothesis YAML

Hypotheses include `id`, `name`, `kind`, `description`, `market_scope`, `time_window`, measurable entry/exit conditions, feature requirements, cost assumptions, risk gates, promotion criteria, rejection criteria, and notes.

## Research packet

Each run writes `hypothesis.md`, `hypothesis.yaml`, `feature_spec.json`, `replay_config.json`, `replay_results.csv`, `edge_summary.md`, `failure_modes.md`, `ai_critique.md`, `next_experiments.md`, `qa_report.json`, and `manifest.json`.

## Decisions

The harness uses deterministic gates for spread, liquidity, book age, raw edge, cost-adjusted edge, latency, missing Binance context, and missing Polymarket context. Results are marked `promote_to_more_replay`, `revise`, or `reject`. Weak or incomplete evidence should be revised or rejected, never promoted to live trading.

## Limitations

The adapter currently consumes persisted `SpotTick` and `PolyBookSnapshot` events from the existing SQLite event store. Missing historical data creates a blocked packet with explicit QA reasons.
