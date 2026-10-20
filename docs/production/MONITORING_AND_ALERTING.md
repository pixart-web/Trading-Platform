# Monitoring and alerting

Native probes are liveness/readiness, Docker healthchecks, structured application logs and Caddy access/error logs. Before public operation configure external HTTPS probes, centralized log shipping, host/container CPU-memory-disk-inode monitoring, PostgreSQL connections/storage/backup age, Redis availability, certificate expiry, restart counts and provider-data freshness.

Page immediately on authenticated endpoint failure, readiness failure over two intervals, database unavailable, backup older than 24 hours, disk above 85%, repeated restarts, certificate under 14 days, execution UNKNOWN/reconciliation failure or any unexpected live-enabled setting. Ticket on elevated latency, provider staleness, storage growth and dependency advisories.

The repository does not bundle a vendor-specific metrics stack or alert receiver. This is a deployment prerequisite, not a claimed pass. No alert should include credentials, order secrets or full financial payloads.
