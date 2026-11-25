# Attested Memory: Agent Memory Atlas re-read fixes on attested, 2026-11-25 14:49:20Z

Fixes of main 445100fe7 for the four gaps Simon Strandgaard's re-read at 25d6b1a named
(neoneye/agent-memory-atlas a9b7c179f). Host attested, compose /opt/aicom/attested/attested-memory-hub.

| service | image now | over (rollback) |
|---|---|---|
| memory-market | `attested-memory-hub-memory-market:atlas2-20261125` (sha256:c8bd5fa1…) | `actorv2-20261125` |
| provenance-ledger | `attested-memory-hub-provenance-ledger:atlas2-20261125` (sha256:3d852250…) | `atlas-20261124` |

The six live files (market clients/reconcile_provenance/store, ledger store/app) were byte-identical to
main 9b765c44c before the change, so the overlays copy main's new files (`kit/`, host /root/am-atlas2-20261125).
Recreated with `docker compose up -d --no-deps provenance-ledger memory-market`; both healthy in 15 s.

Timer: `attested-provenance-reconcile.{service,timer}` in /etc/systemd/system (kit/systemd), hourly at :23 UTC.

## Checks (live, 14:49–14:52Z)

- `ledger_meta.heads_backfilled` set at 14:49:25Z (one last backfill, then never again).
- `reconcile_provenance --count`: 0 unattested. `--check`: 8 attested, 8 matching, 0 mismatched.
- All 8 ledger receipts verify (signer_key, chain_head, both signatures).
- memory.attest@v1 with the internal token and a buyer ref: a new `mem_` id → 403 "Memory Market units
  get their first receipt from the market"; an existing market chain started by another actor → 403;
  receipt count stayed 8.
- First timer run by hand: Result=success, both JSON lines in the journal. No tracebacks in the logs.

## Backup and rollback

`/root/hub-backups/am-atlas2-20261125T144858Z/`: docker-compose.yml + pg_dump of receipts,
receipt_heads, memories (8 receipts, 8 heads, 8 attested units).

```bash
ssh attested 'cd /opt/aicom/attested/attested-memory-hub && cp /root/hub-backups/am-atlas2-20261125T144858Z/docker-compose.yml docker-compose.yml && docker compose up -d --no-deps provenance-ledger memory-market && systemctl disable --now attested-provenance-reconcile.timer'
```

The `ledger_meta` table stays (the old code ignores it).

## Second batch: our own review, LIVE 2026-11-25 15:20:09Z

main 6ba17aacf (worktree commit c8ad78e57). Only memory-market changed: `attested-memory-hub-memory-market:atlas3-20261125`
(sha256:1c414b68…) over `atlas2-20261125`; five files (app, store, models, clients, aimarket), `kit3/`, host
/root/am-atlas3-20261125. Before the swap all 12 live `memory_market/*.py` were byte-identical to main 49ede5edb.

- only a `created` receipt marks a unit attested; payment/verification receipts keep it for reconcile;
- payment receipt: actor `memory-market:payment`, metadata `settlement` = sha256(order|tx|grantee), no buyer or tx in clear;
- receipts of non-public units: sha256 of each source_ref and parent id; verification receipt: `evidence_pack_ref` (hash);
- catalogue/search/`/v1/catalog/{id}`: `evidence_pack_id` only for callers who may read the unit;
- owner revoke: `DELETE /v1/memories/{id}/grants/{grantee}`, `memory.share@v1` `revoke: true`; paid access stays;
- README: no "poisoned memory is caught" claim.

Checks live 15:20–15:22Z: healthy in 8 s; `--check` 8/8 matching; manifest `memory.share@v1` has `revoke`; deployed code
on a throwaway SQLite store: grant → readable, revoke → not readable; private source ref → `sha256:…`. Ledger: 0 of 8
existing receipts carry refs, parents or metadata (nothing exposed before). Prod data: 8 private units, 0 grants,
0 payment orders. No errors in the log.

Backup `/root/hub-backups/am-atlas3-20261125T151953Z/` (compose + pg_dump of memories, grants, payment_orders). Rollback:

```bash
ssh attested 'cd /opt/aicom/attested/attested-memory-hub && cp /root/hub-backups/am-atlas3-20261125T151953Z/docker-compose.yml docker-compose.yml && docker compose up -d --no-deps memory-market'
```
