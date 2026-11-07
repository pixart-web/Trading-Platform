# Native Android implementation report

Candidate branch: `codex/android-native`, based on main `1dd52d4`. This delivers an integrated native candidate, not complete acceptance of the master prompt. No live orders or financial engines were enabled.

## Delivered scope and architecture

Kotlin/Jetpack Compose, Hilt, Retrofit/OkHttp, Room, DataStore and WorkManager form a native client of the existing Python modular monolith. Native routes require revocable opaque sessions; refresh credentials are encrypted using Android Keystore, access tokens remain in memory, and refresh reuse revokes the session family including concurrent rotation. One operator workspace matches the existing platform. Existing web PIN/cookie authentication remains separate.

Dashboard, bounded OHLC/volume charts, Analyze artifact discovery, server scanner, watchlist membership/rename/archive, portfolio accounting with step-up and stable idempotency IDs, device sessions and server-backed advanced artifact views are implemented. Unsupported server capabilities are explicitly unavailable. The phase-by-phase matrix in FEATURE_PARITY_MATRIX.md is the acceptance source; zero complete phase-level acceptances are claimed.

Financial decisions, forecasts, risk approval and execution remain server-side. Amounts use exact decimal strings/BigDecimal; candle timeframe and forecast horizon remain distinct. Historical snapshots retain their identity and timestamps. Missing evidence never becomes an invented probability, forecast, fill or permission to trade. Synthetic data exists only in an explicitly invoked guarded test fixture. No return, profit or economic improvement is assumed.

## Backend and migrations

Migrations 0017/0018 add operator/device/consumed-refresh state and watchlist archival. The native API is disabled by default. Additive migration must precede deployment of the new API image. Retain schema during containment/forward fix; review archive behavior before reverting to older API code. Native deployment has no Next.js service, exposes only the TLS proxy, keeps database/cache private and allows explicit server provider egress.

## Validation and artifacts

Local: Ruff and formatting pass; mypy passes 269 files; Python 1097 passed/233 opt-in skips; focused PostgreSQL/Redis 46 passed; Kotlin 7 passed. Strict Gradle lint/debug/release/APK/AAB builds pass. Four viewport configurations on one API35 ARM64 emulator passed the real HTTPS backend workflow including watchlist CRUD, activity recreation and independent-session revocation. Eight captures are in screenshots/. These are not physical-device or process-death tests.

Runtime Maven OSV: 107 packages, zero known affected. Both Python dependency audits have zero known vulnerabilities after certifi remediation. Bandit has zero medium/high findings; staged tracked-file secret gate passes. These checks do not establish absence of unknown vulnerabilities.

Local outputs: `android/app/build/outputs/apk/debug/app-debug.apk`, `android/app/build/outputs/apk/release/app-release-unsigned.apk`, `android/app/build/outputs/bundle/release/app-release.aab`. Standard outputs contain no test TLS root. Production signing/store distribution is not configured. Artifact checksums are locally recorded in ignored build/reports/local-artifacts.sha256. Remote CI observation is recorded in TEST_EVIDENCE.md after publication.

## Open acceptance and next work

Research/backtest submission and job lifecycle, full incremental sync/realtime/push, complete chart overlays, operational read models, physical-device accessibility/performance, real-provider coverage, exhaustive offline/process-death/revocation qualification and production signing/deployment remain incomplete. Several are backend contract gaps, not UI-only work. macOS has shared contract requirements documented, not a completed shared application architecture. No next phase is started by this report.

Release verdict: UI_READY=NO; FUNCTIONAL_PARITY=NO; BACKEND_INTEGRATION=NO for complete scope; MULTI_DEVICE_SYNC_READY=NO; RELEASE_BUILD_READY=YES for unsigned artifacts; PRODUCTION_READY=NO; MACOS_SHARED_ARCHITECTURE_READY=NO; REAL_MONEY_TRADING_AUTHORIZED=NO. See RELEASE_READINESS.md for exact flags and SECURITY_REVIEW.md for residual risks.

## Complete changed-file inventory relative to base

- `.dockerignore`
- `.github/workflows/ci.yml`
- `.gitignore`
- `.secrets.baseline`
- `README.md`
- `android/README.md`
- `android/app/build.gradle.kts`
- `android/app/gradle.lockfile`
- `android/app/proguard-rules.pro`
- `android/app/src/androidTest/java/pt/pocketalpha/BackendWorkflowTest.kt`
- `android/app/src/androidTest/java/pt/pocketalpha/NativeUiTest.kt`
- `android/app/src/main/AndroidManifest.xml`
- `android/app/src/main/java/pt/pocketalpha/MainActivity.kt`
- `android/app/src/main/java/pt/pocketalpha/PocketAlphaApp.kt`
- `android/app/src/main/java/pt/pocketalpha/core/Api.kt`
- `android/app/src/main/java/pt/pocketalpha/core/Models.kt`
- `android/app/src/main/java/pt/pocketalpha/core/Repository.kt`
- `android/app/src/main/java/pt/pocketalpha/core/Storage.kt`
- `android/app/src/main/java/pt/pocketalpha/feature/AdvancedScreen.kt`
- `android/app/src/main/java/pt/pocketalpha/feature/Charts.kt`
- `android/app/src/main/java/pt/pocketalpha/feature/Components.kt`
- `android/app/src/main/java/pt/pocketalpha/feature/DashboardScreen.kt`
- `android/app/src/main/java/pt/pocketalpha/feature/MarketWorkflows.kt`
- `android/app/src/main/java/pt/pocketalpha/feature/PortfolioScreen.kt`
- `android/app/src/main/java/pt/pocketalpha/feature/Theme.kt`
- `android/app/src/main/java/pt/pocketalpha/feature/WorkspaceViewModel.kt`
- `android/app/src/main/res/drawable/ic_launcher.xml`
- `android/app/src/main/res/values/styles.xml`
- `android/app/src/main/res/xml/data_extraction_rules.xml`
- `android/app/src/main/res/xml/network_security_config.xml`
- `android/app/src/test/java/pt/pocketalpha/ContractsTest.kt`
- `android/build.gradle.kts`
- `android/gradle.properties`
- `android/gradle/libs.versions.toml`
- `android/gradle/verification-metadata.xml`
- `android/gradle/wrapper/gradle-wrapper.jar`
- `android/gradle/wrapper/gradle-wrapper.properties`
- `android/gradlew`
- `android/gradlew.bat`
- `android/lint.xml`
- `android/settings-gradle.lockfile`
- `android/settings.gradle.kts`
- `android/tooling/audit_dependencies.py`
- `compose.native.yaml`
- `compose.production.yaml`
- `deploy/Caddyfile`
- `deploy/Caddyfile.native`
- `docs/android/ANDROID_ARCHITECTURE.md`
- `docs/android/ANDROID_DESIGN_SYSTEM.md`
- `docs/android/API_INTEGRATION_MATRIX.md`
- `docs/android/BUILD_AND_INSTALL.md`
- `docs/android/EXISTING_PLATFORM_INVENTORY.md`
- `docs/android/FEATURE_PARITY_MATRIX.md`
- `docs/android/IMPLEMENTATION_ASSESSMENT.md`
- `docs/android/IMPLEMENTATION_REPORT.md`
- `docs/android/PERFORMANCE_REVIEW.md`
- `docs/android/PRIVACY.md`
- `docs/android/RELEASE_NOTES.md`
- `docs/android/RELEASE_READINESS.md`
- `docs/android/SCREEN_INVENTORY.md`
- `docs/android/SECURITY_REVIEW.md`
- `docs/android/TEST_EVIDENCE.md`
- `docs/android/native-openapi.json`
- `docs/android/screenshots/compact-dashboard.png`
- `docs/android/screenshots/compact-overview.png`
- `docs/android/screenshots/large-dashboard.png`
- `docs/android/screenshots/large-overview.png`
- `docs/android/screenshots/standard-dashboard.png`
- `docs/android/screenshots/standard-overview.png`
- `docs/android/screenshots/tablet-dashboard.png`
- `docs/android/screenshots/tablet-overview.png`
- `docs/architecture/MACOS_COMPATIBILITY_REQUIREMENTS.md`
- `docs/architecture/MULTI_DEVICE_SYNC.md`
- `frontend/app/api/auth/login/route.ts`
- `frontend/package.json`
- `frontend/pnpm-lock.yaml`
- `migrations/env.py`
- `migrations/versions/0017_mobile_identity.py`
- `migrations/versions/0018_watchlist_archive.py`
- `requirements-runtime.lock`
- `requirements.lock`
- `src/pocket_alpha/audit/models.py`
- `src/pocket_alpha/config.py`
- `src/pocket_alpha/main.py`
- `src/pocket_alpha/mobile/__init__.py`
- `src/pocket_alpha/mobile/app.py`
- `src/pocket_alpha/mobile/auth.py`
- `src/pocket_alpha/mobile/export_schema.py`
- `src/pocket_alpha/mobile/models.py`
- `src/pocket_alpha/mobile/provision.py`
- `src/pocket_alpha/mobile/readmodels.py`
- `src/pocket_alpha/mobile/security.py`
- `src/pocket_alpha/watchlists/storage.py`
- `tests/native_e2e_seed.py`
- `tests/test_mobile_identity.py`
- `tests/test_mobile_integration.py`
