# Feature parity matrix

Baseline capabilities audited against roadmap, architecture, route handlers and final release/security/financial reviews. Status vocabulary: FULLY_AVAILABLE (existing platform), BACKEND_ONLY, ANDROID_IMPLEMENTED (not verification), ANDROID_VERIFIED (device+service evidence), EXTERNAL_DEPENDENCY, BLOCKED. No row is ANDROID_VERIFIED at discovery.

| Phase | Capability | Existing status | Android status | Verification gap |
|---|---|---|---|---|
| F0 | Foundation — repository, domain base, config, DB, Redis, Docker, CI, audit, testing, logging. | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F1 | Universal market data — assets/providers/history/candles/trades/quotes/quality/replay. | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F2 | Charting foundation — Next.js shell, search, candles, timeframes, volume, API. | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F3 | Technical intelligence — causal versioned indicator features. | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F4 | Market structure — confirmed swings, HH/HL/LH/LL, BOS, CHOCH. | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F5 | Support/resistance — evidence-based zones and chart overlays. | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F6 | Multi-timeframe — separate analyses, aggregation and disagreement. | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F7 | Regime engine — classifications and probabilities. | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F8 | Forecast infrastructure — immutable forecasts, outcomes, horizons, evaluation. | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F9 | Baseline forecast models — calibration, temporal economic evaluation. | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F10 | Pocket Score — configurable explained components. | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F11 | Directional engine — independent LONG/SHORT/NO_TRADE. | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F12 | Opportunity Score — trade/horizon net economic ranking. | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F13 | Analyze — full shared analysis experience. | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F14 | Watchlists — persistence, snapshots, alert events. | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F15 | Scanner — cross-market filters and ranking. | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F16 | Portfolio — manual positions, accounting and dashboard. | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F17 | Portfolio intelligence — correlations, concentration and allocation. | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F18 | Fundamentals — immutable provider facts and causal financial context implemented; see | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F19 | Derivatives intelligence — causal funding/basis/OI and reported options context implemented; | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F20 | Sentiment/news/macro — causal context and real public market-data gate implemented; see | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F21 | Backtesting — causal event-driven simulation implemented for crypto spot LONG; see | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F22 | Research factory — immutable temporal experiments, robustness diagnostics, one-shot holdout | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F23 | Paper trading — explicit public data, persistent simulated execution; see | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F24 | Strategies — versioned proposals, portfolio and evidence-linked lifecycle; see | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |
| F25 | Leverage research — conditional isolated linear liquidation and stress; see | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F26 | Live read-only — native Binance Spot GET observations and local reconciliation implemented; | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F27 | Live small — spot admission/journal/idempotency architecture and native read/query adapter implemented; | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F28 | Autopilot — fail-closed scanning, existing allocation, monitoring and fresh-portfolio compounding orchestration implemented; see [report](PHASE_28_COMPLETION_REPORT.md). | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F29 | Derivative execution — isolated linear LONG/SHORT, controlled leverage, durable synthetic | BACKEND_ONLY | BLOCKED | Native implementation and integration/device evidence pending |
| F30 | Live control plane — persistent modes, policy, readiness, operator transitions and kill switch; | FULLY_AVAILABLE | BLOCKED | Native implementation and integration/device evidence pending |

## Additional acceptance requirements

| Capability | Status | Gap |
|---|---|---|
| Native identity | BLOCKED | Server sessions, rotation, revocation, device inventory |
| Incremental multi-device synchronization | BLOCKED | Cross-entity change feed, cursors, conflicts, snapshot recovery |
| Remote push | EXTERNAL_DEPENDENCY | Delivery account/credentials and registered devices |
| Real-money qualification | BLOCKED | Explicitly unauthorized; not part of mobile authorization |

Verified Android parity: **0 / 31 phase groups (0%)** at discovery. This denominator is phase-level only, not a claim of exhaustive acceptance coverage.
