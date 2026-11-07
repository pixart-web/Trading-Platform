# Android and native API security review

Scope: new Kotlin client, native FastAPI boundary, identity migrations, watchlist archival and native deployment routing. Existing financial/security reviews remain applicable. This is an implementation review with tests, not a penetration test or production certification.

## Controls implemented

- No embedded backend/broker secret or production signing key. Configured origins require HTTPS and reject userinfo, query, fragment and unrelated paths. OkHttp retains TLS and hostname verification, trusts system roots and refuses redirects.
- Native bearer authentication protects every included business route; login/refresh have a distributed Redis rate limit that fails closed on Redis failure. Access credentials last five minutes; refresh credentials rotate with absolute expiry/replay revocation. Session revocation also invalidates access tokens immediately.
- Password verification uses salted scrypt with bounded input. Passwords/tokens are absent from client logs; server sessions contain only hashes. Provisioning is a private CLI with getpass, no public registration. A database constraint permits one operator workspace.
- Encrypted AtomicFile plus non-exportable Keystore AES-GCM protects stored refresh credentials. Passwords and refresh credentials never enter Room/DataStore. Backup/device transfer is excluded. MainActivity sets FLAG_SECURE; only its launcher activity is exported and there are no deep links/WebViews/broker intents.
- Body and response bounds, bounded queries, strict Pydantic schemas, fixed client routes, server revisions, stable accounting IDs and a recent password confirmation protect mutations. Offline financial commands are not queued.
- The child API excludes broker credentials, execution journals, live-control mutations, internal health and OpenAPI. Caddy only routes the explicit native prefix to it. PostgreSQL/Redis remain private. Backend-only deployment has no Next.js dependency.
- Dependency locks, Gradle distribution checksum and artifact verification metadata are committed. OSV checked 107 resolved runtime packages with no known affected packages at the recorded check. Version-upgrade recommendations remain informational; correctness/security lint findings fail builds.

## Findings and residual blockers

S1 HIGH, OPEN: complete incremental cross-device state/conflict/realtime recovery has not been implemented or audited. Do not claim synchronized financial readiness.

S2 HIGH, OPEN: native research submission and operational monitoring contracts are absent. Do not expose existing privileged interfaces to close this gap.

S3 MEDIUM, OPEN: biometric app unlock is absent; stored read cache relies on Android application sandbox, device security and backup exclusion. No guarantee is made against a compromised/unlocked device.

S4 MEDIUM, OPEN: no full physical-device, TalkBack, process-death, intent/dependency penetration or revocation/offline endurance audit. Keystore behavior still requires representative hardware validation.

The optional `e2eCaFile` Gradle property generates trust for one explicit localhost certificate in debug resources only. It is for disposable HTTPS instrumentation; standard debug/release builds contain no such certificate. No certificate verification bypass is used. Final distributable builds must be produced without this property.

Real-money execution remains unauthorized. Passing mechanical tests is not economic evidence or broker qualification.

Local session storage also retains the server's absolute refresh expiry. Expired/corrupt storage cannot unlock cached views. A server refresh/revocation failure invalidates the in-memory workspace and clears cached credentials/data; the UI returns to sign-in. Device integration exercises revocation by an independently authenticated second session rather than relying only on a local logout flag.

The Python lock audit identified PYSEC-2026-4320 in certifi 2026.7.22. Both runtime/development locks now pin 2026.10.18, and both pip-audit checks report no known vulnerabilities. The secret gate preserves scanning of source and metadata, with a narrowly anchored exclusion for generated 64-hex Gradle SHA-256 records and explicit annotations for rejected login/URL fixtures. Existing baseline entries were normalized from Windows paths; no new secret fingerprints were accepted.

S5 HIGH, RESOLVED: simultaneous refresh requests could both miss the first consumed-token read, allowing the winning token to survive the losing replay. The handler now rechecks consumption in a fresh transaction after waiting on the row lock. A deterministic two-transaction PostgreSQL test reproduced the failure before the fix and now verifies that the newly issued access credential is revoked as well. Native session endpoints are also declared as an opaque HTTP Bearer security scheme in the generated OpenAPI contract.
