# ADR 0001 — PostgreSQL and fixture-first historical ingestion
Status: accepted for Phase 1.

Context: Phase 0 already uses PostgreSQL 16 and validated Alembic deployment. Phase 1 must prove
cross-asset identity, precision, quality, database uniqueness and deterministic replay independently
of external outages. A live provider is optional in the directive.

Decision: retain ordinary PostgreSQL tables and a composite candle primary key. Do not add
TimescaleDB hypertables until measured workloads justify operational/migration complexity.
Use only FixtureProvider now and define historical/streaming/metadata ports. Do not add any
network provider, private keys or market orders. Fixture observations exist solely in test helpers.

Consequences: fully deterministic offline tests; actual PostgreSQL integration remains necessary.
No real historical data is automatically available. A future provider task must verify vendor
semantics, calendars, adjusted/unadjusted prices, licenses, pagination and availability timestamps.
Canonical conflicts are rejected, not silently reconciled or overwritten. First receipt is preserved.
Imports are bounded to 10,000 rows and 100 pages, with one transaction and per-row conflict checks.
Batch insertion/streaming, immutable dataset snapshots and explicit corrections are future work.
SQLite exists only for fast unit tests; PostgreSQL validates financial database constraints.
