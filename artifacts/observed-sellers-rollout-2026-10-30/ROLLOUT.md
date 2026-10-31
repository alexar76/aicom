# Observed-seller tier rollout — 2026-10-30

Owner: «Yes, roll it out» (after the tier was committed as d617b1e0a on branch
`claude/backend-audit-ecosystem-a7acca`; not on main, not on Gitea, never GitHub).

All times are server clocks (UTC). The Mac that ran the rollout was about 58 minutes fast that day.

## What was ported

Production runs the pre-split package (no `hub_lifespan.py`; the lifespan lives inside `api.create_app`), in two
variants: apex (`api.py` c9b22a02, `migrations.py` 6b83aa31 with 061) and the other five (`api.py` 1ad25af1,
`migrations.py` e4a2be72, last migration 060). `database.py`, `hub_routes/{federation,catalog,wellknown}.py` were
identical to main everywhere, so the branch diff applied as is; `mcp_gateway.py` and `outbound_http.py` differ from
main elsewhere but took the diff without fuzz. `port_patch.py` adds by anchor what the diff could not:

- `api.py`: the `_periodic_observe` task (first cycle `crawl_initial_delay_s + 30` s after start, then every
  600 s + 0–60 s jitter; a cycle with no consented seller is one query), cancelled with the other tasks;
- `migrations.py`: 063 `observed_sellers` before `channel_ledger_versions` (the runner applies by set of versions,
  so 063 without 061/062 is safe; those apply when they arrive).

Overlay images FROM each hub's running `:or-20261030` (`Dockerfile` here, 9 files). Each image ran `smoke.py`
inside itself with no network: consent POST (401 without admin), one unpaid probe per route and the discovery read
(no payment header), listing, `observed` in `/search` with price and payTo, `observed_sellers` in the well-known,
MCP `market_search`, DELETE. The file hashes inside every image were compared with the context (`build.sh`).

Before building: `tests/test_observed_sellers.py` 32 passed on copies of both live variants; the neighbouring
suites (api, catalog hygiene, discovery names, federation assay, MCP ×4, open federation, outbound ×2, search
ranking) gave the same 11 failed / 401 passed on the live copies before and after the port: the failures are
main-vs-production differences, none introduced.

## Hubs

| Hub | Host | Before (rollback image) | After | Rollback container | DB backup |
|---|---|---|---|---|---|
| modelmarket.dev | factory-vps | `modelmarket-hub:or-20261030` | `modelmarket-hub:os-20261030` | `modelmarket-hub-security-prev-1793381758159847459` (+ `themis-security-prev-1793381758159847459`) | `/app/data/hub-backup-pre-3160-20261030T173557Z.db` |
| uni.modelmarket.dev | factory-vps | `modelmarket-hub-uni:or-20261030` | `modelmarket-hub-uni:os-20261030` | `modelmarket-hub-uni-security-prev-1793381874456394515` | `/app/data/hub-backup-pre-3160-20261030T173753Z.db` |
| hub.modelmarket.dev | competing-lab | `modelmarket-hub:or-20261030` | `modelmarket-hub:os-20261030` | `modelmarket-hub-security-prev-1793381976441227501` | `/app/data/hub-backup-pre-3160-20261030T173936Z.db` |
| hunt.modelmarket.dev | competing-lab | `modelmarket-hub:or-20261030` | `modelmarket-hub:os-20261030` | `signal-hunt-hub-1-security-prev-1793381981028025419` | `/root/hub-backups/signal-hunt-hub-1-pre-3160-20261030T173940Z.dump` |
| hub.attestedmemory.net | attested | `attested-memory-hub:or-20261030` | `attested-memory-hub:os-20261030` | `attested-memory-hub-hub-1-security-prev-1793382675492716478` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261030T175114Z.dump` |
| independentai.network/hub | indep (venv) | 8 files in `/root/os-20261030/backup-venv/` | 9 files in `hub-3.16.0-rpc` | copy the 8 files back, `rm observed_sellers.py`, `systemctl restart independentai-hub` | none needed |

Rolled with `/root/hub-3160-main-20261021/roll.sh` (backup, then `rollout_container.py`, which keeps the old
container stopped and restores it by itself on a failed health check); contexts and logs in `/root/os-20261030/`
on each host. Independent: the patched copy of its own venv package passed `smoke.py` under the venv's Python
first, then the files were copied in and the service restarted in a separate command.

Rollback leaves migration 063 in place: an additive table the older code never reads.

Compose trap unchanged: hunt and attested are compose services, and `docker compose up` there would recreate them
from the compose image, not from `:os-20261030` (true of every overlay since 10-22).

## Verified (17:36–17:58Z)

- All six: health 200; `GET /ai-market/v2/federation/observed-sellers` 200 with `sellers: []`; POST without the
  admin token 401; `/search` carries `observed`; the well-known carries `observed_sellers_url`; migration 063
  recorded (SQLite on apex, UNI and lab; PostgreSQL on hunt and attested; Independent answers the table query).
- UNI: `enabled: false` (the realm never hands out a real payment offer), as designed.
- `conformance/run.py --hub` passes on all six. Attested failed once with a manifest read time-out right after the
  restart (cold cache, 373 KB); the rerun passed with 39 PASS, the manifest answering in 1.7 s.
- Live end-to-end on apex with our own route (`selftest.py`, consent recorded as an operator self-test): the hub
  read `https://modelmarket.dev/.well-known/x402`, sent one unpaid POST to `/x402/x402-check`, got a V2 402 and
  listed it at $0.003 on eip155:8453 with payTo `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a` pinned; `/search`
  showed it under `observed`; DELETE removed it and the listing is empty again.

No outside seller is recorded: each needs its own consent first (SWARM's letter is in PromoMaterials; TensorFeed is
on hold until it says how to get a 402 without spending its free trial).
