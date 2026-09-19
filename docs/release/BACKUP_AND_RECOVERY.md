# Backup and recovery

## Assets

| Asset | Method | Frequency | Retention |
|---|---|---|---|
| PostgreSQL | `pg_dump --format=custom`, encrypted before off-server copy | daily and before every migration | 7 daily, 5 weekly, 12 monthly |
| Private spot/derivative journals | filesystem snapshot after quiescing writer; encrypt and hash | at least daily and before release/incident work | match PostgreSQL retention |
| Deployment configuration | approved Git SHA plus encrypted secret-manager export/escrow | each change | current plus previous working release |
| Research/model artifacts | content-addressed archive with dataset/model hashes | when sealed/registered | immutable for governance lifetime |
| Redis | normally rebuild from durable state; AOF volume is operational convenience | optional snapshot | short, never sole ledger backup |

Backups must use authenticated encryption, a separate key store, checksum/hash manifests, owner-only staging permissions and an off-server/off-account copy. Monitor backup age and copy failure. Never place broker credentials or plaintext database URLs in Git or logs.

## PostgreSQL backup

Run inside the trusted Docker network and write to protected host staging:

```sh
docker compose -f compose.production.yaml exec -T db \
  pg_dump -U pocket_alpha --format=custom pocket_alpha > pocket-alpha.dump
```

Encrypt, hash, copy off-server and remove plaintext staging after verification.

## Restore rehearsal

1. Provision a new disposable database/volume; never overwrite the source first.
2. Validate dump nonzero size and decrypt/check hash.
3. `createdb` a distinct restore database.
4. Run `pg_restore --exit-on-error` into it.
5. Verify expected public tables, Alembic revision, audit rows and representative immutable/accounting records.
6. Start API against the restored database and disposable Redis; require readiness and read smoke.
7. Record duration, recovered timestamp and evidence; destroy disposable data.

CI performs steps 3-5 on every change. A production operator must perform and record the full encrypted off-server rehearsal before deployment and quarterly thereafter.

## RPO/RTO

Initial target: RPO ≤24 hours plus pre-migration backups; RTO ≤4 hours for the limited research/PAPER service. These are operational objectives, not demonstrated guarantees, until a timed external-host drill is recorded.
