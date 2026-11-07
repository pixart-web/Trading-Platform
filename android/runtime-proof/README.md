# Isolated CPython Android experiment

This is a separate Gradle build, never included by android/settings.gradle.kts and never shipped as part of the Pocket Alpha production APK. No INTERNET permission, local HTTP server, broker or account data. Chaquopy 17.2.0, CPython 3.12 (resolved target 3.12.15-0), AGP 8.9.2, min26/target36, arm64-v8a + x86_64. Dependency locks and verification metadata are checked in.

From android/, with JDK21, Python3.12 and SDK36:

```
./gradlew -p runtime-proof --no-daemon :probe:assembleDebug
```

The default build requires exact production Pydantic2.13.5/core2.46.5. The observed packaging failure is `No matching distribution found for pydantic-core==2.46.5` on ARM64. Never downgrade validation or interpret this as proof that custom cross-compilation is impossible.

For a separately labelled standard-library compatibility/timing probe only:

```
./gradlew -p runtime-proof --no-daemon -PprobeStdlibOnly=true :probe:assembleDebug
adb install -r runtime-proof/probe/build/outputs/apk/debug/probe-debug.apk
adb shell am start -W -n pt.pocketalpha.runtimeproof/.ProbeActivity
adb logcat -d -s PocketRuntimeProof:I
```

This variant intentionally does not package Pydantic; missing imports are expected and `financial_engine_qualified` remains false. Its success proves neither financial-kernel compatibility nor validation equivalence. The Kotlin fallback is independently tested against the unchanged CPython oracle.

A custom core wheel would require pinned Rust/PyO3/maturin and NDK clang toolchains for aarch64-linux-android and x86_64-linux-android, CPython3.12 target headers/sysconfig and compatible Android wheel tagging. Host wheels cannot be relabelled as Android. No custom native wheel was built or audited in this checkpoint: maintaining, patching and qualifying both ABIs fails the current supported-wheel/reproducibility gate. Reconsider embedding only after that pipeline passes full domain imports, golden tests, provenance and maintenance review. The explicit bounded fallback avoids making the product depend on an unqualified native fork.
