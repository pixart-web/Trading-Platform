# Regime engine — Phase 7

## Scope and boundaries

`RegimeEngine` is a shared Python historical application service over trusted native candle replay.
It produces versioned descriptive trend/volatility classifications and, only when an explicit fitted
model is supplied, research probabilities for the current regime. It does not create future price,
return or horizon forecasts, train implicitly, choose investments, place orders or enable live trading.
No provider, training dataset or pretrained model is shipped. An empty production database remains empty.

One `MarketReplay.replay(query, policy)` call supplies the existing technical kernel with realized
volatility and volume specifications. The full query must pass quality checks. Gaps, future receipts,
staleness and infrastructure errors propagate; an explicit empty closed-session schedule returns ().
The service works with all eight existing timeframes and explicit schedules. It does not combine
probabilities across timeframes or override Phase 6 disagreement. Higher-level callers can consume
these per-timeframe services together; no new HTTP endpoint or frontend is introduced.

Output snapshots are frozen. Each contains a `RegimeObservation` and a `ProbabilityResult`. Evidence
retains the complete technical snapshot: market, timeframe, provider source, candle prefix hash,
input start/count, bar times, reconstructed availability, versions and freshness policy. The regime
specification, efficiency, volatility ratio, classification reason and ordered model vector are kept.
Every calculation uses an isolated 50-digit Decimal/ROUND_HALF_EVEN context; no monetary float
conversion is introduced. JSON serializes Decimals as strings. No schema or dependencies change.

## Descriptive baseline, version 1

`RegimeSpec` defaults to period n=14, baseline period b=50, range efficiency 0.3, trend efficiency
0.6, low volatility ratio 0.67 and high ratio 1.5. These are explicit engineering defaults, not tuned
thresholds or statistically validated trading rules. Periods are 2..500. Require range < trend and
low < 1 < high. Unknown versions, extra fields, nonfinite and invalid parameters are rejected.

For n observed close changes, signed efficiency is:

    (close[i] - close[i-n]) / sum(abs(close[j] - close[j-1]), j=i-n+1..i)

Its magnitude describes the path's directional efficiency, not probability or expected return.
Before n changes, trend is null/WARMUP. With zero path length, efficiency is null/UNDEFINED and
trend is RANGE with FLAT_CLOSES evidence. Otherwise:

| Condition | Descriptive class / reason |
| --- | --- |
| abs(efficiency) >= trend threshold, positive | TREND_UP / EFFICIENT_MOVE |
| abs(efficiency) >= trend threshold, negative | TREND_DOWN / EFFICIENT_MOVE |
| abs(efficiency) <= range threshold | RANGE / LOW_EFFICIENCY |
| Between thresholds | TRANSITION / MIXED_PATH |

Equality is inclusive as shown. TRANSITION means intermediate path efficiency, not the Phase 4
CHOCH state or a probabilistic regime switch. RANGE is a descriptive historical rule, not proof of
future mean reversion. No majority indicator voting or hysteresis is asserted.

Volatility reuses Phase 3's RMS log return over n changes. Compare the current value with the mean
of the previous b ready RMS values; the baseline strictly excludes the current observation. The
first ratio is available at n+b+1 candles. Ratio <= low is LOW, >= high is HIGH, otherwise NORMAL.
A zero baseline is UNDEFINED/ZERO_DENOMINATOR, with null volatility class; insufficient baseline
is WARMUP. Volatility is relative to that timeframe's own history, not annualized or forecast risk.

The probabilistic feature vector has exactly three coordinates:

1. Signed efficiency.
2. RMS log return (same n).
3. log(1 + relative volume), where Phase 3 relative volume compares the current volume with the
   previous n observations. This transform accepts a genuine zero current volume.

A missing coordinate makes the vector unavailable; flat prices or an all-zero volume baseline
are not filled. Bounds [-1,1], [0,100], [0,100] exceed the valid domain's possible log magnitudes
while rejecting malformed extreme vectors. Descriptive volatility baseline warm-up does not block
this vector, since the ratio is not one of its coordinates.

## Availability and causality

Each bar output uses only the input prefix ending at that bar. `technical.available_at` is the
maximum receipt of that prefix, at least its close. An earlier late receipt delays every dependent
observation. No historical import is treated as known before receipt. Consumers must gate on this
availability, not bar-open/pivot dates. Model use adds the temporal conditions described below.
Availability is reconstructed earliest permissible use, not an actual computation/emission log.

Appending or perturbing valid future bars cannot alter an earlier prefix with the same query start,
specification and model. An invalid larger query fails entirely without rewriting separately retained
valid results. Existing replay freshness semantics remain: a finite max_age tests every queried bar
against the replay clock. Historical use may explicitly set max_age=None; that is not live freshness.

## Supervised probability model

`RegimeTrainer(clock).fit(examples, fitted_at=..., label_policy=..., spec=...)` fits a Gaussian naive
Bayes baseline from caller-supplied `TrainingExample` observations and external labels. It does not
use the descriptive rule to label its own training data. Each example retains TRAIN/VALIDATION/
FINAL_HOLDOUT partition and label availability; label availability cannot predate observation
availability. Callers must obtain observations from trusted replay and provide legitimate labels.
Typed records and hashes do not authenticate an external annotation's truth.

Training requires 8..10,000 unique bar-close observations, one market/timeframe/source/RegimeSpec,
all four RegimeLabel classes, and at least `minimum_per_class` samples per class (default 10,
minimum 2). All partitions must be TRAIN. `fitted_at` is aware UTC, no later than the injected clock
and no earlier than every observation and label availability. Missing features, duplicate bars,
class shortages, mixed contexts and future labels fail rather than producing a fallback model.

Within each class, fit per-coordinate mean and population variance (MLE, ddof=0). Variance is
floored at the explicit FitSpec value (default 1e-12, allowed 1e-18..1); this stabilizes constant
features, not a claim of measurement noise. Priors are empirical class counts divided by the total,
without invented class frequencies or probability templates. There is no random fitting step.

`RegimeModel` is a frozen, JSON-serializable RESEARCH artifact. It retains feature and fit specs,
label-policy version, scope, ordered class counts/means/variances, training-through time, latest
training availability, fitted_at and a deterministic SHA-256 dataset hash. `model_hash` fingerprints
all model parameters/metadata, separately from its dataset. Hash encoding sorts JSON keys and uses
canonical Decimal values and UTC-normalized typed timestamps; hashes are not signatures or a
persistent model/dataset registry. No automatic save/load worker is added.

Gaussian inference computes class log posterior up to a common normalizing constant:

    log(count[class] / total) - 0.5 * sum(log(variance[j]) + (x[j]-mean[j])**2 / variance[j])

Subtract the largest log score, exponentiate and normalize. Terms below exp(-1000) are numerically
zero at the published 30-decimal-place probability resolution. Round to that resolution, then
assign the rounding residual to the largest log score (canonical class order breaks exact ties).
Every result retains all four probabilities in canonical order, each in [0,1] and summing exactly
to one. This is a statistical model posterior for the externally labeled CURRENT regime, not a
heuristic score relabeled as probability, not a future-return distribution and not a trade success
probability. Baseline classification and model probabilities can disagree; both remain visible.

The Gaussian conditional-independence formula and its probability-estimation limitations were
checked against the [official scikit-learn Naive Bayes documentation](https://scikit-learn.org/stable/modules/naive_bayes.html#gaussian-naive-bayes).
The implementation uses existing Decimal facilities rather than adding scikit-learn. Coordinate
independence and Gaussian class likelihoods are unvalidated model assumptions here. Correlated
features, overlapping windows and label errors can make posteriors overconfident.

| Probability state | Meaning |
| --- | --- |
| UNAVAILABLE / NO_MODEL | No model supplied; no numbers are invented. |
| UNAVAILABLE / MODEL_NOT_AVAILABLE | Observation availability precedes fitted_at. |
| UNAVAILABLE / TRAINING_OVERLAP | Observation close is at/before trained_through. |
| UNAVAILABLE / FEATURES_UNAVAILABLE | Required feature vector is unavailable. |
| RESEARCH, calibration=UNCALIBRATED | Compatible temporally eligible model posterior, no empirical calibration claim. |

Incompatible source/market/timeframe/spec raises rather than returning a misleading distribution.
The older feature window may include warm-up history from before training end during inference;
the target bar must be strictly later. Evaluation uses stricter window separation below. Stage and
calibration fields cannot be set to PRODUCTION/CALIBRATED. Passing tests cannot promote a model.

## Temporal validation and final holdout

`RegimeEvaluator(clock).evaluate(model, examples, evaluated_at=..., label_policy=...)` accepts
1..10,000 labeled examples from one VALIDATION or FINAL_HOLDOUT partition. It rejects TRAIN,
mixed partitions, duplicates, different label policies, unavailable labels/models and future
assessment times. The entire evaluation input window must begin at/after model.trained_through;
thus its warm-up window cannot overlap the fitted observations. Existing inference checks ensure
its target is later and the model was available at the observation's reconstructed availability.

Reports retain model/dataset hashes, partition, count, class support, evaluation time, accuracy and
multiclass Brier score: mean over observations of sum over four classes of (probability - one_hot)^2.
This convention ranges from 0 to 2, without dividing by class count. Accuracy selects the highest
published probability with canonical-order tie-breaking. Both calculations use Decimal.

These are diagnostics, not calibration, confidence intervals, financial returns or approval for
production. `calibration=NOT_ESTABLISHED` remains explicit. Final holdout records are rejected by
training. Caller must preserve honest partitions and label-policy versions, avoid repeated tuning
against a final report, and perform temporal/walk-forward, multi-asset and economic validation
before promotion. There is no global registry detecting deliberately relabeled copies of data.

## Application usage

Inside a caller-owned read transaction, with a repository, clock and validated CandleQuery:

```python
from pocket_alpha.intelligence.regimes.models import RegimeSpec
from pocket_alpha.intelligence.regimes.service import RegimeEngine
from pocket_alpha.market_data.quality import FreshnessPolicy
from pocket_alpha.market_data.replay import MarketReplay

engine = RegimeEngine(MarketReplay(repository, clock))
snapshots = engine.analyze(query, FreshnessPolicy(max_age=None), RegimeSpec())
# Each snapshot contains observation evidence and NO_MODEL probability status.
# A model trained separately on legitimate TRAIN examples may be supplied explicitly:
# snapshots = engine.analyze(query, policy, fitted_model.feature_spec, fitted_model)
```

TRAIN examples require complete observations plus independently supplied labels and timestamps.
Use RegimeTrainer with an explicit label-policy identifier; never seed test examples into application
data. Serialize returned artifacts using model_dump_json() and validate trusted artifacts with
model_validate_json(). Persisting and managing their lifecycle remains a future registry concern.

## Verification, economics and remaining debt

Synthetic tests cover reference paths/thresholds, rolling-baseline exclusion, flat/zero-volume data,
all timeframes and schedules, standalone technical parity, one replay, empty/rejected data, failure
propagation, late receipts, immutable prefixes, Decimal context, training moments and provenance,
posterior agreement with an independent Gaussian calculation, prior-only and extreme likelihoods,
model/partition/temporal rejection, JSON round trips and independent held-out Brier calculations.
Detailed commands/results are recorded in ../roadmap/PHASE_7_COMPLETION_REPORT.md.

Computational work is bounded by 10,000 queried bars/examples and periods <=500; feature calculation
inherits batch technical-kernel costs, fitting is linear in samples and inference compares four
three-coordinate class likelihoods. No streaming state, persistence, performance claim, real dataset
or calibrated model is introduced. No economic assumptions about zero costs, fills, liquidity,
leverage, drawdown, ruin or profitability are made. Live execution remains prohibited.

Debt includes data providers, sessions/corporate actions, label quality, empirical calibration,
regime persistence/HMM alternatives, cross-timeframe probabilistic models, durable datasets/model
registry, richer temporal/economic evaluation and API/UI consumption. Phase 8 forecast infrastructure
is next and is not implemented by this change.
