# Tablet standalone parity audit

Baseline: c3b843fe. Existing server-backed Android acceptance is not standalone acceptance. F26/F27/F29/F30 real-money operations are deliberately excluded; their safety/audit principles remain relevant to PAPER. Every other phase requires local runtime, storage and UI qualification. No complete local phase is accepted.

| Phase | Existing capability | Local acceptance | Required work |
|---|---|---|---|
| F0 | Foundation — repository, domain base, config, DB, Redis, Docker, CI, audit, testing, logging. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F1 | Universal market data — assets/providers/history/candles/trades/quotes/quality/replay. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F2 | Charting foundation — Next.js shell, search, candles, timeframes, volume, API. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F3 | Technical intelligence — causal versioned indicator features. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F4 | Market structure — confirmed swings, HH/HL/LH/LL, BOS, CHOCH. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F5 | Support/resistance — evidence-based zones and chart overlays. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F6 | Multi-timeframe — separate analyses, aggregation and disagreement. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F7 | Regime engine — classifications and probabilities. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F8 | Forecast infrastructure — immutable forecasts, outcomes, horizons, evaluation. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F9 | Baseline forecast models — calibration, temporal economic evaluation. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F10 | Pocket Score — configurable explained components. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F11 | Directional engine — independent LONG/SHORT/NO_TRADE. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F12 | Opportunity Score — trade/horizon net economic ranking. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F13 | Analyze — full shared analysis experience. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F14 | Watchlists — persistence, snapshots, alert events. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F15 | Scanner — cross-market filters and ranking. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F16 | Portfolio — manual positions, accounting and dashboard. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F17 | Portfolio intelligence — correlations, concentration and allocation. | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F18 | Fundamentals — immutable provider facts and causal financial context implemented; see | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F19 | Derivatives intelligence — causal funding/basis/OI and reported options context implemented; | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F20 | Sentiment/news/macro — causal context and real public market-data gate implemented; see | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F21 | Backtesting — causal event-driven simulation implemented for crypto spot LONG; see | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F22 | Research factory — immutable temporal experiments, robustness diagnostics, one-shot holdout | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F23 | Paper trading — explicit public data, persistent simulated execution; see | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F24 | Strategies — versioned proposals, portfolio and evidence-linked lifecycle; see | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F25 | Leverage research — conditional isolated linear liquidation and stress; see | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F26 | Live read-only — native Binance Spot GET observations and local reconciliation implemented; | EXCLUDED: real-money operation | No native broker dispatch; preserve safety controls |
| F27 | Live small — spot admission/journal/idempotency architecture and native read/query adapter implemented; | EXCLUDED: real-money operation | No native broker dispatch; preserve safety controls |
| F28 | Autopilot — fail-closed scanning, existing allocation, monitoring and fresh-portfolio compounding orchestration implemented; see [report](PHASE_28_COMPLETION_REPORT.md). | NOT QUALIFIED | Qualify kernel/dependencies, native persistence, working tablet workflow and acceptance vectors |
| F29 | Derivative execution — isolated linear LONG/SHORT, controlled leverage, durable synthetic | EXCLUDED: real-money operation | No native broker dispatch; preserve safety controls |
| F30 | Live control plane — persistent modes, policy, readiness, operator transitions and kill switch; | EXCLUDED: real-money operation | No native broker dispatch; preserve safety controls |

## Operational UI update

Default standalone launch, public EUR spot discovery/history, qualified local SMA/EMA, one-market manual PAPER accounts, local portfolio valuation/history and portable encrypted restore are implemented. This does not change complete phase-level acceptance: no full F0–F30 parity is claimed. Native strategy/forecast/directional, multi-position accounting, autopilot, scanner/watchlists, operational reports, biometric security and physical qualification remain incomplete. See RELEASE_READINESS.md and the operational flow documents for current bounded capabilities.
