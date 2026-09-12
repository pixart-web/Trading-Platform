# Phase 6 — Multi-timeframe intelligence

## Assessment and implemented scope

User authorized Phase 6. The initial main branch was clean and synchronized. Before production
edits, assessment identified the missing causal cross-frame selection and aggregation contract,
provider/calendar/persistence debt, shared-kernel design, expected files, no migrations and the
acceptance criteria. Only Phase 6 is implemented; Phase 7 is not started.

The shared Python service returns independent technical, structure and zone context for 2..8
native timeframes at one UTC cutoff. It preserves immutable evidence, parameters, freshness,
input hashes and availability. Unanimous resolved structure supplies directional context; all
opposition, neutral/transitional states and unavailable frames remain explicit. Every lower/higher
pair records agreement and opposition without treating indicators or zone strength as votes.

Architecture and usage: ../architecture/MULTI_TIMEFRAME.md. One trusted replay per frame feeds
existing kernels; technical computation was extracted without changing its public interface or
mathematics. No HTTP/frontend, provider, forecast, strategy or execution path was added.
Caller-owned REPEATABLE READ is required for a stable cross-frame database view under concurrent
imports; the service does not claim transaction isolation it does not establish.

## Complete changed-file list

Created:

- src/pocket_alpha/intelligence/multi_timeframe/__init__.py
- src/pocket_alpha/intelligence/multi_timeframe/models.py
- src/pocket_alpha/intelligence/multi_timeframe/service.py
- tests/test_multi_timeframe.py
- docs/architecture/MULTI_TIMEFRAME.md
- docs/roadmap/PHASE_6_COMPLETION_REPORT.md

Modified:

- src/pocket_alpha/intelligence/technical/service.py
- README.md
- docs/architecture/INTELLIGENCE_ARCHITECTURE.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/roadmap/ROADMAP.md

No dependency, schema, migration, CI or frontend files changed. A local .venv was created from
requirements.lock and the project installed editable; environment files are ignored by Git.

## Acceptance and local verification

Python 3.12.14; commands run with .venv/Scripts/python.exe:

- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: passed, 82 files already formatted before this report.
- `python -m mypy .`: passed, 55 source files.
- `python -m pytest --cov=pocket_alpha --cov-report=term-missing`: 291 passed, 73 skipped,
  2 upstream deprecation warnings; 99% overall statement coverage (1,488 statements, 4 missed).
- `python -m pytest tests/test_multi_timeframe.py --cov=pocket_alpha.intelligence.multi_timeframe
  --cov-branch --cov-report=term-missing -q`: 31 passed, 27 PostgreSQL skips; new module 100%
  statement and branch coverage (156 statements, 38 branches).
- `git diff --check`: passed.

Tests demonstrate standalone-engine parity, one replay per frame, all aggregation outcomes,
all eight timeframes, every lower/higher comparison, unresolved retained bias, receipt/close
boundaries, delayed earlier inputs, future append invariance, age based on close time, empty
sessions, missing data, storage failures, mixed-source rejection, UTC normalization, versioned
parameters, resource limits, JSON round-trip and immutability. All fixtures are synthetic and
confined to tests. No existing test was weakened. A new test fixture initially used an invalid
zero low; it was corrected to valid positive prices before the final passing run.

Local PostgreSQL/Redis integration, migrations and Docker builds were not executed: Docker engine
remained unavailable after attempting to start Docker Desktop. Local frontend checks were not run
because no frontend or HTTP contract changed. The existing remote CI includes service integration,
migrations, Docker builds and frontend checks, but has not run against this local implementation.

## Publication status

The user explicitly authorized commit and push to GitHub for work across machines.
Publication branch: codex/phase-6-multi-timeframe. Remote CI results are pending;
no remote success is claimed in this report.

## Migrations, security and financial coverage

No schema migration, data conversion or destructive rollback is required. Existing standalone
analytical APIs preserve behavior; reverting Phase 6 requires code rollback only. Live execution
remains disabled. No credentials, secret logs, external provider, broker, order or withdrawal
capability was added. Data-quality and dependency errors propagate without fabricated analysis.

Causal and Decimal correctness is engineering coverage, not economic evidence. Structural
agreement is neither a calibrated probability nor a recommendation. No profitability, net return,
fill, cost, liquidity, drawdown or ruin estimate is claimed. No assumption of zero trading costs
is made. Those require later independently validated financial models and datasets.

Limitations/debt: real provider and native-resolution availability; sessions/corporate actions;
explicit caller snapshot-age choices; repeatable-read transaction responsibility; query-window
warm-up sensitivity; no cross-provider compatibility policy; no resampling or cross-frame zone
merging; bounded batch computation; no durable dataset/snapshot registry; no API/UI consumption;
empirical economic validation and dependency deprecation maintenance.

Next phase: 7 — regime engine classifications and probabilities. Not started.
