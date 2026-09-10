# Forecast architecture
Forecast horizon differs from candle timeframe. Supported target horizons are 1H, 4H, 8H, 12H,
24H, 2D, 3D, 7D, 14D, 30D, 90D, 6M and 12M. Calendar-month expiry and exchange-session
semantics must be decided and tested in phase 8, not approximated as fixed days.
Forecasts will be immutable snapshots with asset, horizon, direction, up/down/range probabilities,
expected return/move/range, confidence, regime, model version, feature snapshot, generated/expiry
timestamps and reference price. Missing or uncalibrated predictions must be identified honestly.
A separate outcome stores end price, actual return, extrema, favorable/adverse excursion,
realized volatility, target/invalidation hits and directional correctness after expiry.
Evaluate calibration/Brier/error, MAE/RMSE and net expectancy by model/version, asset/class, horizon,
regime, confidence and score bucket. Distinguish error MAE from adverse excursion.
Models begin interpretable; production promotion requires temporal out-of-sample economic evidence.
Registry states: RESEARCH, CHALLENGER, SHADOW, PRODUCTION, DEGRADED, RETIRED.
No forecast generation, probability estimates or outcome worker is implemented in phase 0.
