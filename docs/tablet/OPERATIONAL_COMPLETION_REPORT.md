# Local operational integration checkpoint

## Assessment and phase

The authorized earliest operational increment replaces server-dependent startup with a real native workspace over the verified local authority. It includes public historical data, qualified indicators, manual risk-gated PAPER experiments and authenticated portable backup. Full requested tablet integration remains incomplete. Backend phases 0–30 and their shared Python intelligence are preserved; phase 31 has not been started.

## Architecture and changes

Hilt supplies the Room financial authority and public adapter. Compose observes a dedicated ViewModel. Financial computation remains independent of Activity/lifecycle. Existing Python algorithms remain the reference oracle: no second unqualified forecast/directional/strategy path was introduced. Public GET data is separate from encrypted financial journals and the optional server client. Default startup needs neither credentials nor Pocket Alpha services. Orders still pass the existing financial risk gate; no broker dispatch exists.

Genesis v2 identifies actual EUR spot markets and a monitor-only strategy attribution. Older synthetic v1 fixture journals remain replayable solely for engineering tests and are rejected by operational import. Exact available/reserved cash, inventory reservation, mark equity, unrealized P&L and high-water fields are compared against the Python oracle. Price chart coordinates are presentation-only.

## Persistence and migration risks

No SQL schema/table migration, destructive reset or backend migration. Financial Room schema stays v1; encrypted genesis payload adds supported version v2. New public history uses a separate Room v1 database. Old experiments are retained. Restore creates a new identity, reencrypts with the current device key and verifies the entire hash chain and mathematical state within one transaction. Compatibility is one-way for v2 payloads: an older binary cannot understand new public accounts. Rollback of the whole database or an older valid backup is not prevented.

## Acceptance and executed verification

See [integration evidence](INTEGRATION_TEST_EVIDENCE.md) for exact test counts and raw ARM logs. Accepted: default local launch, real provider candles, exact SMA/EMA, manual account creation, authoritative balance/history, risk-gated manual command path, restart replay, encrypted portable restore, wrong-password/tamper/cancel/key-loss rejection and no real-money execution. Automated real-market strategy decisions/fills and complete standalone E2E are not accepted.

Reproducible checks: `ruff check .`, `ruff format --check .`, `mypy .`, `pytest`, `python -m tests.local_kernel_vectors --check`, `python -m pocket_alpha.mobile.export_schema --check`, `python android/tooling/audit_local_engines.py --check`. Android: `./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest :app:assembleRelease :app:bundleRelease :app:writeRuntimeCoordinates`. Dependency/security commands and all backend/web/device integration gates remain in `.github/workflows/ci.yml`. Final pushed SHA and CI are recorded in delivery after observation.

## Financial coverage and economic assumptions

Each independent EUR account supports one market, one spot LONG inventory and one pending order, exact Decimal80 monetary arithmetic, Decimal50 indicators, causal complete-bar-close simulated fills, partial fills, fees/costs/basis/realized and unrealized P&L, reservations and bounded journal reconciliation. Public data currently exposes BTC/ETH selection and product discovery, not shared multi-market capital. The immutable conservative research profile uses 10 bps fees, 10 bps spread, 5 bps slippage, 5 bps impact, 5% collar, 1% participation, 100 EUR order cap, 10% exposure/drawdown and 3% daily loss. These are hypothetical PAPER assumptions, not venue fees or validated loss guarantees. Minimum quote funds/quantity quantum come from product metadata; quantity quantum is not a claimed exchange minimum size. No probability, profitability or ruin estimate is asserted.

## Security, limitations and debt

Keystore AES-GCM protects device journal payloads; password-derived independent AES-GCM protects portable backups. No provider credentials, exported device key, broker transport or withdrawals. Public history is nonconfidential cache, not financial authority. Password strength, device compromise, whole-backup rollback, biometric gating, physical power loss, hardware/thermal/battery qualification and production signing remain outside accepted security coverage. Network/dependency failure blocks processing. Recovered/interrupted pending orders cannot silently catch up fills.

Uncompleted requirements: multi-position/shared-cash orders, UTC rollover, configurable risk/strategy, qualified native structure/forecasts/directional/strategy, active-session autopilot, full portfolio/watchlists/scanner/risk/performance UI, biometrics and physical Redmi Pad 2 acceptance. Last-selected account preference is not persisted. The mandatory forecast/directional boundary is not bypassed with an SMA-only strategy. The next authorized phase must qualify those prerequisites and accounting invariants before enabling automation; it has not been started.

## Complete changed-file inventory

- `.github/workflows/ci.yml`
- `android/README.md`
- `android/app/src/androidTest/assets/local-kernel-golden.json`
- `android/app/src/androidTest/java/pt/pocketalpha/BackendWorkflowTest.kt`
- `android/app/src/androidTest/java/pt/pocketalpha/KeyLossAndroidTest.kt`
- `android/app/src/androidTest/java/pt/pocketalpha/NativeUiTest.kt`
- `android/app/src/androidTest/java/pt/pocketalpha/PortableLedgerAndroidTest.kt`
- `android/app/src/androidTest/java/pt/pocketalpha/PublicWorkspaceAndroidTest.kt`
- `android/app/src/debug/AndroidManifest.xml`
- `android/app/src/debug/java/pt/pocketalpha/LegacyClientActivity.kt`
- `android/app/src/main/java/pt/pocketalpha/MainActivity.kt`
- `android/app/src/main/java/pt/pocketalpha/PocketAlphaApp.kt`
- `android/app/src/main/java/pt/pocketalpha/local/FinancialKernel.kt`
- `android/app/src/main/java/pt/pocketalpha/local/LocalLedger.kt`
- `android/app/src/main/java/pt/pocketalpha/workspace/LocalWorkspaceModel.kt`
- `android/app/src/main/java/pt/pocketalpha/workspace/LocalWorkspaceModule.kt`
- `android/app/src/main/java/pt/pocketalpha/workspace/LocalWorkspaceScreen.kt`
- `android/app/src/main/java/pt/pocketalpha/workspace/PortableBackup.kt`
- `android/app/src/main/java/pt/pocketalpha/workspace/PublicMarkets.kt`
- `android/app/src/sharedTest/java/pt/pocketalpha/LocalGoldenAssertions.kt`
- `android/app/src/test/java/pt/pocketalpha/OperationalWorkspaceTest.kt`
- `android/app/src/test/resources/local-kernel-golden.json`
- `docs/tablet/AUTOPILOT_RUNTIME.md`
- `docs/tablet/BACKUP_RESTORE.md`
- `docs/tablet/FEATURE_PARITY.md`
- `docs/tablet/INTEGRATION_TEST_EVIDENCE.md`
- `docs/tablet/LOCAL_WORKSPACE.md`
- `docs/tablet/OPERATIONAL_COMPLETION_REPORT.md`
- `docs/tablet/PAPER_OPERATIONAL_FLOW.md`
- `docs/tablet/REAL_MARKET_DATA.md`
- `docs/tablet/RELEASE_READINESS.md`
- `docs/tablet/TABLET_ARCHITECTURE.md`
- `docs/tablet/evidence/operational-2026-11-08/core-create.txt`
- `docs/tablet/evidence/operational-2026-11-08/core-recover.txt`
- `docs/tablet/evidence/operational-2026-11-08/key-loss.txt`
- `docs/tablet/evidence/operational-2026-11-08/public-android.txt`
- `docs/tablet/evidence/operational-2026-11-08/public-provider.txt`
- `docs/tablet/screenshots/real-market-landscape.png`
- `tests/local_kernel_vectors.py`
