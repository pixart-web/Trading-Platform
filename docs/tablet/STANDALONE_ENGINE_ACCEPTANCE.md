# Standalone engine foundation acceptance

This is a real local deterministic engineering harness, not a complete tablet application or live-market strategy qualification. The connected Compose application is preserved; no server dependency has been disguised as standalone operation.

## Reproduction

Build `:app:testDebugUnitTest :app:lintDebug :app:assembleDebug :app:assembleDebugAndroidTest`. Install both debug APKs on a disposable emulator. No Pocket Alpha backend needs to be started. Run:

```
adb shell am instrument -w -r -e class pt.pocketalpha.LocalStandaloneEngineTest -e localPhase create pt.pocketalpha.android.test/androidx.test.runner.AndroidJUnitRunner
adb shell am force-stop pt.pocketalpha.android
adb shell am instrument -w -r -e class pt.pocketalpha.LocalStandaloneEngineTest -e localPhase recover pt.pocketalpha.android.test/androidx.test.runner.AndroidJUnitRunner
```

Each invocation must say `OK (1 test)`. Use a fresh disposable test installation: the fixture owns fixed UUIDs and refuses to overwrite an existing experiment. Recovery deliberately corrupts its test journal only after successful reconciliation to verify fail-closed behavior; do not run this harness against user experiments. No production data-reset capability was introduced.

Create initializes a Keystore-encrypted1000 EUR fixture account, executes the scripted decision through risk admission and persists the first partial fill. It also checks idempotency/revisions/concurrent writers on a second fixture account. Force-stop ends the process. Recover opens the same database, reconstructs the outstanding order and position, explicitly processes the remaining scripted observations, checks the exact Python final balances, then tests tamper rejection. This explicit test continuation is not automatic background order resubmission.

## Verdict scope

| Verdict | Current interpretation |
|---|---|
| PYTHON_ANDROID_RUNTIME_QUALIFIED | NO: exact native core wheel cannot be resolved; only stdlib runtime measured |
| KOTLIN_FINANCIAL_FALLBACK_QUALIFIED | YES within the bounded golden-vector scope; not the complete Python platform |
| LOCAL_FINANCIAL_KERNEL_READY | YES for the foundation only: listed decimal/indicator/risk/simulation subset; not complete engines |
| LOCAL_PAPER_LEDGER_READY | YES for the foundation only: encrypted transactional events and reconstruction; not portable restore or production acceptance |
| ANDROID_STANDALONE_DEMONSTRATION | YES for the isolated engineering harness: create + force-stop + recovery passed without backend; final run is reported with delivery |
| REAL_MONEY_TRADING_ENABLED | NO: no dispatch/broker transport exists in the local kernel |

Final boolean verdicts and SHA are provided after observing the final CI. Remaining product blockers include real provider adapters, arbitrary strategy qualification, multi-market/order support, day-rollover/reconnect lifecycle, explicit active-tablet scheduling, biometric lock, encrypted portable export/restore, tablet presentation and Redmi hardware endurance tests. Production readiness remains NO even when this foundation's demonstration passes.

## Local acceptance achieved

The final ARM64 create/recover invocations passed without starting a backend, in separate Android processes. Exact fixture final cash is997.51274875 EUR and inventory/basis zero. The shared financial comparisons also execute inside both instrumentation phases. Financial foundation verdicts can be YES only within the documented one-market/one-pending-order, synthetic-harness scope; complete tablet/product readiness remains NO. Final CI and x86_64 observations are reported in the delivery response.
