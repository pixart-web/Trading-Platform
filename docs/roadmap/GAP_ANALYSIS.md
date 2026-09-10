# Repository gap analysis
Inspection before implementation: clean main, one initial commit, only README.md and .gitignore.
No AGENTS.md, source, tests, migrations, architecture or task files were present. No Git remote.
Implemented before this task: local Git, basic exclusions and generic multi-machine instructions.
Debt: README clone placeholder and absent authenticated remote; no runtime/dependency reproducibility.
Earliest incomplete phase: 0. There is no business implementation or database data to preserve/migrate.

Against directive sections 1–65: all product analysis, market data, portfolios, research and execution
capabilities are absent. Documentation now maps their boundaries and acceptance principles; it is
not a claim of implementation. Phase 0 introduces the backend foundation only.
Universal domain starts with Asset/AssetType, Timeframe, ForecastHorizon, Money and AuditEvent.
Remaining universal domain models arrive with their owning roadmap phase to avoid speculative schemas.
Financial correctness, profitable models, production readiness and live trading remain unproven.
Migration risk: first audit table only, no existing data; downgrade deletes audit history and is for
disposable test databases, never routine production rollback. Service credentials are local examples.
Acceptance: installable Python package, immutable domain values, rejected live flag, durable append
audit, health probes, reversible migration, local Compose, locked dependencies and service CI.
Required checks: Ruff lint/format, strict mypy, pytest, migration generation and real-service CI.
