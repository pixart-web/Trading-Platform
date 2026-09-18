# Phase 24 completion report

## Assessment, design and acceptance

Phase 24 implements versioned strategy definitions, explained immutable proposals, portfolio sizing,
canonical checkpoints, evidence-linked lifecycle and read-only metadata. The initial supported family
is SMA_TREND_SPOT_LONG; other strategy families are not implemented. The clean preserved Phase 23
baseline is 063ebbbacaf224b5a8bcefcea4b99716d7a4d9f9. Work is isolated on codex/phase-24-strategies.
Phase 25 is next and is not started; no push/main merge or deployment is performed.

Before production edits the assessment declared missing strategy/proposal/lifecycle contracts,
additive migration 0015, shared upstream directional analysis, portfolio allocation before existing
risk and no broker imports. Existing PostgreSQL/Redis integration and execution calibration debt
was retained. Acceptance requires fail-closed missing/future/incompatible evidence, explicit
version/timeframe/horizon/invalidation/provenance, deterministic proposals/checkpoints, cash/exposure/
notional limits, actual prior risk approval for simulated fills, qualified REAL OOS promotions,
causal PAPER/final-holdout binding and permanently disabled LIVE/SHORT/leverage.

## Architecture and financial coverage

See ../architecture/STRATEGIES.md for precise contracts and orchestration. Shared SMA features and
immutable compatible forecasts feed the existing independent LONG/SHORT/NO_TRADE engine. Explained
proposals have no order quantity or broker authority. StrategyAdapter applies portfolio buffers,
exposure/notional caps, worst-cost cash reservation and shared step/minimums; existing simulation
risk independently approves every submitted BUY/SELL. Model return must exceed modeled round-trip
costs plus an explicit margin, without treating scores as probabilities or model estimates as profit.
Private Decimal context, UTC causality, observed-fill stop/expiry, partial-entry cancellation and
checkpoint identity are tested. Bar-close invalidation is not an intrabar guaranteed stop.

StrategyRegistry validates market/source identity and immutable version/hash registration, revision/
CAS, append-only audit chains, sealed matching model evidence and Phase 22 economic gates. CANDIDATE
requires REAL OOS; PAPER binds exact qualified run/source/account/state; SHADOW additionally requires
one-shot final holdout and completed PAPER net return/expectancy/maximum observed drawdown evidence.
Policy/model/account promotion bindings are frozen. Degradation/suspension permits retirement only;
new qualification requires a new version. Historical evidence remains auditable after degradation.

RegisteredStrategyAdapter checks operational lifecycle/model/config before PAPER market execution.
Failure or exception journals a disconnect and cancels pending orders before they can fill; historical
replay uses recorded decisions rather than today's lifecycle. Explicit disconnect reasons survive
stale-feed checks. Native polling stops if the candle cursor cannot advance. Read-only no-store API
returns sanitized dependency/corruption failures, with no HTTP mutation or execution routes.

Synthetic fixtures and explicitly identified qualification/runtime mocks verify contract branches;
they are not financial evidence. No new real OOS experiment or qualified strategy is produced, and
no profitability, calibration, production readiness or live eligibility is claimed. Actual native
market provenance alone cannot authorize strategy promotion. No dependency, credential, private
broker access, withdrawal or automatic worker is added; LIVE remains false and database-blocked.

## Migration and verification

0015 follows 0014 and adds strategy_registry/strategy_events with market-version uniqueness, event
FK and no-live CHECK. Existing records are unchanged. Full SQLite upgrade 0001–0015 creates 36 tables;
downgrade removes only the two new tables and preserves all 34 previous tables. The isolated migration
regression also covers no-live/uniqueness/FK and unrelated-row preservation. Export strategy records
before downgrade; they will be deleted. Alembic heads reports 0015 (head).

Verification before final repetition:

- `.venv/Scripts/ruff.exe check .`: all checks passed.
- `.venv/Scripts/ruff.exe format --check .`: 283 files already formatted.
- `.venv/Scripts/python.exe -m mypy`: success, 203 source files checked.
- Focused strategies/registry/migration: 61 passed, 35 PostgreSQL skips, 2 dependency warnings in 18.73s.
- First full branch-coverage run: 694 passed, 228 integration skips, 2 dependency warnings in 201.06s.
  Combined strategy statement/branch coverage was 88%; the subsequent audit adds run/history/model
  causal guards and additional schema/lifecycle/recovered-drawdown regressions.
- Programmatic Alembic ScriptDirectory/Operations full SQLite upgrade/downgrade: 36/34 tables,
  prior schema preserved. `.venv/Scripts/alembic.exe heads`: 0015 (head).
- `git diff --check`: passed (only repository CRLF normalization notices).

Final audited verification:

- `.venv/Scripts/python.exe -m pytest --cov=pocket_alpha.strategies --cov-branch --cov-report=term-missing -q`:
  **702 passed, 231 skipped, 2 dependency deprecation warnings in 220.11s**. Skips are unconfigured
  PostgreSQL/Redis integration; no integration result is invented. Two warnings are existing
  Starlette/httpx TestClient and anyio BlockingPortal deprecations.
- Strategy combined statement/branch coverage: **96%** (519 statements, 14 missed, 172 branches,
  15 partial). API 100%, schemas 100%, evaluator/allocation 98%, registry 93%.
  Remaining branches include defensive unavailable model/account/plan/holdout cases, malformed audit
  identities/source registration and unreachable-by-valid-schema allocation guards. Coverage includes
  explicit qualification/runtime mocks; it is not empirical economic validation.
- Final Ruff check passed, Ruff format check reported 283 files already formatted; mypy checked
  203 source files successfully. The added two-entry mock journal required a variadic tuple annotation;
  the final complete suite includes this correction.
- Final staged diff check passed; all 20 changed files are listed below. Documentation UTF-8 checked.

Implementation meets the documented local mechanical acceptance scope. Real financial qualification
and production service/migration readiness remain explicitly unverified. Frontend checks are not rerun because
this phase changes no frontend files or contracts consumed by the existing frontend. PostgreSQL and
Redis integration are not configured/executed locally; SQLite does not certify production migration.
No test or CI submits a real order. The two existing dependency deprecation warnings remain.

## Self-audit, corrections and debt

Initial targeted tests exposed duplicate synthetic forecast UUIDs: the fixture now uses deterministic
timestamp-specific IDs. A later guard regression exposed STALE_FEED overwriting an explicit lifecycle
disconnect reason; the runtime preserves explicit disconnects while still evaluating risk. Valid
financial assertions and existing tests were retained. Audit added partial-entry cancellation,
private allocation context and exact experiment/run/history binding rather than silently accepting
changed settings. An unintended roadmap encoding change was corrected before finalization.

Remaining debt: additional strategy families, genuine causal model/OOS/holdout/PAPER qualification,
provider/execution cost and stop calibration, multi-market/account portfolio aggregation, PostgreSQL/
Redis integration, measured large-history revalidation performance, and a dedicated strategy UI.
These are documented limits, not fabricated implementations. Phase 25 leverage research remains next;
this phase cannot enable leverage, derivative execution or live trading.

## Complete changed-file list

- `README.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/STRATEGIES.md`
- `docs/roadmap/PHASE_24_COMPLETION_REPORT.md`
- `docs/roadmap/ROADMAP.md`
- `migrations/env.py`
- `migrations/versions/0015_strategies.py`
- `src/pocket_alpha/main.py`
- `src/pocket_alpha/paper_trading/engine.py`
- `src/pocket_alpha/paper_trading/feed.py`
- `src/pocket_alpha/paper_trading/service.py`
- `src/pocket_alpha/strategies/__init__.py`
- `src/pocket_alpha/strategies/api.py`
- `src/pocket_alpha/strategies/engine.py`
- `src/pocket_alpha/strategies/models.py`
- `src/pocket_alpha/strategies/registry.py`
- `tests/strategy_fixtures.py`
- `tests/test_strategies.py`
- `tests/test_strategy_migration.py`
- `tests/test_strategy_registry.py`

The phase is recorded in a local `feat: implement phase 24 versioned strategies` commit on
`codex/phase-24-strategies`; its SHA is reported to the user after creation. No push/main merge.
