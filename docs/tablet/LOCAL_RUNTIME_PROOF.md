# Local runtime proof

Scope: financial foundation, not complete standalone tablet product. Baseline b2b6390; existing server client remains intact.

## Embedded Python experiment

`android/runtime-proof` is outside the production graph. Default build pins Chaquopy17.2.0, Python3.12 and exact Pydantic2.13.5/pydantic-core2.46.5. Actual pip resolution for ARM64 fails: `No matching distribution found for pydantic-core==2.46.5`. No validation was downgraded. A supported-wheel and reproducible-maintenance gate therefore selects the bounded Kotlin fallback; it does not assert custom NDK/Rust compilation is impossible. Toolchain requirements and reproducible commands are in the experiment README. No custom core wheel is qualified.

A separately labelled stdlib-only APK (no INTERNET permission) actually executed on an API35 ARM64 emulator. It reported CPython3.12.15, aarch64, successful decimal/sqlite3 imports, absent Pydantic/core, and `financial_engine_qualified=false`. First Python start + probe: 399ms; probe body: 21.8ms; PSS at report: 53,879KB; later dumpsys PSS: 68,491KB. These are single emulator measurements, not hardware benchmarks, peak-RAM measurements or an endurance qualification. The absence of Pydantic in this variant is intentional, not a second runtime compatibility test of the exact package.

The dedicated `android-local-engine` CI job executes the equivalent stdlib probe on x86_64. Its final observed run/SHA is reported with delivery. CPython financial execution remains unqualified regardless of stdlib success.

## Kotlin runtime

`pt.pocketalpha.local` has no HTTP, provider, broker, Activity or navigation dependencies. Decimal80 uses BigDecimal with explicit 80-digit HALF_EVEN operations. The financial authority is exposed by `LocalFinancialAuthority`; Room/Keystore persistence is injected by construction. Real broker dispatch is absent.

Supported scope is deliberately limited: one fixture EUR market, one outstanding spot LONG order, zero latency, bounded SMA/EMA, explicit complete-bar-close simulation, partial participation fills, fee-inclusive moving-average basis and realized P&L, risk checks, encrypted event replay. No FX conversion is implied: fixture prices are synthetic quote units labelled EUR. Repeated bars, future inputs, conflicts, stale data, suspension/kill and crossing a UTC day without a qualified rollover procedure fail closed. Suspended experiments cannot automatically resume or submit missed orders.

Not qualified: complete technical engine, forecasting, strategy registry, multiple concurrent orders/markets, real provider admission, rolling-day counters, execution in Doze, process-survival guarantees, production UI, portable encrypted backup or macOS synchronization. No user-facing standalone readiness claim follows from this harness.
