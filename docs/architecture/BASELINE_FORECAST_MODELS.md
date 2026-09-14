# Baseline forecast models

Phase 9 adds a deterministic, interpretable research baseline after the immutable Phase 8 forecast
ledger. It does not create an API, persist model artifacts, select trades or connect to a strategy,
portfolio, risk, execution or broker boundary. Live execution remains disabled.

## Temporal dataset contract

Each labeled example contains the observation known at forecast generation, a separately available
realized return, its outcome hash and exactly one partition: TRAIN, CALIBRATION, VALIDATION or
FINAL_HOLDOUT. The observation fixes market, asset, candle timeframe, forecast horizon, input start,
generation and expiry, reference price, named feature version/vector and causal evidence snapshots.

Training accepts TRAIN only. Calibration accepts a strictly later CALIBRATION partition and
evaluation accepts VALIDATION or FINAL_HOLDOUT only. Outcomes must be available by the fit or
evaluation timestamp. Calibration inputs cannot overlap training targets; evaluation inputs cannot
overlap fitted training or calibration targets. Economic compounding rejects overlapping forecast
periods. The final holdout is evaluated by the same frozen path and is never used to select the
model, feature set, threshold, temperature or costs.

## Interpretable baseline and artifact identity

BaselineForecastTrainer fits a three-class Gaussian naive Bayes model for UP, DOWN and RANGE. The
configured return threshold defines those classes. Each class artifact retains its sample count,
per-feature mean and variance, empirical return mean, mean absolute return and empirical interval. A
variance floor prevents division by zero. The implementation is deterministic and has no random
operation, represented by random_seed: null.

The immutable model artifact retains the complete parameter specification, model/schema/code/
environment/feature versions, dataset hash, market/horizon/timeframe identity, training cutoff,
outcome-availability cutoff and fit time. All published numeric values use Decimal; timestamps are
aware UTC values. Predictions use the Phase 8 Forecast contract, remain in RESEARCH stage and retain
the original causal evidence. Equal top probabilities fail closed as unavailable.

## Calibration

TemperatureCalibrator evaluates a declared, ordered candidate grid that must include temperature
one. It minimizes multiclass Brier score on the separate calibration partition, with deterministic
tie breaking toward no change. The artifact records raw and selected Brier scores, candidate grid,
sample count, dataset/model hashes and temporal cutoffs. Because one is always a candidate, the
selected fitting score cannot be worse than the raw score. CALIBRATED identifies that the
transformation was applied; it is not a claim that probabilities are accurate on unseen or real
market data.

## Temporal economic diagnostics

BaselineForecastEvaluator emits statistical diagnostics and a deliberately simple economic
reference:

- one unit of exposure for UP and one unit of short exposure for DOWN;
- no exposure for RANGE;
- realized return for long and negated realized return for short;
- explicit round-trip fee, spread, slippage and latency assumptions in basis points;
- sequential compounding over non-overlapping periods, with ruin recorded when a net period is at
  or below -100%;
- Brier score, return MAE/RMSE, directional accuracy, gross/net expectancy, compounded net return,
  maximum drawdown, profit factor, unannualized per-period Sharpe/Sortino/Calmar diagnostics, active
  fraction, round-trip turnover, total costs, losing periods and observed ruin.

The evaluation artifact retains the full cost specification, dataset/model/calibration hashes and
partition. The reference ignores sizing, liquidity capacity, partial fills, funding, borrow,
corporate actions and exchange calendars. Its values cannot establish deployable profitability.

## Limits and next boundary

Tests use clearly synthetic fixtures. No trained artifact or research dataset is shipped, and no
claim is made about accuracy, calibration, confidence, profitability, statistical significance or
financial coverage. Walk-forward orchestration, bootstrap/Monte Carlo, cross-asset and regime
stratification, stress suites, registry persistence, drift monitoring and outcome collection remain
research work. Phase 10 adds the separate configurable, explained aggregation described in
[Pocket Score](POCKET_SCORE.md). Phase 11 directional analysis is implemented in [Directional analysis](DIRECTIONAL_ANALYSIS.md).
