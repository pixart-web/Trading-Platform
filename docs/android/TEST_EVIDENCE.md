# Android candidate test evidence

Recorded 2026-11-07. Synthetic fixtures prove mechanics and contract behavior, not economic value, live-provider availability or trading qualification. No full phase-level Android parity is claimed.

## Local checks actually executed

| Check | Result | Scope |
|---|---|---|
| Ruff check / format | PASS | Entire repository Python source |
| Strict mypy | PASS | 269 source/test files |
| Python regression | 1097 passed, 233 skipped | Skips require opt-in PostgreSQL/Redis; no failed tests in this run |
| Focused PostgreSQL/Redis regression | 46 passed | Native auth, expiry/rotation/replay, step-up/idempotency, real Redis rate admission, snapshot discovery, watchlist archival, migration roundtrip/head check |
| Complete remote PostgreSQL/Redis run | 1329 passed, 1 skipped; 91% coverage | First candidate CI backend job passed; later CI corrections affect SDK setup, checksum metadata and web Zod/lint |
| Kotlin behavioral tests | 7 passed | HTTPS origin validation, exact formatting, path traversal rejection, candle identity/OHLC validation, Analyze identity and typed pagination/permission transport |
| Android lint | PASS | Strict correctness warnings/errors; dependency-version suggestions informational |
| Debug + optimized unsigned APK + AAB | PASS | Gradle dependency verification enabled; no production signing key |
| OSV Maven runtime audit | 107 packages, zero known affected packages | Runtime coordinates, not every build-tool dependency |
| pip-audit | PASS, zero known vulnerabilities | Both Python locks after certifi 2026.10.18 remediation |
| Bandit | PASS, zero medium/high findings | src/ |
| Secret gate | Audited | No new secret fingerprints; narrow generated-checksum exclusion and explicitly invalid fixture annotations |

## Real native HTTPS device path

One disposable ARM64 API 35 emulator was run with four viewport configurations, not four physical devices:

| Configuration | Pixels | Density | Result |
|---|---|---|---|
| Compact phone | 720 × 1280 | 320 | PASS |
| Standard phone | 1080 × 2400 | 420 | PASS |
| Large phone | 1440 × 3120 | 480 | PASS |
| Tablet | 1600 × 2560 | 240 | PASS |

`BackendWorkflowTest` used the actual Android app, HTTPS, Retrofit/OkHttp, FastAPI, PostgreSQL and Redis. It signed in, read registered synthetic candles with valid quality, navigated Analyze/Scanner/More, created a server watchlist, added a market, renamed it, removed the market, archived/deleted the list, recreated the activity and verified return to sign-in after revocation from an independently authenticated second session. The test TLS root was injected only into the disposable debug variant for localhost. The final standard builds exclude it. The fixture provider and screenshot labels say SYNTHETIC-E2E; no illustrative reference-image financial values were used.

Eight captures (overview and chart in each configuration) are in screenshots/. They show the tested layouts and explicit source/freshness states. They do not establish complete visual acceptance, physical-device performance, real market coverage or every financial workflow. Subsequent copy wording may clarify freshness without changing the tested routing/contracts.

## Failures investigated and resolved

- Unaligned candle requests generated honest quality errors. The client now discovers the latest stored closed candle and requests its exact bounded historical window; age at fetch is distinct from integrity.
- Compact-screen tests initially searched offscreen elements before asynchronous data arrived. Tests now scroll to semantic targets and wait for actual server-backed state. Refresh preserves list content.
- Native integration originally shared the E2E operator workspace and violated the intentional single-owner constraint. Each test now owns an isolated PostgreSQL schema; it never deletes another workspace to pass.
- Strict Gradle artifact verification identified missing lint/tool hashes. Their fixed official artifacts were recorded and the subsequent build passed in strict mode.
- pip-audit found PYSEC-2026-4320; both certifi locks were updated and re-audited successfully.
- The local backend-only Docker image built, but startup hit the pre-existing Docker VM disk limit. Only owned smoke containers/volumes/images and the base downloaded for that test were removed. Redis failed closed during the incident, then write admission recovered. Local standalone topology runtime acceptance was not completed; the remote container job subsequently passed its explicit no-Next.js/auth/exposure smoke.

- A deterministic concurrent PostgreSQL refresh test reproduced a token-family revocation race. The loser now rechecks consumed tokens in a fresh transaction after row-lock contention; both replay and concurrent regression tests pass.
- Tablet overview grid children overlapped. Grouping each logical grid item fixed the layout; instrumentation now checks title/subtitle and field/button bounds, and all four viewport runs passed.
- Tiny market prices could round to zero in labels. Exact price labels and a six-significant-digit axis formatter now have a dedicated regression test.

## Unexecuted / incomplete acceptance

Physical Android devices; full TalkBack/font scaling/keyboard/landscape; actual process death rather than activity recreation; comprehensive offline/reconnect/revocation endurance; real-provider portfolio/PAPER/research execution; native research submission; full synchronization/realtime/push; performance profiling; production signing/store/deployment. Backtest/research APIs currently only retrieve existing artifacts.

## Remote CI

Branch `codex/android-native` is published. The [first candidate run](https://github.com/pixart-web/Trading-Platform/actions/runs/42380980662) passed the complete backend (1329 passed, one skipped, 91% coverage) and container jobs, including the real standalone native topology/authentication/exposure smoke. It exposed SDK PATH, missing Linux metadata, pre-existing web lint and Zod dependency findings. These were remediated, and Zod 4.6.6 was re-audited with no known vulnerabilities. Local web lint/typecheck, 71 unit tests, production build and 21 authenticated Chromium E2E tests passed. Existing E2E tests were updated to use real PIN authentication and current English UI labels; a new test verifies rejection without session and secure cookie attributes. A clean Gradle cache resolved the missing parent POM, and all build gates subsequently passed again with strict verification. A subsequent XML checksum annotation syntax error was also corrected and Gradle revalidated. The final pushed run must still be observed; no full green remote CI claim is made in this record. Final observed run/SHA is included in the delivery response. All existing backend/frontend/security/container jobs remain, with Android build/audit and device jobs added.

## Reproducing native E2E

`tests/native_e2e_seed.py` is an explicit test-only fixture entry point. It refuses non-test environments, enabled live/derivative gates, non-localhost hosts and any database name other than `pocket_alpha_native_e2e`; it refuses to replace a different provisioned operator. It is not imported by application startup or packaged into the runtime image. The complete disposable PostgreSQL/Redis, TLS, emulator and instrumentation commands are in the `android-device` job of `.github/workflows/ci.yml`. That job now runs the real backend workflow instead of treating it as an unconfigured skip. Its TLS-enabled test APK is not the distributable standard debug/release artifact.

## Target SDK and remote evidence collection

The original local four-viewport captures used API35. Remote lint identified its outdated target; the candidate compile/target baseline is now API36. The official SDK repository queried locally supplied API36 but did not supply `platforms;android-37`, despite newer Android documentation. API37 qualification is therefore not claimed. The API36 device job must be observed separately.

On the earlier API35 remote run, both instrumented tests passed (zero skipped), but Gradle removed the installed test app before the separate screenshot pull, deleting app-specific external files. CI now uses the same direct `adb am instrument` flow proven locally, requires the explicit `OK (2 tests)` sentinel, and collects images before runner cleanup. This preserves the functional test gate instead of ignoring missing evidence.
