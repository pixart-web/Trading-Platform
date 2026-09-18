# Phase 25 completion report

## Summary, assessment and acceptance

Phase 25 adds the independent offline leverage-risk research boundary: immutable versioned inputs,
conditional linear isolated liquidation, stop/collateral/cost/loss assessment and all six explicit
survival stress families. Clean preserved Phase 24 baseline: 75ed1154294cbd736a8dae46fab87dffcfa13067.
Branch: codex/phase-25-leverage-research. No existing uncommitted changes were present.

Before production edits the assessment identified absent leverage research, retained missing genuine
derivative/venue validation and service integration debt, and declared leverage/models.py,
leverage/engine.py, synthetic tests and architecture/policy/roadmap documentation. No migration,
API, UI or execution change was planned. Acceptance: Decimal/UTC, contract/proposal/portfolio/risk
binding and causality, fail-closed missing/incompatible inputs, transparent costs/gap/collateral
deficits, deterministic immutable assessments, no invented ruin probability and no execution grants.

## Architecture, financial coverage and assumptions

See ../architecture/LEVERAGE_RESEARCH.md for usage, exact independently derived equations and full
limitations. The only implemented model is LINEAR_ISOLATED_MARK_NOTIONAL_1: perpetual/dated-future
cash settlement, base-unit multiplier, same quote/settlement/index currency, ISOLATED margin and
one explicitly bounded flat maintenance-rate tier. It is not a supported live venue implementation.
Options, inverse/cross/portfolio/physical margin, currency conversion, horizon expiry and dynamic
tier extrapolation reject. Venue documentation informs the scope, without claiming to implement
its actual rules.

The request retains complete Phase 19 contract, versioned upstream position hash, explicit leverage,
contracts/entry/stop/timeframe/horizon, available collateral/equity, matching prior offline risk
attestation, margin rules, horizon-normalized volatility and transaction/funding assumptions.
Caller hashes/origin labels are provenance assertions, not authenticated financial evidence or
order approval. No confidence, Pocket Score, Opportunity Score or probability determines leverage.
Missing/future/stale/mixed-origin/mismatched/failed/expired inputs reject with absent numerical
metrics; structurally invalid schemas reject before evaluation. Generated reports use actual Clock.

Private Decimal 160-digit context protects bounded monetary products and context-independent ratio
calculations. Linear LONG/SHORT roots solve isolated equity equal to mark maintenance plus closing/
liquidation reserve. Fees/spread/slippage and horizon funding consume declared isolated allocation.
Initial margin, notional/collateral budgets, stop-to-liquidation buffers and tier ceiling apply.
Baseline expected costs refer to assumed transaction costs at the declared stop, not empirical
expectancy. All rates, risk bands, input ages and scenario severities are explicit policy inputs;
none is a recommended production threshold.

Gap, volatility, forced liquidation, slippage, funding and other-holding correlated-loss scenarios
record modeled prices, costs, funding, position/combined losses, deficits, projected equity and ruin/
tier flags. Forced liquidation uses a fixed gross-margin-loss distance (1/leverage) plus declared
gap overshoot, so higher costs do not artificially relax scenario severity. No fill is fabricated
at the modeled liquidation threshold and no insurer/ADL/liability cap is presumed. LONG prices
floor at zero; SHORT losses can exceed collateral. Dated futures reject funding and explicitly use
a zero/not-applicable funding scenario. Dynamic funding paths/carry are unsupported.

Maximum modeled loss means the largest baseline/declared combined scenario loss, not a guarantee
across all future paths. A projected-insolvency scenario is descriptive; ruin_probability is always
null. ACCEPTABLE/ELEVATED/HIGH_RISK/REJECTED are configured research classifications. Every output
retains RESEARCH_ONLY, execution_authorized=false and live_ready=false, with full request, deterministic
UUID and input/content hashes. Hash/time/identity/status validation is not a cryptographic signature
or independent recomputation of a forged report.

## Tests, commands and results

- `.venv/Scripts/ruff.exe check .`: all checks passed.
- `.venv/Scripts/ruff.exe format --check .`: 288 files already formatted.
- `.venv/Scripts/python.exe -m mypy`: success, 208 source files checked.
- `.venv/Scripts/python.exe -m pytest tests/test_leverage.py --cov=pocket_alpha.leverage --cov-branch --cov-report=term-missing -q`:
  81 passed, 2 existing dependency deprecation warnings in 5.43s. Combined statement/branch coverage
  99%; the final full suite additionally checks canonical UTC validation of generation time.
- `.venv/Scripts/alembic.exe heads`: 0015 (head), unchanged.
- `git diff --check`: passed (only normal repository CRLF notices).

Final complete backend verification:

- `.venv/Scripts/python.exe -m pytest --cov=pocket_alpha.leverage --cov-branch --cov-report=term-missing -q`:
  **783 passed, 231 skipped, 2 warnings in 365.87s**. Skips are unconfigured PostgreSQL/Redis
  integration. Warnings are the existing Starlette/httpx TestClient and anyio BlockingPortal
  dependency deprecations.
- Combined leverage statement/branch coverage **99%**: 367 statements, 1 missed, 104 branches,
  1 partial. Models 100%, engine 99%. The sole remaining defensive reserve-rate guard is inside
  the private liquidation helper; public input validation rejects that condition before evaluation.
- Final Ruff/mypy/diff checks passed as reported above. All 13 changed files and UTF-8 checked.

Implementation passes the documented local mechanical acceptance scope. Genuine financial/venue
qualification and production infrastructure readiness remain unverified. Tests include independent LONG/SHORT equity
and loss/cost accounting oracles, exact stop fees, all six stress families, origin/causal/horizon/
contract/risk binding, stops, leverage/margin limits, collateral allocation, tier scope, funding,
zero-price/1x boundary, portfolio insolvency/deficits, status bands, context independence, idempotent
hashes/IDs, schema corruption and permanently unavailable execution/probability fields. Monotonic
cost/volatility shock regressions and import-boundary checks supplement existing spot/PAPER tests.
All fixtures are explicitly synthetic; no actual venue liquidation, profitability or financial
qualification is demonstrated. No test or CI submits a real order.

## Migration, integration and security

No schema, durable records, dependencies, API routes, frontend contracts or execution paths change.
No migration is needed; upgrade/downgrade checks are not repeated because Phase 25 has no DDL changes.
PostgreSQL/Redis service integration is unconfigured locally and its tests remain skipped. Frontend
lint/typecheck/unit/build/E2E are not run because no frontend or consumed API contract changes.
No production migration or service-readiness result is inferred from these skips.


Adding Python modules changes the existing global source-tree hash. Previous PAPER accounts remain
readable/replayable, but their readiness becomes RUNTIME_IDENTITY_CHANGED and new processing refuses
the old runtime identity. No header/checkpoint/model proof is rewritten to bypass this safety guard;
continued research needs a new current-identity run/account and matching qualification. This is a
compatibility consequence, not a database migration or newly authorized execution route.

No broker, secrets, withdrawals, account transfers or network/provider ingestion is introduced.
The leverage module cannot import strategy/PAPER/simulation/execution/broker routes. Existing risk
approval remains mandatory for every simulated BUY/SELL; no leverage research verdict enters that
path. Live remains disabled and unsupported derivative executions remain unreachable.

## Self-audit, corrections, debt and next phase

Initial focused verification reported 4 failed/68 passed: arithmetic oracle used the global Decimal
precision, an expired-risk fixture was structurally invalid, and a 1x forced-loss scenario correctly
crossed the declared ELEVATED threshold. Fixtures/oracle now reflect those original financial
contracts; no valid test was weakened. Further shock monotonicity found 1 failed/80 passed because
the forced liquidation scenario moved its endpoint when costs changed. Its endpoint now uses the
fixed gross-margin-loss benchmark plus explicit overshoot, while the liquidation root still models
costs. The original monotonic assertions pass. Mypy optional fixture narrowing and a Decimal default
were corrected; canonical UTC hashing now exercises the actual generation-time validator.

Debt: real derivative/funding/volatility data, authenticated risk/collateral reconciliation,
venue tiers/deductions/rounding/fees/ADL/insurance, collateral peg/haircuts, dynamic cross-margin/
correlated exposures, actual stop/slippage/liquidation/funding paths, inverse/options support,
empirical OOS/holdout/shadow evidence and validated ruin probability. None is silently implemented.
This phase supplies local research mechanics, not production readiness or profitability.
Phase 26 live read-only connectivity is next and has not been started.

## Complete changed-file list

- `README.md`
- `docs/architecture/LEVERAGE_RESEARCH.md`
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/TRADING_ARCHITECTURE.md`
- `docs/research/VALIDATION_POLICY.md`
- `docs/risk/RISK_POLICY.md`
- `docs/roadmap/ROADMAP.md`
- `docs/roadmap/PHASE_25_COMPLETION_REPORT.md`
- `src/pocket_alpha/leverage/__init__.py`
- `src/pocket_alpha/leverage/engine.py`
- `src/pocket_alpha/leverage/models.py`
- `tests/leverage_fixtures.py`
- `tests/test_leverage.py`

The phase is recorded in a local `feat: implement phase 25 leverage research` commit on
`codex/phase-25-leverage-research`; its SHA is reported after creation. No push/main merge/deployment.
