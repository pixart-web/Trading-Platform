# Data and causality review

## Invariant

For a decision declared at time T, inputs with availability after T must not influence the result. Event time, publication time, availability time, ingestion time and processing/receipt time are kept distinct when the source domain supplies them.

## Reviewed boundaries

- Market data stores open/close/receipt identity, rejects invalid gaps/duplicates and replays deterministic trusted prefixes.
- Technical, structure and zones operate on closed causal prefixes; prefix-invariance and swing/BOS/CHOCH confirmation tests prevent future-bar leakage.
- Multi-timeframe analyses use one declared cutoff, independent native resolutions, freshness checks and explicit disagreement/unavailable states.
- Regime fitting and inference are separate; temporal evaluation rejects overlap. Research probabilities remain unavailable without a supplied model and are not presented as calibrated by default.
- Forecasts are immutable; outcomes are separate post-maturity records. Outcome validation covers expiry, MFE/MAE interval and evidence identity.
- Fundamentals preserve publication/availability/ingestion and revision/restatement identity; point-in-time snapshot tests exclude later facts.
- Context/news/macro preserve event/publication/availability and explicit REAL/SYNTHETIC provenance. Scheduled events are not treated as occurred observations.
- Scanner/Analyze/watchlist snapshots bind exact report IDs, as-of times, policy versions/hashes and deterministic ranks.
- Backtesting uses immutable datasets, complete-bar-close execution and explicit receipts; impossible same-bar execution and future forecast evidence are rejected.
- Research uses temporal partitions, embargoes, immutable hashes and one-use final holdout consumption. Losing trials and cost variants remain part of evidence.
- Strategy, PAPER and Autopilot require evidence available at the decision time; lifecycle/scan/proposal/quote/portfolio timestamps fail closed when stale or future.

## Findings

No reproducible future leakage was found. The source has strong synthetic regression coverage for prefix invariance and point-in-time behavior. Remaining limitations are economic: single/few-market selection, survivorship, provider revisions not captured historically, broad cross-regime/cross-asset validation and independent real dataset custody have not been demonstrated. Public imports record receipt-time availability and must never backdate knowledge to candle open.
