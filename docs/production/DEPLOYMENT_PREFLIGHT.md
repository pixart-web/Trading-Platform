# Deployment preflight

`deploy/scripts/preflight.sh` is read-only. It requires Docker/Compose, non-example DNS, a bcrypt hash, four non-empty secret files, valid Compose interpolation, live flags fixed to false and exactly the three Caddy port publications.

Before an approved deployment also confirm: clean signed/tagged release revision; green CI; resolved image digests recorded; zero critical Trivy findings; one Alembic head; current backup plus restore drill; 80/443 firewall policy; TLS/DNS propagation; sufficient disk/inodes; UTC/NTP; log rotation; external HTTPS/readiness probes; alert receiver; rollback revision; operator window and incident contact.

Failure of any dependency means not ready. Never bypass a failed preflight by editing Compose on the server.
