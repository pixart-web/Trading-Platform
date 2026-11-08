# Native operational integration evidence

Observed on 2026-11-08 on a disposable API 35 ARM64 emulator, 2560×1600 landscape, without a Pocket Alpha backend. This is operational integration of the manual PAPER slice after baseline `fb68ababa0193c25ae59b09c4098b5d62d63c8e4`, not full strategy/autopilot acceptance.

- Final launcher/provider/portable tests: **3 passed**, including real HTTPS BTC-EUR product metadata, 240 closed H1 candles, qualified local SMA and creation/restoration of 1,000 EUR virtual cash. Production default launcher entered the local workspace and its actual account-creation control was exercised. [Raw output](evidence/operational-2026-11-08/public-android.txt), [provider observation](evidence/operational-2026-11-08/public-provider.txt).
- Exact Python golden vectors, atomic journal import and concurrency: **2 passed** in create phase. Recovery in a separate instrumentation process: **1 passed**, including deliberate disposable-journal corruption rejection. [Create](evidence/operational-2026-11-08/core-create.txt), [recover](evidence/operational-2026-11-08/core-recover.txt).
- Device-key loss: **1 passed**, run last because it intentionally invalidates the disposable app key. Original unreadable accounts remained visible as unavailable; password backup restored independently. [Output](evidence/operational-2026-11-08/key-loss.txt).
- Legacy login UI and portable restore separately passed **2 tests** before the final visual-only contrast adjustment. Full legacy server workflow and x86_64 paths are required in final CI; the delivery response records its actual observed SHA/run/result.
- Final JVM suite: **14 passed**. Debug lint, debug/test APK, release APK and release bundle build succeeded. Ruff check/format, mypy (272 files), oracle generation, schema and local-engine source checks passed. OSV: 107 runtime packages, 0 affected; pip-audit: no known vulnerabilities; Bandit: no findings at configured severity.
- Local Python suite: **1,097 passed, 233 skipped**, two warnings; service-dependent cases require PostgreSQL/Redis CI. This is not a claim that skipped tests passed.

The real provider initially returned 350 rows against a 300-row assumption. The adapter now requests and filters an explicit 240-hour window with an independent 1,024-row/2 MiB normalization bound. No interpolation or synthetic operational candles were used. Public outages produce unavailable state. The real-provider test requires explicit `realProvider=true`; deterministic CI does not depend on external market availability.

[Final landscape capture](screenshots/real-market-landscape.png) was inspected after fixing title contrast. It shows actual historical data and source/receipt timestamps, not live bid/ask. The image precedes account creation in that test. Screenshot security is cleared only by test code.

No physical Redmi, autonomous real-data strategy, multiple positions/shared cash, biometric gate, UTC day rollover or complete standalone E2E acceptance has been verified. No market profitability or real-money authorization is claimed.
