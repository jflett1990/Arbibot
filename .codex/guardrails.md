# Codex Guardrails

## Forbidden until explicitly requested

- Live order placement
- Passive maker quoting
- Auto-optimization
- Cloud deployment
- Any GPU dependency
- Any untested external API call in the hot path
- Any code that assumes perfect fills
- Any code that assumes unlimited liquidity
- Any code that assumes sub-100ms execution
- Any code that hides no-trade reasons
- Any code that silently falls back after stale data

## Required for every trading-related change

- Decision records must be auditable.
- Risk engine must be able to veto.
- Stale data must block new trades.
- Unknown order state must block new trades.
- Tests must include failure paths.

## Default posture

The bot should usually not trade. No-trade is a valid and expected decision.
