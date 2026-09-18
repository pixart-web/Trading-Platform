# System architecture
Decision: begin with a Python 3.12+ modular monolith, FastAPI, Pydantic 2, SQLAlchemy 2,
Alembic, PostgreSQL and Redis. No microservices: no independent scaling or ownership requirement
exists. PostgreSQL is the durable source of truth; Redis is disposable coordination/cache, never
the financial ledger. Add TimescaleDB only with time-series workloads and measured justification.
Foundation implements domain values, configuration, audit persistence and dependency health.

Phase 1 adds the universal market-data domain, provider ports, fixture adapter, validated atomic
historical ingestion, canonical candle storage and deterministic replay. See
[Market data architecture](MARKET_DATA_ARCHITECTURE.md) and
[ADR 0001](ADR_0001_MARKET_STORAGE_AND_PROVIDERS.md) for identity, quality and storage contracts.

Planned boundaries: domain; market_data/providers; intelligence (technical, structure, zones,
regimes, fundamentals, derivatives, sentiment, macro); forecasts/scoring/decisions/opportunities;
portfolio; strategies/research/machine_learning; backtesting/simulation/paper_trading; risk/leverage;
execution/brokers/accounting; reporting/monitoring/notifications/audit/security/common.
Create functioning modules as their phase arrives, not empty implementations claiming support.

Next.js/TypeScript charting is implemented in phase 2 (frontend/). Backend computes analytics;
frontend renders them. See CHARTING_ARCHITECTURE.md for the read-only gateway and chart contracts.
Polars/NumPy and justified ML packages arrive with consuming phases. MLflow tracks experiments later.
Phase 3 adds intelligence/technical as a shared historical application service over trusted replay.
It uses standard-library Decimal, with no new dependencies or persistence. See TECHNICAL_INTELLIGENCE.md.
Phase 4 adds intelligence/structure over the same trusted replay and a shared provenance encoder.
See MARKET_STRUCTURE.md; no new persistence, API, frontend or execution dependency is introduced.
Phase 5 adds intelligence/zones, a read-only atomic candles/zones endpoint and optional chart bands.
It reuses structure and provenance; no new persistence or dependencies. See SUPPORT_RESISTANCE.md.
Docker Compose is local development only; GitHub Actions performs quality and service integration.
JSON logs carry generated correlation IDs. Liveness is process health; readiness requires migrated
database, Redis and successful startup audit. Failed startup audit requires restart after recovery.
Prometheus, Grafana, OpenTelemetry and Sentry are planned observability expansion, not yet installed.
No public deployment/authentication or production credential management is implemented.

Phase 6 adds intelligence/multi_timeframe: independent native-resolution analyses at one causal
cutoff, unanimous structural context, explicit disagreement and higher-timeframe opposition.
It reuses the existing kernels after one trusted replay per frame, with explicit freshness and
unavailable states. No persistence, HTTP, UI or execution dependency is added. See MULTI_TIMEFRAME.md.

Phase 7 adds intelligence/regimes over trusted replay and the shared technical kernel. Descriptive
trend/volatility rules and explicitly fitted Gaussian research posteriors retain causal evidence;
temporal evaluation rejects training/holdout overlap. Probabilities remain uncalibrated and absent
without a model. No forecasts, persistence, API/UI or execution path. See REGIME_ENGINE.md.

Phase 8 adds forecasts as the next boundary after intelligence: a validated append-only ledger of
externally produced immutable forecast snapshots, followed later by separate observed outcomes and
deterministic reference evaluation. Migration 0003 persists both records; no model generation,
score, decision, strategy, risk, execution, broker, HTTP or UI path is added. See
FORECAST_ARCHITECTURE.md.

Phase 9 adds an in-memory research producer after the forecast boundary: deterministic Gaussian
direction baselines, separate temporal temperature calibration and cost-aware held-out evaluation.
It emits Phase 8 forecast values and cannot reach strategy, portfolio, risk, execution or broker
modules. No persistence, migration, endpoint, frontend or dependency is added. See
BASELINE_FORECAST_MODELS.md.

Phase 10 adds the scoring boundary as an in-memory deterministic module after forecasts. It combines
versioned normalized evidence using an explicit configuration and fails closed when required inputs
or configured coverage are missing. No persistence, endpoint, frontend, strategy, risk, execution
or broker dependency is added. See POCKET_SCORE.md.

Phase 11 adds directional as an in-memory deterministic boundary after forecasts/scoring and before
strategy. LONG and SHORT use separate explicit criteria; NO_TRADE is fail-closed for conflict,
failure or incomplete evidence. No persistence, endpoint, frontend, strategy, risk, execution or
broker dependency is added. See DIRECTIONAL_ANALYSIS.md.


Phase 12 adds opportunities as an in-memory deterministic consumer of immutable forecasts and
Phase 11 directional analysis. It exposes net economics, configured gates and same-horizon ranking
without adding persistence, an endpoint, frontend, strategy, portfolio, risk, execution or broker
dependency. See OPPORTUNITY_SCORE.md.

Phase 13 adds the analysis read-model boundary, append-only Analyze report persistence, a read-only
FastAPI route and its validated Next.js presentation. The report composes existing artifacts for all
thirteen horizons and never creates a strategy, portfolio, risk, execution or broker dependency.
Migration 0004 is additive. See ANALYZE.md.

Phase 14 adds the watchlist application boundary over registered markets and stored Analyze reports.
Mutable lists use optimistic revisions; snapshots and transition events are append-only and preserve
exact as-of identity. Migration 0005 is additive. No scanner, strategy, portfolio, risk, execution or
broker dependency is introduced. See WATCHLISTS.md.

Phase 15 adds the scanner application/read-model boundary over registered markets and exact stored
Analyze reports. It filters existing Opportunity Scores and ranks them only within identical policy
version/hash groups. Migration 0006 is additive. No strategy, portfolio, risk, leverage, execution or
broker dependency is introduced. See SCANNER.md.

Phase 16 implements the portfolio boundary as a persistent manual accounting ledger. It consumes
registered market identity and causal stored candle closes for valuation, but does not consume scans,
create strategy intentions, approve risk or reach leverage, execution or broker modules. Migration
0007 is additive. See PORTFOLIO.md.

Phase 17 adds a portfolio-intelligence read-model boundary over Phase 16 snapshots and causal stored
candles. Versioned immutable reports explain allocation, concentration and supported historical risk
metrics while retaining explicit unavailable states. Migration 0008 is additive. See
PORTFOLIO_INTELLIGENCE.md.

Phase 18 adds provider-independent immutable corporate facts, conservative point-in-time SEC
ingestion and descriptive financial context. Migration 0009 and read-only asset endpoints preserve
publication/availability/ingestion and revisions. No strategy, risk approval, execution or broker
dependency is introduced. See FUNDAMENTALS.md for coverage and unavailable metrics.

Phase 19 adds precise immutable derivative contract identity and causal observations, with descriptive
funding, open interest, basis, reported option volatility/Greeks, aligned futures curves and explicit
option skew. Migration 0010 and GET-only endpoints add no execution/risk/broker dependency.
See DERIVATIVES_INTELLIGENCE.md for units, unavailable states and provider/financial limitations.

Phase 20 adds a shared causal context boundary for news and explicit normalized sentiment/macro,
GET-only context snapshots, a public Coinbase historical adapter and frozen REAL/SYNTHETIC datasets.
Migration 0011 is additive. Explicit network imports never run at startup and add no strategy, risk
approval, leverage, execution or broker dependency. See CONTEXTUAL_INTELLIGENCE.md and
REAL_MARKET_DATA.md for provenance, economic identity, conservative availability and limitations.

## Phase 21 offline research

Phase 21 adds an offline backtesting module to the modular monolith. It reuses shared technical intelligence and immutable forecasts, validates causal risk approval before simulated execution, and exposes immutable read-only reports. See [BACKTESTING.md](BACKTESTING.md). No broker connection or live readiness is introduced.
