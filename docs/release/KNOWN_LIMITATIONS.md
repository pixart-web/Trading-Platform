# Known limitations

- Real-money, native spot writes, real Autopilot and derivative dispatch are not ready and remain disabled.
- Economic edge is not established. Synthetic fixtures and mechanics tests do not prove profit, calibration or ruin limits.
- Public market import coverage is narrow; broad asset/provider, survivorship and corporate-action validation are incomplete.
- Backtest fill, latency, liquidity and cost behavior are explicit models, not venue guarantees.
- Authenticated exchange read-only qualification and broker sandbox/conformance are absent.
- Minimal bcrypt Basic Auth is for one operator; no SSO, MFA, roles or multi-tenant isolation exists.
- No application-native rate limiter/WAF, metrics, distributed tracing or error-reporting service is configured.
- Base image family tags are mutable. Record resolved digests for every deployment and retain Trivy evidence.
- Production encrypted off-server backup/restore and disaster-recovery timing require operator infrastructure and a recorded drill.
- Private SQLite journals are hash-chained but plaintext and not externally anchored; any later use requires encrypted storage, ACLs and off-server integrity evidence.
- The audit workstation Docker daemon was unavailable due host-local socket corruption; Linux CI is authoritative for service/container gates.
- FastAPI/httpx test tooling emits two upstream deprecation warnings; migration to the upstream-recommended client is tracked debt.
