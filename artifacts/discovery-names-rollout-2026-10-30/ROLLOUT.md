# Discovery names rollout — 2026-10-30

Change: commits 05cfcbaef + e15fd9d7d (deadlock fix) on branch `claude/ecosystem-protocol-standard-4a3020` — the hub serves
`/.well-known/agent-marketplace` beside `/.well-known/ai-market.json`, sends and accepts
`Agent-Marketplace-Crawler` beside `X-AIMarket-Crawler`, and reads draft-shaped discovery
documents (`aimarket_hub/discovery_names.py`; docs `aimarket-hub/docs/discovery-names.md`).

Method: overlay image built FROM the running image plus four files (`discovery_names.py`,
`crawler.py`, `federation_assay.py`, `hub_routes/wellknown.py`). The live `crawler.py` on every
hub predated branch base 44e7b4b5c by one hunk (the finite-price check from 634b2fbac); the
overlay carries the live file with only this change applied, so nothing else moved. `wellknown.py`
and `federation_assay.py` were byte-equal to the branch base on every hub before the overlay.
Context on each host: `/root/dn-20261030/` (Dockerfile, files, roll logs).

| Hub | Host | Container | Before (now `:pre-dn-20261030`) | After | Rollback container | DB backup |
|---|---|---|---|---|---|---|
| modelmarket.dev (apex) | factory-vps | `modelmarket-hub` (+ THEMIS borrows netns, re-created, healthy) | `modelmarket-hub:growth-head-20261029` | `modelmarket-hub:dn-20261030` | `modelmarket-hub-security-prev-1793334540898065494` | `/app/data/hub-backup-pre-3160-20261030T042900Z.db` |
| uni.modelmarket.dev | factory-vps | `modelmarket-hub-uni` | image `21508b911398` | `modelmarket-hub-uni:dn-20261030` | `modelmarket-hub-uni-security-prev-1793334589147604751` | `/app/data/hub-backup-pre-3160-…Z.db` (see roll log) |
| hub.modelmarket.dev (lab) | competing-lab | `modelmarket-hub` | image `18ec481bc53a` | `modelmarket-hub:dn-20261030` | `modelmarket-hub-security-prev-1793334987978411007` | `/app/data/hub-backup-pre-3160-20261030T043627Z.db` |
| hunt.modelmarket.dev | competing-lab | `signal-hunt-hub-1` | image `18ec481bc53a` | `modelmarket-hub:dn-20261030` | `signal-hunt-hub-1-security-prev-1793334992829865908` | `/root/hub-backups/signal-hunt-hub-1-pre-3160-20261030T043632Z.dump` |
| hub.attestedmemory.net | attested | `attested-memory-hub-hub-1` | `attested-memory-hub:3160-client-pagefix-20261024` | `attested-memory-hub:dn-20261030` | `attested-memory-hub-hub-1-security-prev-1793335418226830974` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261030T044337Z.dump` |
| independentai.network/hub | indep (no docker) | systemd `independentai-hub`, venv `hub-3.16.0-rpc` | files backed up to `/root/dn-20261030/backup-venv/` | four files copied into the venv's `aimarket_hub/` | restore from `backup-venv`, `rm discovery_names.py`, `systemctl restart independentai-hub` | none needed (no schema change) |

Rollback for a Docker hub: `docker start <rollback container>` after stopping the new one, or
`rollout_container.py <name> --image <before> --health …` from `/root/hub-3160-main-20261021`.

nginx: `hunt.modelmarket.dev` proxies only named hub paths (its `location /` is the game), so
`location = /.well-known/agent-marketplace` was added on competing-lab
(`/etc/nginx/sites-enabled/hunt.modelmarket.dev`, backup
`/root/dn-20261030/hunt.modelmarket.dev.pre-dn-20261030`, `nginx -t` ok, reloaded) and in the repo
copy `deploy/nginx/hunt.modelmarket.dev.conf`. The other five sites already proxy `/.well-known/`
or `/` to the hub.

Not touched: the non-hub peers that serve their own `.well-known/ai-market.json` (oracles, GAIA,
ATLAS, HESTIA, MOMUS, LOGOS, HISTOR, domains, esim, SYMMARTYS, BASANOS, THEMIS, SKOPOS, CHARON,
the factory, Industrial Sentinel, agent-exec). They keep the legacy name; the crawler reads both.

Verification (from outside, after the swaps): see the table printed in the session — every hub
answers GET and HEAD 200 on the draft path, the legacy path and health stay 200, and
`aimarket-protocol/conformance/run.py --hub <url>` passes the six draft checks on each.

## Second layer the same morning: dn2 (deadlock fix, e15fd9d7d)

The first overlay had a bug: the draft builder asked the well-known cache for the legacy
document from inside the cache's own lock (not re-entrant). The first request to the draft
path on a cold cache hung, and every later well-known request on both paths hung behind it.
Seen on uni and attested (my probes hit the draft path first there) from ~04:40Z; both were
`docker restart`ed at ~04:56Z (legacy path back in <1 s), and the other four hubs never hit
the case (their legacy document is polled constantly, so the cache was warm). Fix: build the
legacy document directly, not through the cache. Regression test in test_open_federation.py.

Images `:dn2-20261030` = `:dn-20261030` + the fixed `hub_routes/wellknown.py`
(`/root/dn-20261030/dn2/`). Rolled with the same roll.sh, EXPECT = the dn image; rollback
containers `*-security-prev-<stamp>` from the dn2 roll logs
(`/root/dn-20261030/roll-dn2-{factory,lab,attested}.log`). Independent: the fixed file copied
into the venv, service restarted, draft-first request 200 in 0.38 s.

## Verified 2026-10-30 05:15Z (after dn2 on all six)

| Hub | draft GET | HEAD | legacy | health | conformance `--hub` |
|---|---|---|---|---|---|
| modelmarket.dev | 200, 0.75 s | 200 | 200 | 200 | all 39 passed |
| uni.modelmarket.dev | 200, 0.71 s | 200 | 200 | 200 | all 39 passed |
| hub.modelmarket.dev | 200, 0.37 s | 200 | 200 | 200 | all 39 passed |
| hunt.modelmarket.dev | 200, 0.72 s | 200 | 200 | 200 | all 38 passed |
| hub.attestedmemory.net | 200, 0.87 s | 200 | 200 | 200 | all 39 passed |
| independentai.network/hub | 200, 0.90 s | 200 | 200 | 200 | all 38 passed |

THEMIS (borrows the apex netns) healthy after both swaps.
