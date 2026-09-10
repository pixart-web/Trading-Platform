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
Foundation has no economic models, financial modules or market datasets; tests use clearly synthetic
domain fixtures only. No profitability, financial coverage or statistical confidence is claimed.
