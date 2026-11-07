# Standalone feasibility — 2026-11-07

Status: architecture investigation, not standalone acceptance. Source baseline c3b843f. The installed application still requires its private backend.

## Reproducible repository evidence

Run `python android/tooling/audit_local_engines.py --check` from the repository root. IMPORT_AUDIT.json records SHA-256 digests as eight big-endian 32-bit words and static imports for 177 Python modules, including relative import resolution. It counts 53 modules importing Pydantic, 89 importing SQLAlchemy, 22 FastAPI and 3 Redis. Counts overlap; an import is not a runtime compatibility verdict. Optional/type-only imports are conservatively included. Dynamic imports and native ABI compatibility require separate runtime tests.

The current paper runtime imports simulation, backtesting risk, technical intelligence and validated domain models. Replacing only its persistence is insufficient: its Pydantic/native dependencies must also run. The current production lock requires Python >=3.12 and pydantic_core 2.46.5. PostgreSQL schemas, Redis admission and FastAPI startup are not Android persistence/runtime contracts.

## Options evaluated

| Option | Benefit | Evidence / unresolved cost | Decision |
|---|---|---|---|
| Full Kotlin rewrite | Android lifecycle, BigDecimal, Room | No cross-language golden qualification; changes Decimal context and validation semantics | Reject blind rewrite; allow bounded ports only after golden validation |
| Embed complete backend | Maximum source reuse | Native wheels unqualified; server dependencies and operator HTTP surfaces inappropriate | Reject complete backend embedding |
| Hybrid native host + isolated Python kernels | Preserves causal financial source while Kotlin owns storage/providers/UI | Python/native ABI and Pydantic wheel compatibility remain unproved | Preferred investigation path, NOT approved production runtime |
| Kotlin ports + native persistence | Avoid native Python packaging if unavailable | Must qualify each port against unchanged Python including exceptional/rounding cases | Explicit fallback if embedded kernel proof fails |

## Package availability probe

On 2026-11-07 HTTPS GET of `https://chaquo.com/pypi-13.1/pydantic-core/` returned 404; SQLAlchemy's index also returned 404. The numpy index listed an ARM64 CPython 3.12 wheel. This demonstrates that connectivity worked and that the required native core was not found at the documented package index. It does NOT prove a custom Android build impossible, nor does a desktop import prove Android support.

Chaquopy documents Python 3.12 support and a separate Android wheel ecosystem: [runtime/plugin](https://chaquo.com/chaquopy/doc/current/android.html), [package guidance](https://chaquo.com/chaquopy/doc/current/faq.html). Never silently downgrade Pydantic or replace validation with dictionaries to obtain a green APK.

## Concrete unblock sequence

1. Build a disposable isolated Android runtime module, with Python 3.12 and exact native dependency versions for arm64-v8a and x86_64. Produce native core wheels using the supported Android build toolchain if necessary; audit licenses/source/hashes. Do not change the production app's dependency resolution until the probe passes.
2. Import only an allowlisted financial kernel graph, never main/mobile/broker/control API. Run existing causality/accounting/risk vectors inside Android, measure cold start, peak memory and bounded research duration, and compare canonical results with the CPython oracle.
3. If exact core packaging cannot be maintained, port only the bounded core using BigDecimal with explicit 80-digit HALF_EVEN context. Python-generated golden fixtures must cover partial fills, allocated basis, full exit, precision, fees, rejection, stale input and restart reconciliation before enabling it.
4. Replace journals with native SQLite transactions and revision/idempotency/hash constraints. Restore must reconstruct accounting and verify approvals, not trust a cached balance. No localhost HTTP server, PostgreSQL process, Redis process or Docker.
5. Gate standalone entry and account controls on the proven local engine. Preserve the existing backend client as a separate optional mode during migration. No fabricated initial analysis or missed executions.

No Android embedded-runtime timing, physical-tablet benchmark, local PAPER account, direct provider execution or standalone E2E result has yet been measured. Those are blocking acceptance evidence, not assumed capabilities.
