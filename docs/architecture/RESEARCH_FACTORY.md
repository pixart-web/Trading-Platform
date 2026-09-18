# Research factory

Phase 22 adds offline experiment orchestration and model evidence to the Python modular
monolith. It reuses Phase 21 Backtester, Decimal accounting, shared technical intelligence
and the immutable forecast/outcome ledger. It adds no broker interface, paper trading,
production execution, leverage or strategy family. Existing crypto spot LONG limitations,
complete future-bar CLOSE execution and unvalidated cost assumptions remain applicable.

## Plans, training and evaluation

StudyPlan is immutable and content-addressed. It declares version/rationale, frozen dataset
UUIDs/hashes, one origin, distinct native assets, variants with parameters/model/feature/code/
environment identities, baseline, cost stress, horizon labels, regime segment provenance,
maximum label horizon, embargo, matrix budget, analysis policy/seed and final reserve.
Train/validation/test windows are ordered. Walk-forward expands from one start; rolling
advances a fixed training width. Test windows do not overlap. Embargo must cover every
variant horizon under calendar expiry conventions. Final holdout follows all tests.
Temporal helpers construct folds, but callers must explicitly approve the research design.
Parameter variants and cost scenarios are declared before results; all are reported.
No optimizer, automated winner selection or corrected statistical significance is claimed.

Window subsets require complete aligned candle coverage and original receipts no later
than their cutoff. UUIDs derive from parent UUID and immutable subset hash. Original source
receipts and captured_at remain unchanged. Historical downloads cannot masquerade as known
past data. Future revisions or missing observations fail instead of producing fallback data.
ResearchFactory.fit receives training data only and returns bounded canonical JSON.
Its fitted artifact/hash is persisted. materialize creates a new callback for each independent
flat-start evaluation window; strategies are never reused with a previous portfolio state.
All model fitting and callback code is trusted Python, not a security sandbox. Callers must
make their fitted state complete, deterministic and versioned. The factory never receives
test/final data through fit. Training labels/features are the provider's responsibility and
must satisfy the existing temporal policies; this phase adds no new predictive algorithm.

Every source/fold/variant executes validation and test. Research Trial.partition is the
authoritative split annotation; validation/test/regime use the existing engine VALIDATION
configuration, while the protected final run uses FINAL_HOLDOUT. Declared causal regime segments get
separate independent-window runs, not attribution of a continuous portfolio. Native crypto
assets are evaluated independently; currencies and portfolio returns are not aggregated.
Horizon is distinct from candle timeframe and is passed to the research factory. Report
labels cannot establish forecast-horizon validity of arbitrary third-party callbacks.
Losses, rejected orders and unavailable metrics are preserved. Dependency/fitting failure
rolls back incomplete experiment artifacts; no completed report or ready state is invented.

## Robustness, calibration and drift

Each trial includes Phase 21 net economics and fixed-seed moving-block bootstrap terminal
return quantiles plus shuffled-return Monte Carlo drawdown quantiles. Block length, sample
minimum, simulation count and quantile bounds are explicit. Samples must be sufficiently
large, regular and nonzero at return denominators. These empirical scenarios assume a
stationary/exchangeable return history; they are not confidence intervals, independent
strategy reruns, calibrated ruin probabilities or evidence that a strategy is profitable.
Mean and standardized mean shifts compare training and evaluation close returns. Zero
reference variance is unavailable. The reusable drift helper also accepts finite feature
samples, but no live drift monitor or automated trading suspension is implemented here.

Optional predeclared calibration forecast IDs load full matching ledger forecasts/outcomes.
Reports freeze both and compute Brier score and aggregate top-label calibration gap using
the shared financial outcome validator. Inputs must match study assets/model/horizon,
come from validation/test, mature before the final reserve and be known at evaluation.
Missing outcomes fail not ready. Undeclared calibration is unavailable, not guessed.
Descriptive calibration diagnostics neither fit a calibration model nor grant confidence.
Multiple testing is explicit: report declared matrix size and preserve all trials. No
p-values, false-discovery correction, calibrated confidence or probability of backtest
overfitting is fabricated; the registry policy does not imply statistical significance.

## Protected final holdout

Public Backtester.run continues rejecting FINAL_HOLDOUT. consume_final owns independent
SQLAlchemy Engine transactions and requires committed complete experiments. The selected
variant, experiment hash and plan hash are frozen in a durable consumption record before
any callback evaluates final data. Fitted artifacts come from the last fold's sealed test
trial; fit is not called again. The selected strategy is materialized once per asset.
The internal backtester entry is a trusted research implementation detail, not a public
permission to execute real orders or an adversarial sandbox.

The consumption primary key is the conservative asset-type/native-symbol economic key,
shared across source UUIDs, aliases and venues. A symbol can have one final consumption in
this registry; renamed studies cannot obtain another attempt. Claims for all assets commit
atomically. Failed final materialization/execution retains consumption and forbids retries.
A successful final report can be read repeatedly, but cannot be rerun. This conservative
rule needs independent governance before any future fresh holdout campaign; there is no
reset API. Immutable evidence reload checks plan/source/backtests/diagnostics, consumption
and the frozen fitted artifact. Administrative DB edits or raw/private Python access are
outside the trusted application governance boundary.

## Model registry and operational limits

The registry stores an immutable model-version/fitted-artifact bundle tied to experiments
and a selected variant. Revision-checked transitions append hash-linked UTC evidence. Registration and promotion
cannot predate their evidence; baseline differences use the fixed Decimal precision 80.
RESEARCH -> CHALLENGER requires REAL out-of-sample experiments, explicit positive net-return
and closed-trade expectancy thresholds, sample/asset/fold minimums, drawdown/bankruptcy checks,
optional required cost stresses and positive baseline improvement for added complexity.
CHALLENGER -> SHADOW additionally requires the one-shot final report for the same selection.
SHADOW is a research qualification label; it starts no shadow trading process.
DEGRADED/RETIRED transitions retain reasons and evidence; retired is terminal. PRODUCTION is
represented by the shared stage enum but cannot be entered in this foundation. Strategy
PAPER/LIVE states and operational promotions belong to later phases. No in-sample or synthetic
promotion is possible through the factory registry. No observed real strategy qualification
is claimed by this delivery. Thresholds must be explicitly supplied, not invented defaults.

GET /api/v1/research/reports/{report_id} and /models/{artifact_id} are read-only, no-store,
with generic dependency/corruption errors. There are no HTTP run/promotion/reset endpoints.
Migration 0013 adds five tables: studies, reports, holdout consumption, registry heads and
registry events. Export all evidence and consumption records before rollback. Downgrade
removes these tables; recreating an empty registry invalidates one-use holdout governance.
PostgreSQL integration/concurrency remains to be verified; local SQLite checks do not claim
production readiness. Hashes detect corruption, not authenticated hostile replacement.
Live remains Literal[False], no credentials or withdrawal rights are added, and no CI/test
can issue real orders. Phase 23 is not started.
