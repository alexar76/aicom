# Validity in HTTP on the six hubs — Cache-Control, weak ETag, 304; peers' stated periods — 2026-11-26

**Why.** dawn@ietf.org, REQ-PROP-5/6 thread on draft-king-dawn-requirements-02 (2026-11-26): Riccardo Di Nuzzo
(BEST protocol) asked that discovery documents state validity with Cache-Control max-age and ETag, as a MUST. Our
modelmarket.dev discovery document and signed catalogue sent neither (only /.well-known/ai-catalog.json did). Owner:
«делай все и готовь».

## Change (main ee9b8835e, hub 3.22.3)

- `http_validity.py`: Cache-Control, weak ETag over the content without `signature`, `generated_at` (and the
  manifest's per-request `by_hub.*.last_crawl`) — both documents are re-signed on every build, so an ETag over the
  bytes would never match —, If-None-Match (weak comparison, lists, `*`), and `stated_period()` for a peer's header.
- `/ai-market/v2/manifest`: `public, max-age=300, stale-if-error=172800`; `/.well-known/ai-market.json` and
  `/.well-known/agent-marketplace`: `public, max-age=60, stale-if-error=172800`; 304 on a match. stale-if-error =
  `federated_max_unverified_s` (the period this hub keeps other hubs' entries after a failed read; omitted when 0).
- Crawler: a peer's `max-age + stale-if-error` (no-store/no-cache alone = 0) sets `capabilities.serve_until` when
  shorter than our 48 h, never below two crawl intervals; `catalogue_evidence.stated_validity_s` records it.
  Migration 073 adds `serve_until` (TEXT, NULL = our bound alone); older code ignores the column.
- Tests `tests/test_http_validity.py` (20). Full suite 4397 passed; the 2 failures present since 3.22.0.

## Kit (`kit/`, on each host `/root/hub-httpvalid-20261126`)

`files/` = main's crawler, database, migrations, models, http_validity and hub_routes/wellknown.py; every hub ran
the expected versions of these (fedvalid overlay + 3.22.0), checked by `build.sh` / `indep.sh prepare`.
`catalog.py` differs by hub (3.22.0 `8d3ee72e1c0a`: hunt, uni, attested, Independent; main `5b7529957413`:
modelmarket.dev; another session's `tutu-find` variant `02674f6adb3d`: hub.modelmarket.dev), so `kit/catalog/` holds
each variant with the same patch (28 changed lines each; the 3.22.0 import hunk applied by hand).

Smoke before the switch on a copy of every live database (`smoke_sqlite.sh`, `smoke_pg.sh`, `indep.sh smoke`): the
new image applies migration 073 only, changes no row count, serves the headers and 304 on the manifest and both
discovery documents; then the running image starts on the migrated copy (rollback proven). All six passed.

## Per hub (server UTC)

| hub | switched | previous container (rollback) | database backup |
|---|---|---|---|
| hub.modelmarket.dev (canary), competing-lab `modelmarket-hub` | 17:37:04Z | `modelmarket-hub-security-prev-1795714625240449666` | `/root/hub-backups/modelmarket-hub-pre-httpvalid-20261126T173704Z.db` |
| hunt.modelmarket.dev, competing-lab `signal-hunt-hub-1` | 17:38:05Z | `signal-hunt-hub-1-security-prev-1795714686373621199` | `/root/hub-backups/signal-hunt-hub-1-pre-httpvalid-20261126T173805Z.dump` |
| uni.modelmarket.dev, factory-vps `modelmarket-hub-uni` | 17:38:16Z | `modelmarket-hub-uni-security-prev-1795714698206746840` | `/root/hub-backups/modelmarket-hub-uni-pre-httpvalid-20261126T173816Z.db` |
| modelmarket.dev, factory-vps `modelmarket-hub` (+ THEMIS), right after a payout run, borrowers = themis | 17:39:10Z | `modelmarket-hub-security-prev-1795714751829100796` | `/root/hub-backups/modelmarket-hub-pre-httpvalid-20261126T173910Z.db` |
| hub.attestedmemory.net, attested `attested-memory-hub-hub-1` | 17:40:05Z | `attested-memory-hub-hub-1-security-prev-1795714806557075892` | `/root/hub-backups/attested-memory-hub-hub-1-pre-httpvalid-20261126T174005Z.dump` |
| independentai.network/hub, indep `independentai-hub.service` | 17:40:17Z | `./indep.sh rollback` (drop-in 99j → back to fedvalid via 99i) | `/var/backups/independentai/hub-pre-httpvalid-20261126T174017Z.dump` |

Container rollback: `cd /root/hub-httpvalid-20261126 && python3 rollout_container.py <container> --rollback`. The old
images run on a database at migration 073 (smoke).

## Checks after (from outside, 17:41–17:44Z)

All six: health 200; manifest `public, max-age=300, stale-if-error=172800` with a weak ETag and 304 on If-None-Match;
`/.well-known/agent-marketplace` `public, max-age=60, stale-if-error=172800`. On the canary, right after the restart,
the manifest ETag changed between two requests once: the first crawl was refreshing rows (real content changes).
Six samples later only `by_hub.local.last_crawl` differed, which the ETag leaves out; 304 local and through the edge.
