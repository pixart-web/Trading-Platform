# Pocket Alpha Android

Native Kotlin/Compose integration candidate; no WebView or local trading engine.

Use JDK 21, Android SDK 36/build-tools 36.0.0 and the included Gradle Wrapper:

```sh
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleRelease :app:bundleRelease
```

See [build/install](../docs/android/BUILD_AND_INSTALL.md), [architecture](../docs/android/ANDROID_ARCHITECTURE.md), [test evidence](../docs/android/TEST_EVIDENCE.md) and [release gaps](../docs/android/RELEASE_READINESS.md). Current status is an integration candidate with incomplete full functional parity. A private HTTPS backend and provisioned native operator are required. No signing secret or broker credential belongs in this directory.
