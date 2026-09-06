# Operations traps — things that look fine and are not

Every entry here was measured on the live deployment, not reasoned about. Each one had
the same shape: a check passed, a deploy reported success, or a number looked plausible,
while the thing being checked was broken. That is the only kind of fact worth writing
down separately from the code — a failure that announces itself needs no runbook.

**English only, deliberately.** The public layer — `README`, `USER_GUIDE`, `FAQ`, the
whitepaper and the knowledge base — is translated into five languages because readers
arrive there. This file has one reader: whoever is on call. Five translations of an
operations document means five things to keep in step, and a stale runbook in a language
you trust is more dangerous than no runbook. Related:
[`known-issues.md`](known-issues.md) (open items),
[`payment-enable-runbook.md`](payment-enable-runbook.md),
[`deploy-ecosystem-runbook.md`](deploy-ecosystem-runbook.md).

---

## T-1 — `modelmarket.dev` resolved to two addresses; only one served its certificate — RESOLVED 2026-08-25

**Measured 2026-08-25.** The apex and `www` each carry two A records:

```
203.0.113.10     cert CN = modelmarket.dev        → the hub, HTTP 200
203.0.113.40     cert CN = emberlinedesk.com      → TLS verify fails; plain HTTP 301s to
                                                    https://emberlinedesk.com/
```

(Addresses above are RFC 5737 documentation placeholders — real fleet IPs stay off the
public tree; see `scripts/scrub_private_hosts.sh`.)

From the second host, **10 of 20** plain HTTPS requests to the apex failed with
`CERTIFICATE_VERIFY_FAILED`. `curl` hides this by retrying the other address; Python's
`urllib`, and many SDKs, do not — for them half the calls simply fail. Every
single-connection health check stayed green for weeks, because whichever address answers
first is usually the right one.

`203.0.113.40` **is ours** — a third Timeweb box (`competing-lab` in `~/.ssh/config`)
running Signal Hunt, the "Competing Lab Hub" on `:9083`, and `emberlinedesk.com`. It has
Let's Encrypt certificates for `hunt.`, `om.`, `pantheon.`, `use.` and
`warden.modelmarket.dev` — and **none for the apex**, and no vhost claiming it, so its
default server answers with the redirect above. `hunt.modelmarket.dev` resolves there and
only there, which is correct; the apex record is not.

**Fixed** by deleting the stray apex/`www` `A` record that pointed at competing-lab in
Timeweb (Домены → `modelmarket.dev` → DNS-записи; the row for the hub carries the server
label `Polite Erinome` and must stay). Measured after: SOA serial 70 → 71, all four
Timeweb nameservers clean **8 minutes** later, and the client-side test went 10/20 →
**20/20**.

Two things to know for the next zone change. `ns3.timeweb.org` briefly served the **new**
serial with the **old** A record, so a serial check alone does not prove propagation —
compare the records themselves, on every nameserver. And a resolver cache outlives the
change: `resolvectl flush-caches` was needed on the alerter's own host, or it would have
reported a false `hub_dns_all_addresses_valid` failure for the remaining TTL.

**Verify:**
```bash
dig +short A modelmarket.dev @1.1.1.1        # expect only the hub address
python3 scripts/ecosystem_alert.py --dry-run  # hub_dns_all_addresses_valid must pass
```

**Why a health check cannot catch this on its own:** it has to walk *every* address
separately. `probe_dns` in [`scripts/ecosystem_alert.py`](../scripts/ecosystem_alert.py)
does, and names the certificate the impostor presents.

---

## T-2 — restarting the Hub takes THEMIS down and nothing puts it back

**Measured 2026-08-25.** THEMIS runs inside the Hub's network namespace
(`--network container:<hub>`), and the Hub publishes the auditor's port on its behalf:

```
modelmarket-hub  8080/tcp -> 127.0.0.1:9460
```

A plain `docker restart modelmarket-hub` recreates the Hub's network sandbox. THEMIS keeps
a handle on the old one, so its `NetworkMode` still reads `container:<the same id>` and its
image is unchanged — while the auditor is unreachable. Measured: **30 seconds of `000`**
from the host, with no recovery; `docker restart themis` cures it immediately.

`deploy_hub_rebuild.sh` re-homes THEMIS after a container *swap*, so deploys are safe. A
bare restart has no such hook.

**Fix:** after any `docker restart modelmarket-hub`, run

```bash
/root/attach_themis_to_hub.sh
```

Since 2026-08-25 that script checks liveness, not just the namespace string, so it
re-homes in exactly this case instead of reporting "nothing to do". Skipping happens only
when namespace, image **and** a live `/health` all agree.

---

## T-3 — probing THEMIS on 9460 from inside the Hub always fails, and that is normal

`9460` exists only on the **host** side of the port publish. Inside the shared namespace
the auditor listens on **8080**. A `docker exec modelmarket-hub curl 127.0.0.1:9460` is
refused on a perfectly healthy system — this cost a wrong diagnosis once.

```bash
# from the host
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:9460/health
# from inside the Hub
docker exec modelmarket-hub python3 -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=3).status)"
```

---

## T-4 — deleting the seeded demo catalogue is undone by the next restart

`seed_capabilities` runs when the local capability count is **zero**, so removing the
twelve unexecutable showcase rows guaranteed their return on the next deploy — catalogue
hygiene as a temporary state.

Closed in code on 2026-08-25: a hub with `AIFACTORY_PROD=1` does not seed at all
(`api.py`, near `seed_capabilities`), rather than depending on `AIMARKET_SKIP_SEED` being
remembered in a deploy capture. The rows were then deleted for real:

```
before: capabilities 97, offerable 85, demo 12     /prices 97, /manifest 85
after:  capabilities 85, offerable 85, demo 0      /prices 85, /manifest 85
```

Backup of the deleted rows: `/root/local-capabilities-backup-20260825.json` on the hub
host. They are also reproducible from `aimarket_hub/demo_seeder.py` on any non-prod hub.

---

## T-5 — duplicate env assignments: docker keeps the LAST, `re.search` finds the FIRST

`AIMARKET_SELLS_FOR` appeared twelve times in the payment env file. Docker applied the
last line; the test that was supposed to guard the setting matched the first. ATLAS was
served free for weeks with a green test.

`deploy_hub_rebuild.sh` now collapses duplicates keeping the last, and
`tests/test_hub_payment_env.py` reads last-wins and fails on any duplicated key. When
adding an env var to prod, check for an existing assignment before appending.

---

## T-6 — the build tree is not what production runs

The hub image on prod is built elsewhere; `docker build` from the working tree produces a
*different* application. To ship one changed file, derive from the live image:

```bash
# on the hub host
mkdir -p /root/hub-derived && cd /root/hub-derived
cp /tmp/api.py .
printf 'FROM %s\nCOPY api.py /app/aimarket_hub/api.py\n' \
  "$(docker inspect modelmarket-hub --format '{{.Config.Image}}')" > Dockerfile
docker build -t modelmarket-hub:prod-$(date +%Y%m%d)-fix .
cd /root && AIMARKET_HUB_IMAGE=modelmarket-hub:prod-$(date +%Y%m%d)-fix \
  ./deploy_hub_rebuild.sh --no-build
```

The deploy keeps the previous container as `modelmarket-hub-prev`; rollback is
`./deploy_hub_rebuild.sh --rollback`.

---

## T-7 — run the payment canary from the hub host, not from a laptop

The canary is a customer-side check, so it goes through DNS. While T-1 was open, a laptop
run failed on `manifest_served` about half the time with production perfectly healthy,
because the cron on the hub host resolves to itself first and never saw it. The lesson
outlives the incident: a check that runs beside the thing it checks cannot see the network
between the thing and its customers.

```bash
ssh factory-host '/usr/bin/python3 /root/aicom-hub-build/payment_canary.py'
```

The deployed copy is a standalone file, not a checkout: after editing
`scripts/payment_canary.py`, copy it over, or the daily green light keeps testing the old
logic. That happened — the cron ran a version probing 4 of 7 priced providers, which is
the exact blind spot that let T-5 through.

---

## T-8 — "timer enabled" is not "alerter working"

The alert timers were enabled, `systemctl list-timers` showed both scheduled, and the unit
did nothing at all: `ProtectHome=yes` in the service hides `/root`, where the script had
been copied, so every run died with

```
/usr/bin/python3: can't open file '/root/aicom-watch/ecosystem_alert.py': No such file or directory
```

`SuccessExitStatus=1` (needed so a real incident does not leave a red unit) also made the
failure quiet. A monitoring component is the one thing that cannot be verified by its own
status — it has to be verified by an observed run:

```bash
systemctl start aicom-alert@quick.service
journalctl -u 'aicom-alert@quick.service' -n 20 --no-pager   # expect probe output, not ENOENT
```

The script now lives in `/usr/local/lib/aicom-alert/`, which survives the hardening.

Two follow-on traps from the same component, both hit on 2026-09-01:

**The alerter is not in anybody's crontab.** It runs on systemd timers. `crontab -l` on every
host finds only `payment_canary.py`, which reads exactly like "there is no alerting in
production" — a wrong and expensive conclusion to hand an operator. Ask systemd:

```bash
systemctl list-timers 'aicom-alert*' --all --no-pager
```

**A green alerter only means the checks it has are passing.** It ran 11/11 green for five days
while ATLAS's key pin was rejected on two hubs and a paid capability was missing from the
catalogue: no check looked at peers, and a partial federation freeze does not empty the
catalogue that `hub_catalogue_not_empty` watches. `probe_federation` now covers it —
`hub_federation_pins_accepted` (any peer in `key_mismatch`, named in the message) and
`hub_federation_crawl_fresh` (stalest `last_crawl`, `AICOM_ALERT_PEER_STALE_HOURS`, default
26h). Both are needed: a hub image older than the status-preserving `upsert_peer` fix resets a
rejected peer to `active` on every trust-score refresh, so the pin check alone reads clean
while the crawl stays rejected. Deploying the script is a copy, and `--dry-run` is how you
confirm the count went up:

```bash
scp scripts/ecosystem_alert.py not-my-vps:/usr/local/lib/aicom-alert/ecosystem_alert.py
```

Every hub in the federation gets its own copy of those checks, named `...@label`.
`AICOM_ALERT_FEDERATION_HUBS` lists hubs explicitly (an entry may be `label=url`, so a page
reads `@independent` rather than a bare hostname), and `full` mode additionally *discovers*
them: it walks the primary hub's peers and probes each for a peer list of its own, so a hub
that joins is watched without anyone editing a config. Satellites publish no peer list and
never appear.

A hand-kept list was the original hole — two hubs went 21 days un-recrawled because nobody
had listed them — and the first attempt to patch it was worse: a completeness check plus an
"ignore" list for hubs judged not ours to watch. The federation is open, hubs join without
asking, so "ours" is not a property this alerter can read; the one hub that got classified as
somebody else's had a rejected key pin at that moment, which the ignore entry would have
hidden. Nothing is classified now and nothing is silenced. An independent node — a standard
hub on a separate server — is watched like any other and simply labelled.

---

## T-9 — the collector is automated now; here is how to tell it is working

Since 2026-08-25 submission is not a human habit. Two timers, on two hosts, deliberately:

| where | unit | cadence | what it does |
|---|---|---|---|
| hub host | `aicom-settlement-sweep.timer` | 15 min | `escrow_bridge.cli submit --yes` when the queue is non-empty, then publishes `settlement.json` |
| oracle host | `aicom-alert-quick.timer` | 10 min | probes the hub, the signer, both published reports; pages Telegram on state change |
| oracle host | `aicom-alert-full.timer` | 1 h | the same plus real unpaid invokes against every priced provider |

Check it in one line:

```bash
curl -s https://verify.modelmarket.dev/settlement.json | python3 -m json.tool
```

`ok:false` or a non-zero `pending_usd_after` means authorizations are sitting unbroadcast.
`uncollected.expired_usd` is different and never urgent: those are debits already recorded
on chain, in channels past expiry, waiting for anyone to call `expireChannel` — which is
permissionless and pays the hub the same amount, so the money cannot be lost by waiting.

Two bugs found while building this, both of the same kind — code written against the shape
a payload *seemed* to have:

* `unsubmitted_units` lives under `store`, not at the root of `status --json`. Read from
  the root it returned 0 for every input, so the sweep would have found an empty queue
  forever **and reported success**. The test fixture is now a verbatim copy of a live
  payload.
* a bridge with `may_broadcast: false` also looks like an empty queue. It is now an error
  that names the missing switch, instead of a quarter-hourly no-op.

**Still manual, by design:** `settleChannel`. HORKOS signs `debitChannel` and nothing else,
so collection needs either the depositor's key (what the buyer uses anyway) or a decision
to widen the signer's policy. `expireChannel` needs only gas from any account.

---

## T-10 — the signer was running different code than the repository, and the chain rule had changed

Shipping the working tree's `ledger.py` over the signer's took it out of service. Not a
crash: it booted, said `REFUSING TO SERVE: spend chain broken at seq 4`, and answered every
signing request with 503 — the fail-closed behaviour working exactly as designed, on a
problem that was entirely self-inflicted.

The cause is T-6 wearing different clothes. Production was running an image built 16 hours
earlier from a **wide** integrity rule: the row hash covered every immutable field *plus*
`gas_limit`, `hub_gas_hint`, `max_fee_wei`, `account_nonce` and a hardcoded
`state="reserved"`. The repository already had the **narrow** rule (`_CHAINED_FIELDS`,
immutable fields only) — a fix that was committed but never deployed. New code met a row
written by old code, and could not verify it.

The narrow rule exists for a reason worth keeping in mind: `reserve`'s revive path, which
lets a debit be retried after a released simulation, *rewrites* `account_nonce`,
`gas_limit` and `max_fee_wei`. Under the wide rule a legitimate retry silently invalidated
the row's own tag, so the next boot refused. An integrity check that a normal operation
breaks is a time bomb, not a check.

**Recovery** — `escrow-signer/migrations/001_narrow_chain_rebaseline.py`:

```bash
# stop the signer first: it holds the database open and boots by verifying it
docker run --rm --user 0 -e PYTHONPATH=/app -v escrow-signer_escrow_signer_data:/data \
  -v /root/escrow-signer/migrations:/app/migrations --entrypoint python \
  escrow-signer:0.1.0 /app/migrations/001_narrow_chain_rebaseline.py /data/signer.db
# then the same command with --apply
```

Its safety property is the part to preserve if this ever has to happen again: a row is
re-tagged **only after** its stored tag is verified under the rule that wrote it, using the
row's own `prev_row_hash` as the link. A row authentic under neither rule leaves the
migration refusing and the data untouched — that is the tampering case, and the chain exists
to catch it. The migration also writes itself into the audit chain, because an operator
touching the books has to be visible in them.

**How to avoid needing it:** before replacing any file in the signer, diff the running
image against the tree.

```bash
id=$(docker inspect escrow-signer --format '{{.Image}}')
docker run --rm --entrypoint cat "$id" /app/escrow_signer/ledger.py > /tmp/prod-ledger.py
diff /tmp/prod-ledger.py escrow-signer/escrow_signer/ledger.py
```

---

## T-11 — `rsync --delete` of the monorepo wipes `deploy/hub-payment.env`

**Measured 2026-08-27.** A security redeploy rsynced the working tree to
`/root/claudecode/aicom` with `--delete`. `deploy/hub-payment.env` is **gitignored**
(correct — host-only payment interlock), so it is not in the source tree. `--delete`
removed the live file. The next hub recreate started without the interlock:

```
payment_configured   false
payment_testnet      true
AIMARKET_ESCROW_BRIDGE_ENABLED unset → settlement sweep: "bridge disabled"
priced peers served unpaid (HTTP 200) → canary_verdict_ok FAIL
```

Telegram fired `canary_verdict_ok` + `settlement_nothing_stuck`. Restored from
`/root/aicom-hub-build/deploy/hub-payment.env`, recreated the hub container, canary
33/33 green again.

**Durable copy:** keep `/root/deploy/hub-payment.env` (and `hub-zk.env`) **outside** the
monorepo path. `scripts/deploy_hub.sh` restores from there (and from
`/root/aicom-hub-build/deploy/`) when `$ROOT/deploy/hub-payment.env` is missing.

**When syncing the monorepo to the factory host, never bare `--delete` over `deploy/`
secrets** — exclude `deploy/hub-payment.env` and `deploy/hub-zk.env`, or sync only the
paths you intend to change.

---

## T-12 — deploying a factory code change: one factory, two copies of the code

There is exactly **one** running factory: `my-vps`, container `aicom-app-1`, live store
`/root/claudecode/aicom/data/state/pipeline.db` (185 MB, written continuously). Checked
2026-08-27, because the topology invites the opposite conclusion:

| Host | What is there | Is it a factory? |
|---|---|---|
| `my-vps` | `/root/claudecode/aicom` + `aicom-app-1` | **yes** — the only one |
| `admin-vps` | `/root/aicom`, plus dioscuri / helios / argus containers | no — satellites only; its `pipeline.db` is 40 KB frozen at 2026-08-01 |
| `not-my-vps` | no checkout | no |

So a factory change is **not** two deploys. But it *is* two steps on the one host, because the
code exists twice there and only one copy runs:

1. the rsync'd source tree at `/root/claudecode/aicom` — what you edit;
2. the **baked image** `ai-factory:<tag>` — what actually executes.

`docker inspect aicom-app-1` shows a single mount, `/root/claudecode/aicom/data → /app/data`.
Only `data/` is shared. Every `.py` under `agents/`, `core/`, `web/` is inside the image, so
**syncing the tree changes nothing about the running worker** until the image is rebuilt.

```bash
# 1. sync only the paths you changed — never a bare --delete (see T-11)
rsync -av --relative core/foo.py agents/qa.py my-vps:/root/claudecode/aicom/

# 2. rebuild AND force the container to be replaced
ssh my-vps 'cd /root/claudecode/aicom \
  && TAG=prod-$(date +%Y%m%d-%H%M)-nogit \
  && AICOM_IMAGE_TAG=$TAG docker compose build app \
  && AICOM_IMAGE_TAG=$TAG docker compose up -d --force-recreate app'

# 3. prove the new code is actually inside the thing that is running
ssh my-vps 'docker exec aicom-app-1 ls -la /app/core/foo.py'
```

### Two ways this silently does nothing

**A reused tag does not recreate the container.** The first attempt used
`AICOM_IMAGE_TAG=prod-$(date +%Y%m%d)-nogit`, which on the day in question evaluated to
`prod-20260827-nogit` — *the tag already running*. `docker compose build` rebuilt and re-tagged
the image, then `up -d` compared the resolved service config, saw the same image reference, and
left the old container in place. Everything exited 0. `docker ps` still said `Up 3 hours`, and
the new files were absent from `/app`. Put a time in the tag, and pass `--force-recreate`.

**A one-shot management script cannot run on the host at all.** `ssh my-vps 'python3
scripts/enqueue_kleroterion.py'` exited 1 having written nothing, reporting only
`ERROR: append_product_to_pipeline_state failed`. Two different things are wrong, and the first
one hides the second:

- `core.paths.data_root()` resolves to `/app/data`, which is the path *inside* the container;
- and the host's system `python3` can import every factory module but **has none of the
  factory's dependencies** — the append dies at `create_sync_pipeline_manager()` with
  `ModuleNotFoundError: No module named 'aiosqlite'`, i.e. it cannot open the SQL store at all.

Setting `AIFACTORY_DATA_ROOT` fixes only the first. There is no host-side workaround for the
second, so run such scripts **inside** the container, where the data root and the dependency set
are the factory's own:

```bash
ssh my-vps 'docker exec aicom-app-1 python /app/scripts/enqueue_kleroterion.py'
```

That also means the script must be in the **image**, not just the tree — so it needs the rebuild
above first. **Rebuild, then exec.**

`scripts/enqueue_kleroterion.py` now refuses to start outside the container rather than failing
generically: it probes `create_sync_pipeline_manager()` and, on ImportError, exits 3 printing the
`docker exec` line. Worth copying into any other one-shot script that writes to the live store —
a failure indistinguishable from a different failure costs more than the check.

### Timing

A rebuild restarts the worker. If a product is mid-round (`DEV_FIXING`), that round is lost.
Check what is in flight first:

```bash
ssh my-vps 'cd /root/claudecode/aicom && python3 -c "
import sqlite3, datetime
c = sqlite3.connect(\"data/state/pipeline.db\")
for i, s, t in c.execute(\"select id, state, updated_at from products order by updated_at desc limit 3\"):
    print(i, s, datetime.datetime.fromtimestamp(t))
"'
```

Note `pipeline.json` is a **stale projection**, not the store — on 2026-08-27 it was three hours
behind the database. Read `pipeline.db`; `sqlite3` is not installed on the host, so use
`python3 -c` with the `sqlite3` module.

### Retention: delete the pre-previous tag after a verified deploy

Nothing removed old tags, so they accumulated until a build could not fit. On 2026-08-27 the
factory host held 36 images / 48.4 GB on a 77 GB disk, 22.6 GB of it unreferenced — including
seven `modelmarket-hub:prod-20260826-{zkdemo,zkdemo2..5,chrome,chrome2,chrome3}` tags from one
afternoon of debugging. With 11 GB free, the 13.1 GB factory rebuild failed at `[base 19/21]`,
the `chown -R` step whose own Dockerfile comment (line 155) warns it "exhausts disk on build".

Diagnosis, in order, because the daemon log only ever said `exit code: 1`:

* the four `chown` targets all exist (Dockerfile lines 114, 146-148) — not a missing path;
* `data/` (7.4 GB on the host) is excluded from the build context by `.dockerignore` line 47, so
  the layer is not bloated by it;
* `groupadd --system --gid 10001 && useradd --uid 10001` succeed on a clean `ubuntu:24.04`
  (verified with `docker run --rm`; only a harmless `uid greater than SYS_UID_MAX` warning), so
  the first half of the step is fine;
* which leaves the `chown` layer write, and free space. The same Dockerfile had built four hours
  earlier, when the previous 13.1 GB image was not yet occupying the disk.

So: **after a deploy is verified, drop the pre-previous tag.** Not before — the tag you are about
to delete is the one you roll back to if the new image is broken.

```bash
REMOTE=my-vps ./scripts/prune_stale_deploy_images.sh          # dry run
REMOTE=my-vps ./scripts/prune_stale_deploy_images.sh --yes    # apply
```

It keeps every tag any container references (including stopped ones — a stopped `*-prev`
container IS the rollback mechanism here) plus the newest `--keep` (default 2) per repository,
touches only `prod-*` tags so `:local` and `:latest` are never its business, and runs `docker rmi`
without `-f` so a still-referenced layer refuses instead of breaking its holder.

Two things that made this take longer than it should have, both worth avoiding:

* `pgrep -f "compose build app"` **matches the shell running it**, because the pattern is present
  in that shell's own command line. Every check reported "still building" for the better part of
  an hour after the build had already failed twice. Use the bracket trick — `ps aux | grep -E
  "compose[ ]build"` — or match on a pattern the checking command does not itself contain.
* `docker compose build` succeeding is not a deploy. Confirm the new tag exists
  (`docker images | grep <repo>`), that the container was actually replaced (`docker ps` uptime in
  seconds, not hours), and that a file you just added is inside it
  (`docker exec <c> ls /app/<newfile>`).
* **A tag existing is not a build succeeding.** buildkit names the image before it unpacks it, so
  a build that dies at `exporting to image` with `no space left on device` still leaves the tag
  behind — pointing at a PARTIALLY EXTRACTED image. One such image was 2.04 GB instead of 13.1 GB
  and looked plausible from the inside: `ms-playwright` was there, `fastapi` imported. A watcher
  that waited for the tag reported "BUILD OK". Wait for the container to be RUNNING the new tag,
  and grep the build log for `no space left|failed to solve|ERROR: failed` as a separate exit.
* **Recreate with the same compose file set the container was created with.** This stack is
  `docker-compose.yml` PLUS `docker-compose.dind.yml`, and `DOCKER_HOST: tcp://docker:2376` lives
  only in the overlay. `AICOM_IMAGE_TAG=… docker compose up -d --force-recreate app` — no `-f`
  flags — therefore produced a container with an EMPTY `DOCKER_HOST` that could not reach the
  docker daemon at all. Everything the obvious checks look at was green: right tag, uptime in
  seconds, `/api/health` ok, new files present. What broke was invisible from there — the sandbox
  fell back to SQLite (`postgres required but Docker unavailable`), so a product that declares
  Postgres was tested on the wrong database, and the developer was handed findings that were
  artifacts of the environment (`SQLAlchemy 2.x incompatible: db.query(User) on synchronous
  Session`, `shared SQLite engine`, `SQLite-specific connect_args`). Read the label before you
  recreate, and check the env after:

```bash
ssh my-vps 'docker inspect aicom-app-1 --format "{{index .Config.Labels \"com.docker.compose.project.config_files\"}}"'
ssh my-vps 'cd /root/claudecode/aicom && AICOM_IMAGE_TAG=<tag> docker compose -f docker-compose.yml -f docker-compose.dind.yml up -d --force-recreate app'
ssh my-vps 'docker exec aicom-app-1 sh -lc "echo \$DOCKER_HOST; docker ps --format \"{{.Names}}\" | head -3"'
```
