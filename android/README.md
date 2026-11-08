# Pocket Alpha Android

Native Kotlin/Compose integration candidate; no WebView or local trading engine.

Use JDK 21, Android SDK 36/build-tools 36.0.0 and the included Gradle Wrapper:

```sh
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleRelease :app:bundleRelease
```

See [build/install](../docs/android/BUILD_AND_INSTALL.md), [architecture](../docs/android/ANDROID_ARCHITECTURE.md), [test evidence](../docs/android/TEST_EVIDENCE.md) and [release gaps](../docs/android/RELEASE_READINESS.md). Current status is an integration candidate with incomplete full functional parity. A private HTTPS backend and provisioned native operator are required. No signing secret or broker credential belongs in this directory.

## Current application entry

The launcher now opens the local workspace, without Pocket Alpha server credentials. Public Coinbase HTTPS is used for actual EUR spot H1 history. Manual single-market PAPER experiments and Settings → portable encrypted backup operate locally. Settings can open the optional legacy server client; it is no longer required for startup. Automated strategy/PAPER autopilot, consolidated multi-market cash and UTC day rollover remain unavailable. See docs/tablet/LOCAL_WORKSPACE.md and RELEASE_READINESS.md before evaluation. Real-money execution remains disabled.
