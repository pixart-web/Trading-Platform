# Android implementation assessment

User authorization supersedes the historical one-phase roadmap limit for this Android assignment. Preserve all existing code and the F0–F30 history.

## Design and impact before production edits

Add a Kotlin/Compose application under android with cohesive core and feature packages rather than 25 empty Gradle modules. Reuse FastAPI handlers through a separate authenticated mobile surface. No broker, execution or live-control mutation routes on this surface. Introduce opaque short-lived access tokens, hashed rotating refresh credentials, revocable device sessions and one provisioned operator identity. Existing workspace is single-owner: no public registration or unsupported multi-tenant isolation claims.

Additive identity migration follows 0016; no ledger rewrite. Deploy migration before mobile API. Old web remains compatible. Rollback disables mobile routing before reverting identity tables; never roll back financial records. Use server revision conflicts, bounded Room read cache and no offline financial commands. Full cross-entity change tracking and durable research jobs require further server contracts; document missing capabilities rather than manufacture success.

Expected changes: android/**, docs/android/**, docs/architecture/{MULTI_DEVICE_SYNC,MACOS_COMPATIBILITY_REQUIREMENTS}.md, src/pocket_alpha/mobile/**, main.py, migration imports/new additive migration, tests/test_mobile*.py, explicit mobile deployment proxy and Android CI. No change to financial engines.

Acceptance: real compile/build, unit+API regression and device/integration evidence; HTTPS-only native traffic, no plaintext credentials, inaccessible privileged routes; exact parity gaps and unavailable data remain visible. Never infer parity from screen count or passing mocks.
