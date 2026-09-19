# Phase 26–29 security audit at Phase 29

## Reviewed surfaces

This audit covers read-only broker observation, spot execution, Autopilot and derivative execution,
plus repository API/proxy, secrets, dependency, container and filesystem/network controls. It is a
source and local-test audit, not a penetration test or authenticated venue certification.

## Findings and controls

- Credential scope and withdrawals: Phase 26/27 native Spot code uses excluded SecretStr fields,
  pins expected account identity and rejects unapproved permission flags. The derivative boundary has
  no credential type or native client. Its account fixes withdrawal_permission=false; its default
  broker has no transfer or withdrawal method. No derivative credential, withdrawal, transfer or
  universal-margin endpoint exists.
- Secrets in Git, logs and frontend: tracked configuration contains development-only local database
  values and false enable flags. Broker secrets are environment-only, excluded from representation
  and absent from new journals, reports, tests and docs. HTTP logs contain correlation ID and status.
  Frontend proxy tests strip arbitrary query tokens. Phase 29 adds no secret.
- Authentication and authorization: Phase 29 adds no HTTP, CLI or UI surface. Existing analytical
  FastAPI routes remain unauthenticated and Compose binds them to loopback. They must not be exposed
  to the internet without identity and authorization. No route enables derivative execution.
- CSRF, CORS, redirects, SSRF and injection: Phase 29 has no browser or HTTP request path. The
  application installs no permissive CORS middleware. Existing frontend upstream construction uses a
  fixed base, path allowlists, credential rejection and redirect:error; public data transport rejects
  cross-origin redirects. SQLite writes are parameterized. Pydantic validates bounded values and
  journal JSON is never evaluated. No shell, template, SQL interpolation, dynamic import, eval or
  exec was added.
- Rate, replay and ambiguity: policy bounds minute/day submissions. Deterministic client IDs, full
  request hashes, an account-wide unresolved-flow gate and append-only journal prevent ordinary
  replay. PREPARED/UNKNOWN is never submitted again. Not-found and transport errors remain UNKNOWN.
- Dependency and supply chain: Phase 29 adds no dependency or lockfile change. Runtime images use
  Python 3.12 slim and a non-root UID. PostgreSQL, Redis, API and frontend ports bind to loopback.
  Python installs from the lock without cache. Version-major image tags are not immutable digests and
  remain deployment debt. External vulnerability-database scanning remains a release requirement.
- Filesystem and network: the derivative module has no network client. Its journal is account/origin
  pinned, transaction-serialized, size-bounded and hash-chained. It is plaintext and not externally
  anchored; production needs a private directory, restrictive ACLs, encrypted storage/backups and an
  external append-only anchor.
- Failure behavior: REAL origin, missing health/qualification, stale or mismatched evidence,
  unsupported instruments, permission ambiguity, report regression, unvalued fees and clock reversal
  fail closed. Exceptions become static reason codes; credential or upstream response text is not
  persisted.

## Residual risks and release blockers

Real derivative trading remains blocked. Before any later enablement: perform authenticated read-only
venue qualification; validate exact contracts, filters and margin tiers; review a least-privilege
trade key with every withdrawal/transfer permission disabled; independently acquire account and loss
state; add operator authentication/authorization, alerting and external journal anchoring; scan
dependencies; pin production images; run broker sandbox/venue conformance and a manual incident and
reconciliation exercise. Existing unauthenticated analytical APIs must remain local or gain access
control before external deployment.

No critical vulnerability was introduced by Phase 29 under its synthetic-only reachable surface.
This does not certify the whole application for public or live deployment.
