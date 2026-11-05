# Catalogue floor on all six hubs — 2026-11-04

Owner: «Да, разверни». Code: aicom 28004ff8a (local branch only at the time of the rollout, not on main or Gitea).
All times are server clocks (UTC).

## What changed on the hubs

A crawl refuses a peer catalogue whose signed `generated_at` is older than the newest one this hub has already verified
from that peer under the same pinned key (discovery draft -04 §5, first check). The refusal counts as a failed
retrieval: stored entries stay and nothing is pruned. The time is recorded after each verified catalogue in a new table
`peer_catalogue_watermarks` (migration 066); a new pinned key starts a new record, a time more than an hour ahead of the
hub's clock is never recorded, `delete_peer` forgets it, and `aimarket peers --reset-catalogue-time <url>` clears it for
a peer whose clock went back. The pending-peer preview applies and records the same floor. Nothing else changed.

## Live variants and the port

The hubs do not run main. Before the change the four files were:

| File | modelmarket.dev (3.17.0) | the other five (3.16.0, Independent's venv too) | change base d509649f9 |
|---|---|---|---|
| crawler.py | `da1e1a6d572e` = base | `18ca66858706` | `da1e1a6d572e` |
| database.py | `4fd4134306ae` = base | `51e9785d810a` | `4fd4134306ae` |
| migrations.py | `b370e869934a` (up to 064) | `56ea4f9940cc` (59, 60, 63) | `679c835ccf35` |
| cli.py | `055905a73d19` = base | `055905a73d19` | `055905a73d19` |

`kit/patch_live.py` cuts every new block out of the committed source by its markers and inserts it at anchors that must
occur exactly once in the live file. Applied to the base files it reproduces the committed `database.py` and
`migrations.py` byte for byte, and `crawler.py` differs only in where `_parse_generated_at` sits and in the
`_manifest_too_stale` refactor, which is not ported. modelmarket.dev got the committed `crawler.py`, `database.py` and
`cli.py` (its live files equal the base) and the patched `migrations.py`; the 3.16.0 hubs got the three patched files
and the committed `cli.py`. Migration 066 does not collide with any live number.

| Context | crawler.py | database.py | migrations.py | cli.py |
|---|---|---|---|---|
| 3.16.0 (uni, lab, hunt, attested, Independent) | `81dca534c7d6` | `eee503f47b39` | `73ec24976866` | `8c86e0708cd9` |
| 3.17.0 (modelmarket.dev) | `0e5748920a9c` | `303c1768ce6b` | `286bc34629cf` | `8c86e0708cd9` |

## Build and smoke

`kit/build.sh` on each host: refuses unless the base is the image the container runs and the four live files still have
the hashes the context was patched from; builds FROM that image (`kit/Dockerfile`, four COPY lines); runs `kit/smoke.py`
inside it with no network and the hub's env names removed (a temp SQLite hub: replayed older catalogue refused and the
withdrawn entry stays out, same catalogue again accepted, newer accepted, CLI reset, new key, far-future time not
recorded with the max age off, preview floor, `delete_peer`; 13 checks); then compares the files in the image with the
context. All five builds: `catalogue floor smoke ok: 13 checks` (3.16.0 ×4, 3.17.0 ×1). Logs `logs/build-*.log`.

hub.attestedmemory.net ran `attested-memory-hub:bref2-20261104` (`629feadf6e35`), another session's image of the day
(ard2 + `hub_routes/invoke.py` + `provider_buyer_ref.py`), recreated 20:05Z on the same image and the same env names.
The overlay was built FROM it; both of that session's files are unchanged in the new container (`2b63407ac216`,
`cca0ec4b9c5d`).

## Rolls (`/root/hub-3160-main-20261021/roll.sh`: DB backup, then rollout_container.py with auto-rollback)

| Hub | Host | Before | After | Previous container | DB backup |
|---|---|---|---|---|---|
| uni.modelmarket.dev | factory-vps | `modelmarket-hub-uni:ard2-20261104` | `modelmarket-hub-uni:cf-20261104` | `modelmarket-hub-uni-security-prev-1793824944652070097` | `/app/data/hub-backup-pre-3160-20261104T204223Z.db` |
| modelmarket.dev | factory-vps | `modelmarket-hub:ard2-20261104` | `modelmarket-hub:cf-20261104` | `modelmarket-hub-security-prev-1793824968675101439` (+ THEMIS `themis-security-prev-1793824968675101439`) | `/app/data/hub-backup-pre-3160-20261104T204248Z.db` |
| hub.modelmarket.dev | competing-lab | `modelmarket-hub:ard2-20261104` | `modelmarket-hub:cf-20261104` | `modelmarket-hub-security-prev-1793825033608774170` | `/app/data/hub-backup-pre-3160-20261104T204353Z.db` |
| hunt.modelmarket.dev | competing-lab | `signal-hunt-hub:ard2-20261104` | `signal-hunt-hub:cf-20261104` | `signal-hunt-hub-1-security-prev-1793825069791662362` | `/root/hub-backups/signal-hunt-hub-1-pre-3160-20261104T204429Z.dump` |
| hub.attestedmemory.net | attested | `sha256:629feadf6e35…` (`attested-memory-hub:bref2-20261104`) | `attested-memory-hub:cf-20261104` | `attested-memory-hub-hub-1-security-prev-1793825121960976717` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261104T204521Z.dump` |
| independentai.network/hub | indep (venv) | the four files in `/root/cf-20261104/indep/backup-venv/` | the 3.16.0 context files in `hub-3.16.0-rpc-security-20261031` | — | `/root/indep-hub-pre-cf-20261104.dump` (`sudo -u postgres pg_dump -Fc independentai_hub`) |

Rolls 20:42–20:45Z, all `ROLL-EXIT=0`, healthy; THEMIS recreated healthy. Independent: `kit/indep/prepare.sh` checked the
live hashes, backed up the four files and ran the smoke on a patched COPY of the venv package under the venv's Python
(13 checks ok); the files were then copied in and the service restarted in a separate command at 20:46:50Z, healthy
after 4 s. The alerter had no open alerts before (oracle disk flapped three times earlier in the day, closed), and no
OS rollout was running.

## Verified live

- Migration 066 applied on all six (`kit/check_live.py`, Independent via psql).
- Times recorded after the first crawl: modelmarket.dev 21 of 22 trusted peers (the missing one,
  x402-gateway-production-1f21.up.railway.app, answers 404 for its well-known since 2026-10-31), uni 6/6, hub.modelmarket.dev
  21/22 (the same gateway), hunt 21 (18 trusted + 3 pending through the preview), attested 12 of 17 (the five others —
  oracles, momus, logos, histor, basanos — fail to fetch from that host; the previous container failed on the same five),
  Independent 21/21.
- hub.modelmarket.dev and hunt crawl every 300 s: their second crawl (about 20:50Z) moved every time forward and refused
  nothing. Peers that cache their catalogue (histor, registry) served the same time again, which passes and is not
  rewritten.
- `kit/outside_monotonic.py` from outside: each of the 21 peers' catalogues read twice; none older than the recorded value,
  none going backwards between reads (`logs/outside-monotonic.log`).
- Catalogue totals before → after: uni 93 → 93, modelmarket.dev 282 → 284 (fresh crawl), hub.modelmarket.dev 284 → 284,
  hunt 249 → 249, attested 215 → 215 (`logs/totals.log`).
- No refusal lines and no new tracebacks from the crawler. modelmarket.dev logs one existing 500 from an outside client
  on `POST /ai-market/v2/p/aimarket-zk/zk/prove-input` (`poseidon2 helper failed (exit 1): usage …`), present ten times in
  the previous container too; unrelated to this change.

## Rollback

Per container hub: start the previous container above, or
`cd /root/hub-3160-main-20261021 && python3 rollout_container.py <container> --image <before image> --health <url>`.
The old code ignores `peer_catalogue_watermarks`; leaving the table (and the `_migrations` row 066) is harmless, and
`DROP TABLE peer_catalogue_watermarks; DELETE FROM _migrations WHERE version=66;` removes them. Independent: copy the four
files from `/root/cf-20261104/indep/backup-venv/` back into the venv's `aimarket_hub/` and restart `independentai-hub`.

The compose trap still applies: hunt and attested are compose services, and `docker compose up` there recreates them
from the compose image, dropping this overlay (and, on attested, the other session's).

## Files

`kit/` (patch_live.py, Dockerfile, build.sh, smoke.py, check_live.py, outside_monotonic.py, indep/prepare.sh), `logs/`.
Build contexts and the live files they were patched from: `/root/cf-20261104/` on each host.
