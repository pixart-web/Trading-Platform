# Validation policy
Use temporal train/validation/final holdout splits; never tune on final test data. Record dataset
hash, availability timestamps, parameters, seed, code/model/feature/cost versions and environment.
Begin with interpretable baselines. Complexity requires improved temporal out-of-sample economics.
Use rolling/walk-forward tests, bootstrap/Monte Carlo, parameter sensitivity and cross-asset/regime
evaluation. Stress fees, slippage, latency, liquidity, missing data and crash gaps.
Event-driven fills must occur only when information and liquidity permit; no impossible same-bar
execution. Account for partial fills, pending orders, spread, fees and rejected orders.
Report net expectancy and compounded growth with drawdown, Sharpe/Sortino/Calmar, profit factor,
turnover, exposure and cost attribution. Include losing periods and unprofitable strategies.
Economic regressions use identified reference datasets; changes are measured, never hidden.
Monitor rolling expectancy, execution drift, feature/regime drift and deviations from expectations;
reduce or suspend using configured degradation limits. Live promotion needs paper/shadow evidence.
The initial Foundation had no economic models, financial modules or market datasets. Subsequent
phases add descriptive intelligence and versioned research infrastructure; this does not establish
profitability or calibrated statistical confidence. Automated tests use clearly synthetic fixtures.
Phase 20 introduces explicit public Coinbase imports and frozen REAL/SYNTHETIC datasets. Economic
research must record dataset identity/hash and economic market/asset/venue/currency identity and may
not silently mix origins. Imported historical prices are available locally at receipt/capture, never
retroactively at candle open. Real-data smoke/replay evidence is not economic validation, survivorship
protection, production readiness or execution authorization.
