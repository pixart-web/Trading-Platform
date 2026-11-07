# ADR T001 — native tablet host with qualified local financial boundary

Decision state: proposed, contingent on Android runtime proof. Supersedes server authority as the desired tablet product architecture; it does not misdescribe the current client as local. Existing backend/web remain preserved. No Hetzner deployment or public website is part of this work.

## Boundary

Provider HTTPS → normalized immutable local observations → financial kernel → forecasts → directional analysis → strategy → portfolio → risk admission → PAPER simulator → durable journal. There is no real broker adapter in the tablet execution boundary. Portfolio accounting alone must never authorize a simulated order.

Kotlin owns tablet navigation, provider admission/rate limiting, SQLite transactions, Keystore encryption, bounded job scheduling and exports. A qualified local kernel owns financial computations, decimal context and causal artifact production. Runtime choice is gated by STANDALONE_FEASIBILITY.md; the Python source remains the reference oracle. No network-accessible local services.

## Persistence and crash safety

Use a separate local database identity/schema, not a destructive migration of the server response cache. Persist accounts, immutable policy/configuration versions, input/event digests, order approvals, fills, journal hash chain, high-water mark and actual processing timestamps. A single writer atomically appends journal and revision with uniqueness on account/event ID. Replay/reconciliation precedes resumption. Corruption or incomplete reconciliation freezes submissions. Reset creates a new experiment; it never deletes old accounts.

Encrypt sensitive financial payloads with device-bound Keystore material. Portable exports need independently derived authenticated encryption and explicit password verification; exporting the device key is forbidden. Restore validates schema, limits, identity, journal chain and reconstructed balances into a new account namespace before activation. Biometric gating remains required, not implemented by this ADR.

## Runtime and gaps

Supported initial operating contract: explicit active-tablet session with visible runtime status. Leaving the active execution state, feed gaps or restart records a suspension and cancels pending simulation where required. Relaunch reconciles and requires explicit resume. Never reconstruct fills during an unobserved interval or submit delayed intents on reconnect.

WorkManager is deferred maintenance/import scheduling, not a continuous trading clock. Its minimum periodic interval is 15 minutes and execution is affected by Doze: [Android documentation](https://developer.android.com/reference/androidx/work/PeriodicWorkRequest). A foreground service does not guarantee survival; qualify its permitted service type and actual behavior on target OS before introducing one. Report observed uptime, suspension intervals and missed evaluation intervals rather than inferred uptime.

## Acceptance gates

Runtime/native ABI proof → financial golden equality → transactional ledger/recovery → real public provider provenance → bounded local research → risk/PAPER orchestration → tablet UI and hardware endurance. No gate may be replaced by the previous server-backed E2E success. Standalone readiness stays NO until all essential paths work without external Pocket Alpha services.
