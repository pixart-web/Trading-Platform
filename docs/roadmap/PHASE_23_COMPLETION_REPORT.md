# Phase 23 completion report

## Summary, architecture and acceptance

Phase 23 implements persistent incremental crypto spot LONG PAPER execution, shared Phase 21
risk/execution economics, append-only decision journals, restart recovery, local reconciliation,
explicit public native polling and read-only API/UI. No real broker, strategy lifecycle or live
promotion is introduced. See ../architecture/PAPER_TRADING.md for exact assumptions and workflow.
Implementation is complete for this documented scope; production readiness or profit is not claimed.
Phase 24 is next and was not started. Work is isolated on codex/phase-23-paper; no push/main merge.

The clean preserved baseline was b94439153a127de1dbef35d06ff0263405fc6726 (Phase 22).
Pre-edit assessment identified missing incremental durable paper accounts, decision checkpoints,
recovery/reconciliation and shared simulation. It declared the extraction of existing execution,
additive migration 0014, actual processing-time causality, loss-of-feed suspension and unmistakable
PAPER labels in database/API/UI/logs. Existing service integration and execution calibration debt
was preserved. Acceptance requires no retroactive/duplicate fills, shared risk approvals and costs,
recovery without historical strategy callbacks, exact ledger reconciliation, atomic rollback,
idempotency/revision conflicts, permanent kill/drawdown halts and no real broker route.

## Implementation and financial coverage

SimulatedExecution is the unchanged extracted Phase 21 order/risk/fill engine. PaperStrategy extends
the existing immutable view/intention port with canonical checkpoint/restore. The PAPER runtime
receives only complete ordered native candles; recorded provider receipts remain immutable while
all decisions/fills observe actual processing time. A future complete bar must open strictly after
order readiness. Fees, spread, slippage, impact, volume participation, latency/ack, partial fills,
expiry/cancellation, precision, minimums, collars and existing risk limits are shared assumptions.

Cash, inventory, moving-average cost basis, reserves, realized/unrealized PnL, fees and marked equity
persist in a PAPER head. Its validator independently reconstructs financial accounting from fills
and verifies each fill's unique prior risk approval. Journal decisions and checkpoints rebuild
state deterministically without strategy callbacks. Hash/revision/idempotency and DB constraints
protect against incomplete/corrupted history and concurrent head updates. Savepoints roll back
both head and journal; transaction owners commit. Logs explicitly mark PAPER and prepared transactions.

Native gaps/staleness, disconnection, unknown simulated order state and strategy failures suspend
orders; pending simulation orders cancel and existing inventory remains genuinely marked.
Fresh data and matching accounting reconciliation can resume a suspension; operator/risk halts
remain latched. CLI observation emits no orders. Read-only no-store API/UI display origin, freshness,
readiness, accounting and recent events; invalid/unavailable data has no invented demonstration balance.

Regressions cover shared-engine round-trip parity, fees/PnL/cash/approval causality, FIFO liquidity,
partial fills, rejected SHORT/cash reservations/cancellation, original receipt versus processing
clock, event UUID reuse and revision conflicts, feed loss/unknown-state reconciliation, stale
suspension/catch-up, kill/drawdown with retained inventory, callback/checkpoint failure,
conflicting intentions with discarded tentative submissions, persisted restart in a new DB session,
private Decimal context, corruption and rehashed financial tampering, CAS/DB rollback, budget/code
drift, JSON PAPER logs, native/mock polling, CLI and read-only sanitized APIs.

## Migrations

0014 follows 0013 and adds paper_accounts/paper_journal with PAPER-only CHECK constraints,
head revision, hashes, journal FK and account/event UUID uniqueness. No prior records change.
SQLite verifies full upgrade 0001–0014 (34 tables) and 0014 downgrade preserving all 32 prior tables.
The isolated migration regression checks mode, event uniqueness, FK and preservation of unrelated data.
Export journal/header records before downgrade: it deletes PAPER data only. PostgreSQL DDL/service
integration was not executed locally; no production migration-readiness claim is made.

## Commands and exact results

- `.venv/Scripts/ruff.exe check .`: all checks passed.
- `.venv/Scripts/ruff.exe format --check .`: 270 files already formatted.
- `.venv/Scripts/python.exe -m mypy`: success, 194 source files checked.
- `.venv/Scripts/python.exe -m pytest --cov=pocket_alpha.paper_trading --cov-branch --cov-report=term-missing -q`: 641 passed, 196 skipped (unconfigured PostgreSQL/Redis integration), 2 dependency deprecation warnings in 258.45s. Combined PAPER statement/branch coverage 87%.
- Focused PAPER tests with branch coverage: 28 passed, 25 PostgreSQL skips, 2 dependency deprecation warnings in 32.82s. PAPER coverage: 87% combined statements/branches (650 statements, 55 missed, 210 branches, 52 partial). API 100%, service 94%, engine 87%, repository 86%, models 82%, feed 87%, CLI 90%.
- `.venv/Scripts/alembic.exe heads`: 0014 (head). Full SQLite upgrade/downgrade and isolated FK/mode/uniqueness/preservation regressions passed.
- Extraction AST comparison against baseline `_Simulation`: identical class logic after renaming to SimulatedExecution.
- `pnpm --dir frontend lint`: passed, zero warnings.
- `pnpm --dir frontend typecheck`: passed.
- `pnpm --dir frontend test`: 66 tests passed across 9 files.
- `pnpm --dir frontend build`: production build passed, including /paper.
- `$env:PA_TEST_BROWSER_CHANNEL='msedge'; pnpm --dir frontend test:e2e --workers=2`: 17 passed in 55.5s. PAPER empty-state screenshot visually inspected; labelled synthetic accounting screenshot verified by E2E; fixtures are explicitly synthetic.
- `git diff --check`: passed.

The first complete backend attempt reported 1 failed, 636 passed, 193 skipped in 287.28s;
its only failure was the new caplog test after application logging disabled ancestor propagation.
The test now captures the actual PAPER logger directly and retains its JSON mode/privacy assertions.
Initial E2E reported 14 passed/2 failed: an ambiguous alert selector including Next's route announcer
and an existing zone scenario timing out during six-worker concurrency. The selector now scopes
to main, and all criteria remain intact; the reduced-worker repeat passed all original scenarios,
followed by the final 17-case run including labelled synthetic accounting. Initial focused fixture
expectations were corrected to respect volume-limited inventory and current event timestamps;
no valid production test or economic assertion was weakened.

## Manual native observation

An opt-in, manual unauthenticated Coinbase BTC-USD 1-minute observation used a new PAPER account
with explicit uncalibrated costs/risk limits and the no-order Observer. At
2026-09-18T19:18:29.632618Z it accepted the native candle closing 2026-09-18T19:18:00Z,
became ACTIVE/ready for PAPER, persisted original receipt plus actual processing time and
reconciled after replay. Fills/orders remained zero and live_ready remained false. This proves
public-feed/persistence plumbing only, never economic edge, calibrated costs or execution quality.
The raw header/journal/view and SQLite probe are local ignored data/local/phase23_public_* artifacts;
no public payload is bundled into unit fixtures. Automated tests perform no network requests.

## Complete changed file list

- README.md
- docs/architecture/PAPER_TRADING.md
- docs/architecture/SYSTEM_ARCHITECTURE.md
- docs/architecture/TRADING_ARCHITECTURE.md
- docs/research/VALIDATION_POLICY.md
- docs/risk/RISK_POLICY.md
- docs/roadmap/ROADMAP.md
- docs/roadmap/PHASE_23_COMPLETION_REPORT.md
- frontend/app/page.tsx
- frontend/app/paper/page.tsx
- frontend/components/paper-panel.tsx
- frontend/e2e/paper.spec.ts
- frontend/lib/paper.ts
- frontend/lib/proxy.ts
- frontend/tests/paper.test.ts
- migrations/env.py
- migrations/versions/0014_paper.py
- src/pocket_alpha/backtesting/engine.py
- src/pocket_alpha/main.py
- src/pocket_alpha/observability.py
- src/pocket_alpha/paper_trading/__init__.py
- src/pocket_alpha/paper_trading/__main__.py
- src/pocket_alpha/paper_trading/api.py
- src/pocket_alpha/paper_trading/engine.py
- src/pocket_alpha/paper_trading/feed.py
- src/pocket_alpha/paper_trading/models.py
- src/pocket_alpha/paper_trading/service.py
- src/pocket_alpha/paper_trading/storage.py
- src/pocket_alpha/simulation/__init__.py
- src/pocket_alpha/simulation/engine.py
- tests/test_paper_api.py
- tests/test_paper_cli.py
- tests/test_paper_feed.py
- tests/test_paper_migration.py
- tests/test_paper_trading.py

## Economic assumptions, limitations, debt and security

Single-market quote-currency crypto spot LONG only. Complete-bar-close fills and configured
fee/spread/slippage/impact are modeled assumptions, not measured order-book/tick execution.
There is no validated ruin probability, profit protection guarantee, calibrated strategy/model,
multi-asset/correlated risk, SHORT/leverage/margin, derivative execution or autonomous deployment.
Rolling technical history is bounded; recursive features after truncation can differ from a
full-prefix backtest. Explicit operator polling/heartbeats are required; no continuous availability
or automatic reconnect/resume is claimed. No automatic portfolio liquidation occurs on stale data
or halt. Journal replay is bounded but not optimized for production throughput.

Coverage does not prove profit. Remaining uncovered branches are defensive invalid-record/model
and runtime-contract guards, UTC day rollover, specific forecast identity/availability rejection,
malformed checkpoints, missing accounts/custom-identity CLI polling and deliberate budget/index
corruption. These must receive further negative/adversarial tests before production qualification;
valid flow plus principal execution/idempotency/reconciliation failure behavior is exercised.
PostgreSQL/Redis integration and Docker/container checks remain unexecuted locally due the previously
recorded Windows psycopg DLL/App Control and unavailable Docker Linux daemon. Skips are not passes.
No dependency failure is reported as ready, and no remote CI is claimed for unpushed work.

Live configuration remains Literal[False]. There are no credential/order/withdrawal adapters,
public write routes or dynamic strategy loaders. HTTP error details are sanitized; JSON logs
allowlist PAPER metadata without input/checkpoint/secret bodies. Tests/native observation cannot
place real orders. Hashes are audit consistency checks, not protection against an administrator
rewriting all records. Custom Python strategies are trusted code, not security sandboxes.
No new dependencies or authentic trading performance claims are introduced.

Next phase: 24, Strategies. Not started.
