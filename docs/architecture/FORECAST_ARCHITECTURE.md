# Forecast architecture

Phase 8 implements an append-only forecast ledger. It accepts predictions produced outside this
module; it does not train a model, infer probabilities or generate a forecast. The application
boundary validates a complete forecast before persistence and rejects replacement content under an
existing identity. A later outcome is a separate immutable record with at most one outcome per
forecast. Forecast strategies, portfolio actions, risk, execution and brokers are not connected.

## Time and horizon contract

Candle timeframe describes input sampling. Forecast horizon describes the prediction target and is
stored independently. The supported horizons are 1H, 4H, 8H, 12H, 24H, 2D, 3D, 7D, 14D, 30D,
90D, 6M and 12M. Hour/day values are exact elapsed UTC durations. 6M and 12M use UTC calendar-month
arithmetic and clamp the day at month-end. For example, 31 August 2024 plus 6M expires on 28
February 2025. Exchange-session horizons are not inferred because no authoritative exchange
calendar is available in this phase.

`expires_at` must equal the result of that convention from `generated_at`. All timestamps are
aware and normalized to UTC. A forecast cannot be appended in the future. Evidence availability
must be no later than generation, which prevents later data from entering an earlier snapshot.

## Immutable forecast contract

A forecast records identity, market and asset, candle timeframe, horizon, generation/expiry,
reference price, model/feature/schema versions, model lifecycle stage, dataset hash and one or more
canonical evidence snapshots. Each evidence item retains its kind/version, upstream input hash,
availability time, canonical JSON and verified SHA-256 content hash.

An available forecast requires:

- UP, DOWN and RANGE probabilities in canonical order, summing exactly to one with Decimal
  arithmetic;
- the declared direction to match the largest probability;
- expected return, non-negative expected move, expected return interval and a non-negative
  `range_threshold` used to classify realized direction;
- confidence and an explicit CALIBRATED or UNCALIBRATED label;
- a model version/stage, feature version, dataset hash and causal evidence.

Confidence and probability are stored claims, not profitability and not automatically trusted.
Scores are absent. An unavailable forecast contains an explicit reason and no prediction values,
probabilities, confidence or directional levels. Optional target and invalidation returns must be
provided together and must straddle zero in the declared UP/DOWN direction; RANGE forecasts cannot
carry directional levels.

Persistence stores the complete versioned JSON payload plus indexed identity, market, horizon,
times and model/status columns. Re-appending byte-equivalent domain content is idempotent. Different
content under an existing forecast identity raises a conflict. `ForecastLedger` is the validated
application entry point; `ForecastRepository` is the persistence adapter. Queries are bounded.

## Outcomes and evaluation

An outcome can be recorded only for an available persisted forecast. Its observed end time cannot
precede expiry, its source observation must already be available, and it cannot be recorded in the
future. Reference/end/extreme prices determine actual return and UP/DOWN favorable/adverse
excursions exactly with Decimal arithmetic. RANGE forecasts leave directional excursions null
instead of assigning an artificial favorable side. Directional correctness is derived with the
forecast's immutable range threshold. Target/invalidation flags are allowed only when the forecast
contains levels and must match the observed extrema.

The reference evaluator groups matching forecast/outcome pairs by model version and horizon and
computes multiclass Brier score, expected-return MAE/RMSE, directional accuracy and aggregate
calibration label. It is deterministic and bounded to 10,000 pairs. These are statistical
measurements, not evidence of calibration, economic value or production readiness.

Migration 0003 creates `forecasts` and `forecast_outcomes`, preserving the foreign-key boundary to
market metadata and uniqueness of one outcome per forecast. Upgrade is additive. Downgrade deletes
all forecast and outcome history, so retained data must be exported before rollback.

## Explicit limitations

There is no baseline forecast model, fitting/calibration procedure, outcome collection worker,
exchange calendar, corporate-action adjustment, net expectancy, transaction-cost evaluation,
asset/class/regime/confidence stratification, registry persistence, drift monitoring, API or UI.
Phase 9 owns baseline models and temporal economic validation. Phase 10 owns the explained,
configurable Pocket Score. Neither phase is started here.
