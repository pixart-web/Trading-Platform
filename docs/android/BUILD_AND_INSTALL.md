# Build and install

Application ID: `pt.pocketalpha.android`; version 0.1.0 / code 1. Minimum API 26 (Android 8), compile/target API 36. This is the documented candidate baseline, not a guarantee of current Play Store eligibility. JDK 21 runs Gradle 8.11.1; bytecode targets Java 17. AGP 8.9.2/Kotlin 2.1.20/Compose versions are pinned in the catalog; Room/Hilt use KSP. Gradle Wrapper includes the official distribution SHA-256 and dependency verification metadata/locks.

```sh
cd android
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleRelease :app:bundleRelease
```

Set `ANDROID_HOME` to a licensed SDK with API 36/build-tools 36.0.0. A local `local.properties` may supply sdk.dir and is ignored. Never commit SDK caches or signing material. Run standard builds without `e2eCaFile`.

Artifacts:

- `android/app/build/outputs/apk/debug/app-debug.apk`: installable development build.
- `android/app/build/outputs/apk/release/app-release-unsigned.apk`: optimized release candidate, requires signing.
- `android/app/build/outputs/bundle/release/app-release.aab`: unsigned release bundle, requires signing/distribution qualification.

```sh
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Backend

Run additive migrations before enabling the mobile route. Provision the single operator using `python -m pocket_alpha.mobile.provision`; password entry uses getpass. The existing web PIN/cookie login is not a native refresh credential. Set PA_MOBILE_API_ENABLED=true in the combined topology, or use `compose.native.yaml` for a backend-only topology. Configure a real TLS domain, private Docker secret files, database backup and operational monitoring. API origin entered into Android is `https://your-domain` (the client appends `/mobile/`). Do not publish the original unauthenticated internal API, database or Redis ports.

## Secure release signing

Use an operator-owned signing key kept outside the repository, preferably protected in secure signing infrastructure. Use Android `zipalign` then `apksigner sign --ks /secure/operator-release.jks` and `apksigner verify --verbose --print-certs`. Enter passwords interactively or via a protected CI secret mechanism. Sign the AAB using the approved Java/Play signing workflow and verify the certificate. No production key has been generated or committed by this work.

Installation of an unsigned APK is not supported. Play listing/privacy/review, signing credentials, update distribution and production endpoint provisioning remain external release work. Reuse one signing identity and increment versionCode for updates; never present this candidate as a store release.

## Migration and rollback order

Back up the database, apply migrations 0017/0018, then deploy the new API image and enable the native route. The new API references additive columns even when native routing is disabled. Disable the native route to contain a client issue. Prefer a forward fix and retain the additive schema during rollback; an older API may expose archived watchlists again. Do not blindly downgrade populated identity/session tables or remove the archive column in production. Test recovery against a restored backup first.
