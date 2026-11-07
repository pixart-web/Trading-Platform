# Native Android architecture

The application is Kotlin/Jetpack Compose, not a WebView. `android/app` is one Gradle module with `core` and `feature` packages. This avoids 25 empty modules while the feature contracts are consolidated. Hilt creates the repository, JSON serializer, Room database, preferences and Keystore vault. `WorkspaceViewModel` exposes StateFlows; Compose collects them with lifecycle awareness. Navigation Compose owns bottom navigation and the module drawer; saved state restores supported forms/navigation after recreation. Passwords are deliberately not saved in Bundle state.

## Data boundary

Retrofit/OkHttp calls only the configured HTTPS origin under `/mobile/api/v1/`. Redirects and connection retries are disabled. Authentication is server-side. The authenticated FastAPI child application reuses existing financial route handlers and the same SQLAlchemy engine/Redis instance. The private original API and web frontend remain available in their existing topology. No native broker SDK, forecast model, fill simulator or risk authorization engine exists.

Access tokens live in memory; only the rotating refresh credential, session and user IDs persist in one AES-GCM encrypted AtomicFile under no-backup storage. The encryption key stays in Android Keystore. The server stores credential hashes, five-minute access expiry, absolute 30-day refresh expiry, consumed-token history and revocable device sessions. Reusing a consumed refresh credential revokes its session. Manual accounting edits require a separate recent password confirmation. Identity is one provisioned operator for the existing shared workspace, not multi-tenant signup.

Room stores bounded read snapshots, scoped by origin/user/request. Up to 64 payloads of at most 1 MiB are retained; each network response is limited to 4 MiB. ViewModel resources are also bounded. Failed network reads may show an explicit stale cache timestamp; permission and validation failures never become cached success. Financial writes have no offline queue or network retry. Manual entry IDs survive recreation and the server checks idempotency/revision. WorkManager periodically refreshes allowed reads with network/battery constraints; it does not run server operations.

## Additive backend changes

Migration 0017 adds native operator/session tables. Migration 0018 adds revision-checked watchlist archival, preserving snapshots and alerts. Native snapshot discovery uses bounded keyset pagination over existing immutable Analyze reports. `native-openapi.json` is generated from the allowlisted native routes and checked for drift in CI. No accounting ledger is rewritten.

## Current limits

Cross-entity incremental synchronization, realtime sequence recovery, remote push, durable research job submission, local biometric gating and privileged operational monitoring are not implemented. Advanced artifact views expose actual existing read contracts and explicit unavailable states. This architecture is an integration candidate and is not full Android functional parity.

## Official references used

- [Android Gradle plugin compatibility](https://developer.android.com/build/releases/agp-8-9-0-release-notes)
- [Android offline data architecture](https://developer.android.com/topic/architecture/data-layer/offline-first)
- [Android Keystore](https://developer.android.com/privacy-and-security/keystore)
- [KSP migration](https://developer.android.com/build/migrate-to-ksp)
- [AndroidJUnitRunner](https://developer.android.com/training/testing/instrumented-tests/androidx-test-libraries/runner)
- [OSV batch audit API](https://google.github.io/osv.dev/post-v1-querybatch/)

The native topology gives only the API an outbound provider network in addition to its private application/data networks. PostgreSQL/Redis keep no host ports and no external network. This permits explicit server-side provider imports without requiring Next.js; it does not start ingestion or authorize broker writes automatically.
