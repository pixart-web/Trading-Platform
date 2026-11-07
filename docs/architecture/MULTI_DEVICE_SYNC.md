# Android/macOS synchronization contract and implementation status

The existing PostgreSQL state is authoritative. Redis is coordination/cache. Android Room is a replaceable read cache, never a ledger or order authority. Manual, PAPER and broker-synchronized balances are separate domains. This release adds reusable native identity and documented OpenAPI, but does **not** implement a complete incremental synchronization protocol.

## Implemented

Stable server entity IDs, existing optimistic revisions for watchlists/manual portfolios, immutable accounting/report IDs and UTC timestamps remain unchanged. Native deletion archives a watchlist at an expected revision and preserves immutable history. Analyze snapshot discovery uses bounded keyset cursors (as-of/report identity). Authentication supplies hashed rotating credentials and per-device revocation for the single existing operator workspace. Android caches bounded reads by origin/user/request, labels offline timestamps and refuses permission/validation fallback. WorkManager only polls permitted read state; it does not keep server jobs alive. Financial edits are explicit online operations with stable IDs and no blind transport retry.

## Required before shared sync readiness

A transactionally committed change/outbox feed must cover preferences, watchlists/tombstones, portfolios/entries, research jobs, strategies, forecast history, scanner settings, notifications, PAPER, execution and risk read models. Allocate cursors with commit-safe ordering: a naive increasing database sequence can skip a transaction that commits late. Define retention, expired-cursor full recovery and versioned snapshot contracts. Every event carries entity/type/ID/revision/server timestamp, not secrets. Snapshot installation and cursor advancement must be atomic on each client.

Immutable financial records, order states and risk controls never use last-write-wins. The server rejects stale edits and returns current revision/conflict context. Idempotency keys bind actor, operation and canonical request hash; retrying a key with different content must conflict. Only explicitly allowed non-financial drafts/preferences may be queued offline; each needs ownership, expiry and reviewable conflict handling. No offline real-money command may be queued for later execution.

Realtime SSE/WebSocket delivery is an optimization over durable cursors, not the source of truth. Authenticate streams, bound buffers, carry sequence/resume identity, detect staleness, reconnect with backoff and recover a server snapshot on gaps. Notifications are advisory and must never implement risk control. Neither this stream nor the full change feed is implemented yet.

A future macOS client must use the same identity, server revisions and financial boundaries. It must not infer success from Android cache contents, merge account balances, send credentials to brokers or depend on either client remaining open. Readiness remains NO until two independently running clients pass conflict, revocation, offline and snapshot-recovery integration tests.
