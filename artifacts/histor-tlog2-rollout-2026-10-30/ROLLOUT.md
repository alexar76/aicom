# HISTOR histor-tlog/2 rollout — 2026-10-30

Change: commit 612b37c9a (main) — C2SP checkpoint for the log's head, the instance as a
c2sp.org/tlog-witness, `python -m histor witness-submit`, migration 017.

Run by the owner on admin-vps (the auto-mode classifier refused it to the agent):
`bash /root/tlog2-20261030/histor_tlog2_overlay.sh`, 06:06–06:09Z.

| Item | Value |
|---|---|
| Base (running before, now `histor-histor:pre-tlog2-20261030`) | `3519cee8e02f` (app == cbb84563d, 48 files) |
| New image `histor-histor:tlog2-20261030` | `b92c69562e53`, container started 06:09:30Z |
| MOMUS release gate | passed, receipt 20261030T032741 (WARDEN unchanged) |
| MOMUS quality binding | rebound to `b92c69562e53`, tagged `histor:warden-remediation-base` |
| Dump before | `/var/backups/histor/histor-20261030T060643Z.dump` |
| Schema | 17 (`witness_logs`, `cosignatures`, both empty) |
| Crawl | was running, restarted after the swap |
| Key backup | `keys-20261030T061204Z.tar` contains `data/issuer.key` and `data/witness.key` |

Overlay = nine files over the running image: `checkpoint.py`, `witness.py`, `cosign_cli.py`
(new); `app.py`, `store.py`, `service.py`, `config.py`, `migrations.py` (branch == live + this
change); `__main__.py` (the live file with only this change applied).

## Verified afterwards (from outside, 2026-10-30 ~08:30Z)

- `GET https://histor.modelmarket.dev/checkpoint` → origin `histor.modelmarket.dev/log`, size
  1288341, root `LDo6h5Dw…/w6k=`, one log signature line.
- The note verifies with the reference Go implementations (`golang.org/x/mod/sumdb/note`,
  `github.com/transparency-dev/formats/note`) under the vkey the issuer document publishes:
  `histor.modelmarket.dev/log+ad3ca066+AfXpkWqXVW93sChXnhKsNzvGLTFAAredl1jLlEjbr4wU`.
- The checkpoint's size and root equal `/api/v1/log/sth` at the same moment.
- Witness: `histor.modelmarket.dev/witness+87df9f83+BHmgo3SRWlaehFMgWBDIOWFgs1V2YQS+ufBcg/ht6kw/`;
  `POST /witness/v1/add-checkpoint` with a malformed body → 400 with the specification's reason;
  `knownLogs` is empty (no `HISTOR_WITNESS_LOGS` yet), so every real submission is a 404.

## Rollback

```
docker exec histor-histor-postgres-1 psql -U histor -d histor -c "BEGIN; DROP TABLE IF EXISTS witness_logs; DROP TABLE IF EXISTS cosignatures; DELETE FROM schema_migrations WHERE version = 17; COMMIT;"
docker image tag histor-histor:pre-tlog2-20261030 histor-histor:latest
docker compose -p histor --env-file /opt/histor/.env -f docker-compose.yml -f docker-compose.postgres.yml up -d --no-build histor
```
then `skopos-warden-quality rebind` on the restored image. Do NOT roll back once a witness has
co-signed: the checkpoint origin and key are a promise to it.
