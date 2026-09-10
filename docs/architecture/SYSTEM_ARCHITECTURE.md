# System architecture
Decision: begin with a Python 3.12+ modular monolith, FastAPI, Pydantic 2, SQLAlchemy 2,
Alembic, PostgreSQL and Redis. No microservices: no independent scaling or ownership requirement
exists. PostgreSQL is the durable source of truth; Redis is disposable coordination/cache, never
the financial ledger. Add TimescaleDB only with time-series workloads and measured justification.
Foundation implements domain values, configuration, audit persistence and dependency health.

Planned boundaries: domain; market_data/providers; intelligence (technical, structure, zones,
regimes, fundamentals, derivatives, sentiment, macro); forecasts/scoring/decisions/opportunities;
portfolio; strategies/research/machine_learning; backtesting/simulation/paper_trading; risk/leverage;
execution/brokers/accounting; reporting/monitoring/notifications/audit/security/common.
Create functioning modules as their phase arrives, not empty implementations claiming support.

Next.js/TypeScript charting starts in phase 2. Backend computes analytics; frontend renders them.
Polars/NumPy and justified ML packages arrive with consuming phases. MLflow tracks experiments later.
Docker Compose is local development only; GitHub Actions performs quality and service integration.
JSON logs carry generated correlation IDs. Liveness is process health; readiness requires migrated
database, Redis and successful startup audit. Failed startup audit requires restart after recovery.
Prometheus, Grafana, OpenTelemetry and Sentry are planned observability expansion, not yet installed.
No public deployment/authentication or production credential management is implemented.
