# Roadmap
Implement one phase per authorized task, in order. Foundation is delivered and published publicly
on GitHub; service integration and Docker build passed CI. See COMPLETION_REPORT.md.
Phase 1 is complete with passing PostgreSQL/Redis CI, migration checks and Docker build;
verification is recorded in PHASE_1_COMPLETION_REPORT.md.
Phase 2 charting is implemented; verification is recorded in PHASE_2_COMPLETION_REPORT.md.
Phase 3 technical intelligence is implemented as the initial five-family feature engine;
scope, catalogue extensions and verification are recorded in PHASE_3_COMPLETION_REPORT.md.
Phase 4 market structure is implemented; conventions and verification are recorded in
PHASE_4_COMPLETION_REPORT.md and ../architecture/MARKET_STRUCTURE.md.
Phase 5 support/resistance zones and overlays are implemented; verification is recorded in
PHASE_5_COMPLETION_REPORT.md and conventions in ../architecture/SUPPORT_RESISTANCE.md.
Phase 6 multi-timeframe analysis is implemented; contracts are in
../architecture/MULTI_TIMEFRAME.md and verification in PHASE_6_COMPLETION_REPORT.md.
Phase 7 regime classification, research probabilities and temporal evaluation are implemented;
see ../architecture/REGIME_ENGINE.md and PHASE_7_COMPLETION_REPORT.md.
Phase 8 immutable forecast and separate outcome infrastructure is implemented; conventions and
verification are recorded in ../architecture/FORECAST_ARCHITECTURE.md and
PHASE_8_COMPLETION_REPORT.md.
All phases after 8 are unimplemented.
0. Foundation — repository, domain base, config, DB, Redis, Docker, CI, audit, testing, logging.
1. Universal market data — assets/providers/history/candles/trades/quotes/quality/replay.
2. Charting foundation — Next.js shell, search, candles, timeframes, volume, API.
3. Technical intelligence — causal versioned indicator features.
4. Market structure — confirmed swings, HH/HL/LH/LL, BOS, CHOCH.
5. Support/resistance — evidence-based zones and chart overlays.
6. Multi-timeframe — separate analyses, aggregation and disagreement.
7. Regime engine — classifications and probabilities.
8. Forecast infrastructure — immutable forecasts, outcomes, horizons, evaluation.
9. Baseline forecast models — calibration, temporal economic evaluation.
10. Pocket Score — configurable explained components.
11. Directional engine — independent LONG/SHORT/NO_TRADE.
12. Opportunity Score — trade/horizon net economic ranking.
13. Analyze — full shared analysis experience.
14. Watchlists — persistence, snapshots, alert events.
15. Scanner — cross-market filters and ranking.
16. Portfolio — manual positions, accounting and dashboard.
17. Portfolio intelligence — correlations, concentration and allocation.
18. Fundamentals — providers, financials, valuation.
19. Derivatives intelligence — positioning and volatility context.
20. Sentiment/news/macro — validated contextual features.
21. Backtesting — realistic causal event-driven simulation.
22. Research factory — experiments, registry, reproducibility.
23. Paper trading — live data, simulated execution.
24. Strategies — validated lifecycle and portfolio.
25. Leverage research — liquidation and stress.
26. Live read-only — balances, positions and reconciliation.
27. Live small — explicitly configured strict spot limits.
28. Autopilot — scanning, allocation, monitoring and compounding.
29. Derivative execution — independently validated SHORT and controlled leverage.
