# Feature parity matrix

Baseline capabilities audited against roadmap, architecture, route handlers and final release/security/financial reviews. Status vocabulary: FULLY_AVAILABLE (existing platform), BACKEND_ONLY, ANDROID_IMPLEMENTED (not verification), ANDROID_VERIFIED (device+service evidence), EXTERNAL_DEPENDENCY, BLOCKED. No entire phase is declared ANDROID_VERIFIED. Narrow passing paths do not establish phase-level acceptance.

| Phase | Capability | Existing status | Android status | Verification gap |
|---|---|---|---|---|
| F0 | Foundation — repository, domain base, config, DB, Redis, Docker, CI, audit, testing, logging. | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Native identity/API/cache foundation; full sync/release acceptance incomplete |
| F1 | Universal market data — assets/providers/history/candles/trades/quotes/quality/replay. | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Registered markets/search and bounded stored candles; provider coverage external |
| F2 | Charting foundation — Next.js shell, search, candles, timeframes, volume, API. | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Native candles/volume/gestures; indicators, structure and target overlays incomplete |
| F3 | Technical intelligence — causal versioned indicator features. | BACKEND_ONLY | BACKEND_ONLY | Shared technical kernel preserved; full native read model incomplete |
| F4 | Market structure — confirmed swings, HH/HL/LH/LL, BOS, CHOCH. | BACKEND_ONLY | BACKEND_ONLY | Shared structure kernel preserved; native overlays incomplete |
| F5 | Support/resistance — evidence-based zones and chart overlays. | FULLY_AVAILABLE | BACKEND_ONLY | Existing zones endpoint preserved; native bands not integrated |
| F6 | Multi-timeframe — separate analyses, aggregation and disagreement. | BACKEND_ONLY | BACKEND_ONLY | Shared multi-timeframe kernel preserved; dedicated native composition incomplete |
| F7 | Regime engine — classifications and probabilities. | BACKEND_ONLY | BACKEND_ONLY | Shared regime kernel preserved; native dashboard context incomplete |
| F8 | Forecast infrastructure — immutable forecasts, outcomes, horizons, evaluation. | BACKEND_ONLY | ANDROID_IMPLEMENTED | Immutable forecast artifacts displayed through Analyze; outcome/evaluation UX incomplete |
| F9 | Baseline forecast models — calibration, temporal economic evaluation. | BACKEND_ONLY | BACKEND_ONLY | Research producer/calibration preserved; no second Android forecast engine |
| F10 | Pocket Score — configurable explained components. | BACKEND_ONLY | ANDROID_IMPLEMENTED | Server Pocket Score circle/components/version/coverage; real stored-score device acceptance pending |
| F11 | Directional engine — independent LONG/SHORT/NO_TRADE. | BACKEND_ONLY | ANDROID_IMPLEMENTED | LONG/SHORT/NO_TRADE evidence from Analyze; targets/overlays incomplete |
| F12 | Opportunity Score — trade/horizon net economic ranking. | BACKEND_ONLY | ANDROID_IMPLEMENTED | Server Opportunity Score/economics and policy groups; comprehensive acceptance pending |
| F13 | Analyze — full shared analysis experience. | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Thirteen horizons, validated identity, history discovery; complete native analytic experience pending |
| F14 | Watchlists — persistence, snapshots, alert events. | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | CRUD/membership/revision API tests and native device CRUD pass; sort/filter/alerts/offline drafts incomplete |
| F15 | Scanner — cross-market filters and ranking. | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Server scan/filter/history/exclusion UI; complete filter and real-data/device acceptance pending |
| F16 | Portfolio — manual positions, accounting and dashboard. | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Manual ledger UI and server step-up/idempotency tests; full history/device scenarios incomplete |
| F17 | Portfolio intelligence — correlations, concentration and allocation. | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Existing intelligence report retrieval; rich correlation/allocation presentation incomplete |
| F18 | Fundamentals — immutable provider facts and causal financial context implemented; see | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Stored fundamentals snapshot UI; ratios/context/provider verification incomplete |
| F19 | Derivatives intelligence — causal funding/basis/OI and reported options context implemented; | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Stored contracts/curve/skew/context UI; real provider/device coverage pending |
| F20 | Sentiment/news/macro — causal context and real public market-data gate implemented; see | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Stored causal context UI; feed discovery/provider coverage incomplete |
| F21 | Backtesting — causal event-driven simulation implemented for crypto spot LONG; see | FULLY_AVAILABLE | BLOCKED | Known-run retrieval only; authenticated durable backtest submission/jobs absent |
| F22 | Research factory — immutable temporal experiments, robustness diagnostics, one-shot holdout | FULLY_AVAILABLE | BLOCKED | Report/model lookup only; durable research configuration/job service absent |
| F23 | Paper trading — explicit public data, persistent simulated execution; see | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Existing server PAPER state inspection; native start/control and complete device acceptance absent |
| F24 | Strategies — versioned proposals, portfolio and evidence-linked lifecycle; see | FULLY_AVAILABLE | ANDROID_IMPLEMENTED | Read-only catalog/lifecycle evidence; operational lifecycle actions backend-only |
| F25 | Leverage research — conditional isolated linear liquidation and stress; see | BACKEND_ONLY | BACKEND_ONLY | Conditional leverage research remains server/operator-only; no native execution authority |
| F26 | Live read-only — native Binance Spot GET observations and local reconciliation implemented; | BACKEND_ONLY | EXTERNAL_DEPENDENCY | Private read-only venue qualification absent; no broker keys or account journals exposed |
| F27 | Live small — spot admission/journal/idempotency architecture and native read/query adapter implemented; | BACKEND_ONLY | BACKEND_ONLY | Synthetic spot mechanism preserved; safe native operational monitoring absent; live dispatch disabled |
| F28 | Autopilot — fail-closed scanning, existing allocation, monitoring and fresh-portfolio compounding orchestration implemented; see [report](PHASE_28_COMPLETION_REPORT.md). | BACKEND_ONLY | BACKEND_ONLY | Autopilot safety engine preserved; safe native operational monitoring absent |
| F29 | Derivative execution — isolated linear LONG/SHORT, controlled leverage, durable synthetic | BACKEND_ONLY | BACKEND_ONLY | Synthetic derivatives qualification preserved; native venue execution absent/disabled |
| F30 | Live control plane — persistent modes, policy, readiness, operator transitions and kill switch; | FULLY_AVAILABLE | BACKEND_ONLY | Privileged operator control plane intentionally excluded from native client |

## Additional acceptance requirements

| Capability | Status | Gap |
|---|---|---|
| Native identity | ANDROID_IMPLEMENTED | Server session/rotation/revocation and device CRUD paths verified; biometric/hardware/security coverage incomplete |
| Incremental multi-device synchronization | BLOCKED | Cross-entity change feed, cursors, conflicts, snapshot recovery |
| Remote push | EXTERNAL_DEPENDENCY | Delivery account/credentials and registered devices |
| Real-money qualification | BLOCKED | Explicitly unauthorized; not part of mobile authorization |

Verified Android parity: **0 / 31 phase groups (0%)** for complete acceptance. This denominator is phase-level only, not a claim of exhaustive acceptance coverage.

## Verified slices (not full phase parity)

Native login → authenticated API → PostgreSQL/Redis → market candles and watchlist CRUD passed on an API 35 emulator at four viewport configurations. Activity recreation and independent-session revocation are tested separately as recorded in TEST_EVIDENCE.md. API tests cover accounting step-up/idempotency and snapshot cursors. These are mechanical tests on explicitly synthetic fixtures, not production provider/economic qualification. No whole F0–F30 phase has every Android acceptance condition met, so the strict full-phase percentage remains 0%. The implementation contains useful working paths; this percentage must not be reinterpreted as screen-count completion.
