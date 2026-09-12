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
