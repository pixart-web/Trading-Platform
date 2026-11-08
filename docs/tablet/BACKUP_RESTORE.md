# Portable encrypted backup

Settings exports the selected reconciled experiment through Android's document picker. Export decrypts the device journal only in memory, then applies an independent PBKDF2-HMAC-SHA256 key (600,000 iterations,16-byte random salt,256-bit key) and AES-GCM (12-byte random IV). The fixed version/salt header is authenticated. The Android Keystore key is never exported. Use a strong unique password; minimum12 characters is not a strength guarantee.

Restore reads at most8MiB plus envelope overhead, authenticates the password/ciphertext, validates version/budgets and creates a new UUID. Header, events and head are inserted in one SQLite transaction, then the entire chain and financial reconstruction are verified before commit. Wrong passwords, modified ciphertext, invalid head/state or cancellation roll back the import. Existing experiments are preserved. Operational import explicitly rejects synthetic fixture origins.

Device-key loss leaves original accounts unreadable; no new balances replace them. Such records are retained and reported. A password-protected portable backup can restore a new experiment under the current device key independently. At most100 experiments are accepted; journals remain bounded to10,000 events/4,096 event bytes, and portable exports to8MiB. Oversized exports fail rather than truncate history.

Tests cover roundtrip, password failure, modified ciphertext, modified journal, interrupted transaction, synthetic-origin rejection and device-key loss. They do not establish resistance to rollback of an entire older valid backup, password reuse/guessing, compromised/rooted devices or physical power-loss endurance. Biometric application gating is not implemented; production security acceptance remains incomplete.
