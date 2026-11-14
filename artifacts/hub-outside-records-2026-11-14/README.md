# Outside records on observed sellers (spec §2.7) — modelmarket.dev apex, 2026-11-14

**Why.** An observed listing says only what a seller's unpaid 402 asked for; it cannot see delivery. vet402 pays x402
sellers with its own money and publishes what each paid call returned. On 2026-11-14 vet402 (Sen,
support@vet402.com) confirmed that `https://vet402.com/sellers/<host>` is the URL it keeps stable and that
`GET https://vet402.com/api/v1/check?url=<listing>&method=<METHOD>` needs no key. Owner: «сделай».

**What changed.** `aimarket_hub/observed_sellers.py` and `aimarket_hub/hub_routes/federation.py`:
- each seller in `/ai-market/v2/federation/observed-sellers` gets `outside_records: [{by, url}]`;
- each route (listing and the `observed` array of `/search`) gets `outside_checks: [{by, url}]`;
- the listing gets `outside_records_note`: the hub builds links only, runs and reads nothing, and the answers are not
  part of `vouches_for`;
- the host is taken exactly from the seller's origin (`www.oracleinsight.xyz` has a vet402 page, the bare domain is
  404); an origin with a port gets no link; `AIMARKET_OBSERVED_OUTSIDE_RECORDS` chooses the services (default
  `vet402`, `none` = off).
- `aimarket-protocol/spec.md` §2.7 «Outside records» (MAY link; MUST NOT fetch on a buyer's behalf or fold answers into
  `tier`/`fresh`/`served`; MUST say so in the listing).

**Tests.** `tests/test_observed_sellers.py` 77 passed (5 new). Every hub test file that mentions observed sellers: 359
passed. Full suite: see `tests.log`.

**Kit.** `kit/` (copied from `hub-external-directory-2026-11-13`, two files): `stage.py` checks the preimages against
local main 4a16d654b, which equal the live container byte for byte (checked over ssh before staging). `deploy.sh
prepare|switch|rollback` on factory-vps in `/root/hub-outside-records-20261114/kit`.

**Prepare (factory-vps).** Live parent `sha256:60b41cad9c31…` → candidate `sha256:f2f06e99ff73…`. Source delta exactly
the two files; 76 Python distributions and 129 Debian packages unchanged. Smoke on disposable copies of both ledgers,
base and candidate: identical manifest, observed listing (minus the new keys), search and bridge; no migrations; links
for all four sellers (tienda.textokit.store, aemb.pro, priorseal.xyz, www.oracleinsight.xyz). Log: `prepare.log`.

**Rollback.** `cd /root/hub-outside-records-20261114/kit && bash deploy.sh rollback` (same payout-timer coordination;
ledgers and payouts stay).

## Switch, 2026-11-14 (server clock)

**Attempt 1, 09:05:39Z — aborted before anything stopped.** `rollout_container.py` checks both health URLs first;
THEMIS (127.0.0.1:9460) refused. Cause, found then: `modelmarket-hub` (container 4c7e27093b6a) was stopped and started
in place at 05:30:42Z by something outside this work (dockerd «stopping restart-manager» for that container; host not
rebooted, uptime since 10-31). THEMIS shares the hub container's network namespace (`container:<hub id>`) and was not
restarted with it, so it stayed in the dead namespace: **themis.modelmarket.dev answered 502 from ~05:30Z to 09:07Z**
while its own healthcheck said healthy. The alerter had no alert for it. Ledger backup of the attempt:
`/root/hub-backups/outside-records-20261114T090539Z-uED5DGwV`.

Kit bug the attempt exposed: `restore_timer` was a `local`, so the EXIT trap hit «unbound variable» under `set -u` and
the payout timer stayed stopped (the worker had nothing queued; restarted by hand within ~1 min). Fixed in `kit/deploy.sh`
(global flag); the same bug is in the 11-13 kits (`hub-external-directory`, `hub-x402-observer`) — it only bites on a
failed switch.

**THEMIS fix, 09:07:04Z:** `docker restart themis` (image unchanged, `themis-before-restart.txt`); local and public
/health 200 at once.

**Attempt 2, 09:07:46Z — done.** Backups `/root/hub-backups/outside-records-20261114T090746Z-7SevLfq2`. Live image
`sha256:f2f06e99ff73…`, previous container kept as `modelmarket-hub-security-prev-1794647267205156637`, THEMIS recreated
into the new hub's namespace by the rollout tool, payout timer active, overlay sha256 OK in the live container.

**Checked from outside after the switch:** observed-sellers listing carries `outside_records_note`; all four sellers have
`outside_records` and every route `outside_checks`; the four vet402 seller pages answer 200; vet402's check answers
ALLOW for www.oracleinsight.xyz pre-trade (l1_delivered) and `not_in_catalog` for routes it has not catalogued (aemb.pro
ping, a PriorSeal example) — the link is right, vet402 simply has no record yet. `/search` observed rows carry
`outside_checks`. modelmarket.dev, /tools/, hub health and themis.modelmarket.dev/health: 200. Payout worker ran clean
after the switch. Hub log: no traceback (one ordinary 404 from crawling a stranger's well-known).

## THEMIS protection installed (owner «Да, ставь»), 2026-11-14

- **Watcher on factory-vps.** `themis-reattach-factory.service` (docker events: every hub `start`) and
  `themis-reattach-check.timer` (every 5 min) run `/usr/local/lib/themis-reattach/themis-reattach.py`
  (source `themis/deploy/`). The test is reachability from inside the hub (`docker exec modelmarket-hub` →
  127.0.0.1:8080/health), not the container ID: the 09-08 script compared IDs and would have called today's
  in-place restart "attached". Same hub ID → `docker restart themis`; other ID → recreate from THEMIS's own inspected
  config (env, volume themis_data, policy, image), old container renamed and kept until the new one answers.
  No /root/themis.env exists on factory-vps, so the 09-08 recreate path would have dropped THEMIS's identity env.
- **Alerter on skopos-vps.** New check kind `service_up` (`AICOM_ALERT_SERVICE_URLS`), wording «{t} is not
  answering», not «hub»; `themis.modelmarket.dev=https://themis.modelmarket.dev/health` added to /etc/aicom-alert.env.
  Backups: `ecosystem_alert.py.pre-20261114-service`, `/etc/aicom-alert.env.pre-20261114-service`. Dry run: 114 checks,
  `service_up@themis.modelmarket.dev` ok (200 in 0.3 s); only `host_disk[competing-lab]` failing (open since ~03Z).
- **Proof by breaking it, 09:20:22Z:** `docker stop themis` → 127.0.0.1:9460 000 → `themis-reattach-check.service`:
  «points at the live hub 2114a8d0d977 but is not reachable … restarting THEMIS» → reachable at 09:20:25Z; local and
  public /health 200.
- Not proven on purpose: the recreate path (hub gets a new ID outside our rollout tool) — that needs a hub recreate;
  our rollout tool already recreates borrowers itself.
- Undo: `systemctl disable --now themis-reattach-factory.service themis-reattach-check.timer`; alerter: restore the two
  `.pre-20261114-service` files.
