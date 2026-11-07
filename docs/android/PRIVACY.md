# Native candidate privacy and data handling

This document describes implemented behavior, not a published store privacy declaration.

The app connects to the HTTPS Pocket Alpha origin chosen by the operator. It does not embed broker credentials, connect directly to brokers, include advertising analytics or register with a remote push provider. Market-provider access and financial processing remain on the server. The backend receives the operator login, device model label, session activity and explicitly submitted workspace edits. It stores a password hash and hashed session credentials, not their plaintext values.

Android stores a rotating refresh credential and session/user IDs in a Keystore-encrypted no-backup file. Access credentials remain in memory. Room stores previously requested analytical/accounting snapshots inside the app sandbox; these snapshots are not encrypted separately from platform/device storage. Credentials are not stored in Room/DataStore. DataStore retains the configured non-secret server origin. Cloud backup and device transfer are excluded, and production screens set FLAG_SECURE. Logout/revocation clears local credentials and cached data; offline logout explicitly warns if server revocation could not be confirmed.

The server remains responsible for database encryption, backups, retention and operator access. Revoked/consumed session records are retained for replay/audit purposes; automated retention and account-erasure administration are not implemented by this candidate. Watchlist deletion archives the active list while preserving immutable analytical/alert history. No client can rewrite financial execution journals or silently merge manual, PAPER and broker balances.

Notification permission is optional. Native channels are present, but remote registration/delivery is not implemented. No remote push payload or provider token is collected. Before public distribution, the operator must finish retention controls, provider/privacy notices, store data declarations and the remaining security/device acceptance work described in RELEASE_READINESS.md.
