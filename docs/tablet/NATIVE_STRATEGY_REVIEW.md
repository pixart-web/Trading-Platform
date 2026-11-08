# Native strategy research review

## Assessment, phase and acceptance

After delivering the frozen `tablet-preview-0.1` APK from `f3ad549`, development resumes on the earliest strategy prerequisite: a read-only native projection of the existing Python `TrendStrategy.proposal` decision mechanics. This is not complete strategy parity or a working Paper Autopilot. `LOCAL_STRATEGY_PIPELINE_READY`, `PAPER_AUTOPILOT_READY` and `STANDALONE_E2E_VERIFIED` remain NO. The published Preview asset is unchanged.

Acceptance: exact actions/reasons, reference/invalidation values, quantized trend/return, selected forecast identity and expiry against the original Python engine; future-input rejection, strict definition/memory binding, bounded inputs and no path from the review to orders. No forecast, probability, model promotion, fill or profit is invented.

## Architecture and scope

`LocalTrendReview` is independent of Compose, Room, financial authority, providers and brokers. It snapshots collections, uses Decimal80 HALF_EVEN with 24-place HALF_EVEN quantization at the same boundary as Python, and returns immutable scalar research results. Native versioned definitions include explicit periods, thresholds, model/feature/market/source identities, freshness, invalidation and a forecast horizon separate from candle timeframe. A native JSON SHA-256 definition key binds memory; this native key is deliberately not claimed to equal the Python full-definition hash.

It checks freshness/causality and source identity, requires one unambiguous newest compatible available forecast, tests LONG/SHORT trend and expected-return criteria independently, retains NO_TRADE for missing or opposing evidence, and evaluates observed-price stop/holding expiry before trend exits. A SHORT analysis with no position remains NO_TRADE with SHORT_CASE_ONLY; it cannot open a short. Existing-position exit indications still require an invalidation reference. These are research indications, not allocated orders or risk approvals.

`ForecastHorizonClock` reproduces all thirteen fixed/calendar horizon conventions, including six/twelve UTC calendar months and end-of-month clamping. It produces no forecast estimates.

`StrategyReviewAdapter` consumes the application's actual non-synthetic Coinbase candles and the same qualified SMA helper. The operational research definition uses SMA20/SMA50, H1 input/4H horizon, 0.001 trend/expected-return thresholds, 10% invalidation and 7,200-second freshness. These are explicit unvalidated research settings, not a promoted strategy. It supplies **no forecasts** and **no strategy-owned position memory**. Manual account inventory is not relabelled as a strategy fill. The UI shows the evaluator's NO_TRADE/MISSING_EVIDENCE and explains the missing native forecast and Autopilot capabilities.

The forecast input type is a mechanical research projection, not the complete immutable canonical forecast/evidence/probability contract. Only isolated tests supply forecast projections. Operational forecast ingestion, generation and persistence remain unavailable. No review is persisted as a strategy proposal, no full Python proposal/evidence/hash equivalence is claimed, no generic directional engine is qualified, and no review can call submit/order/risk or alter financial balances. Allocation, lifecycle promotion, observed-fill memory and durable session orchestration remain separate gates.

## Validation

`python -m tests.local_strategy_vectors --check` regenerates both Android fixtures from the **existing Python TrendStrategy**; it does not reproduce strategy formulas in Python test code. The fixtures are explicitly SYNTHETIC_ENGINEERING_FIXTURE and contain 27 cases plus 26 horizon cases. They cover entry, hold, SHORT-without-entry, opposing evidence, absent/warmup/incompatible/ambiguous forecasts, selection of newest compatible forecasts, stop/expiry precedence, stale exits, exact freshness boundary and a one-microsecond violation, source/bar mismatch and HALF_EVEN expected-return rounding. JVM and Android share the same comparison function. The backend CI gate rejects stale fixture files; the existing x86_64 engine test executes the comparisons in both create/recover processes without replacing journal assertions.

JVM suite: 16 passed. Ruff check/format, mypy (273 files), both golden generators and existing schema checks pass. Local pytest: 1,097 passed, 233 skipped, two warnings; service-backed tests remain mandatory in final pushed CI. Final local build/debug/release/bundle/lint passed. ARM64 API 35: actual-provider/UI/review/portable suite passed 3 tests; oracle/journal create plus backup passed 2; separate-process recovery passed 1; key-loss recovery passed 1. The new review diagnostics were asserted in the real-data UI test and the landscape capture was visually inspected. Final pushed x86_64/backend CI is reported after observation at delivery. An initial oracle run caught and corrected the SHORT_CASE_ONLY reason mismatch; the test expectation was preserved.

Commands: `ruff check .`, `ruff format --check .`, `mypy .`, `pytest`, `python -m tests.local_strategy_vectors --check`, `python -m tests.local_kernel_vectors --check`, `python -m pocket_alpha.mobile.export_schema --check`; Gradle tasks `:app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest :app:assembleRelease :app:bundleRelease`. Android instrumentation separately targeted PublicWorkspaceAndroidTest/RealPublicProviderAndroidTest/PortableLedgerAndroidTest, LocalStandaloneEngineTest create/recover and KeyLossAndroidTest. Only the explicit real-provider test used public network data; no broker or Pocket Alpha backend was running.

## Persistence, financial coverage and security

No schema, database, migration, broker path, dependency or financial accounting change. Existing experiments and encrypted backups remain compatible with the Preview. Financial coverage extends only exact research price/invalidation/return arithmetic; cash/reserves/P&L/risk/fills stay under the existing authority and oracle. No secret or broker credential is added. Input bounds are 1,000 historical bars, 64 projected forecasts and 16 matching values per SMA period. Malformed/future/unbound inputs fail rather than authorize a decision. No ruin probability, empirical profitability or continuous-execution guarantee is asserted.

## Limitations, debt and next prerequisites

Still required before automation: full immutable native forecast/evidence contract and actual model qualification, complete directional evidence/provenance, allocated proposal identity bound to risk, lifecycle/strategy qualification, observed-fill checkpoint ownership, UTC day rollover, durable decision/session/suspension journal, lifecycle-safe active-session runtime, pause/resume/stop/reconciliation and forward real-data E2E. Multi-position accounting, biometric gating and physical Redmi acceptance remain pending. No background loop or automatic order route has been started in this increment.

## Changed files

- `.github/workflows/ci.yml`
- `android/app/src/androidTest/java/pt/pocketalpha/LocalStandaloneEngineTest.kt`
- `android/app/src/androidTest/java/pt/pocketalpha/PublicWorkspaceAndroidTest.kt`
- `android/app/src/androidTest/assets/local-strategy-golden.json`
- `android/app/src/main/java/pt/pocketalpha/local/LocalTrendReview.kt`
- `android/app/src/main/java/pt/pocketalpha/workspace/StrategyReviewAdapter.kt`
- `android/app/src/main/java/pt/pocketalpha/workspace/LocalWorkspaceScreen.kt`
- `android/app/src/sharedTest/java/pt/pocketalpha/StrategyGoldenAssertions.kt`
- `android/app/src/test/java/pt/pocketalpha/LocalStrategyReviewTest.kt`
- `android/app/src/test/resources/local-strategy-golden.json`
- `tests/local_strategy_vectors.py`
- `docs/tablet/NATIVE_STRATEGY_REVIEW.md`
- `docs/tablet/AUTOPILOT_RUNTIME.md`
- `docs/tablet/TABLET_ARCHITECTURE.md`
- `docs/tablet/RELEASE_READINESS.md`
- `docs/tablet/FEATURE_PARITY.md`
