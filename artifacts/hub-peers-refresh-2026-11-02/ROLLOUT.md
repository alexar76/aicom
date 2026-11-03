# Hub page: the unapproved-hub list follows the hub (2026-11-02, about 05:31–05:33Z)

Owner: «Да, сделай», «сделай везде». The modelmarket.dev page still listed registry.modelmarket.dev under "Unapproved
hubs" after it was approved: `ensurePeers()` in `terminal-home.html` answered from its first fetch for the life of the
tab, although `poll()` calls it every 3 s.

**Change.** The cache now lasts one minute. `poll()` asks again after that, and a failed try waits a minute too, not 3 s.
The rail is redrawn only when the pending queue changed, so an open "Show what it offers" or a typed search survives the
refresh. `patch.py` applies the same edit to each production variant of the page:

| Variant (sha256 of the live page) | Hubs | Patched page |
|---|---|---|
| `1ea47818…` (= main) | modelmarket.dev | `variant-1ea4/` |
| `c68312a5…` | uni, hub.modelmarket.dev, hunt | `variant-c683/` |
| `cb598100…` | hub.attestedmemory.net | `variant-cb59/` |

The c683 and cb59 diffs are line for line the same. The main source `aimarket-hub/terminal-home.html` gets the 1ea4
edit.

## Checks before rolling

- **Syntax.** `node --check` passes on every page script. The JSON-LD block is not JS.
- **Behaviour, in a browser against live data.** `test_server.py` serves a patched page and proxies the rest to
  modelmarket.dev. It can add or remove a made-up pending hub.
  - Main variant: 3 list requests in about 2 minutes. A marker on the rail survived when the queue did not change. A
    hub added to the queue appeared within a minute and disappeared within a minute after removal. No console errors.
  - c683 variant: the added hub appeared within a minute, after 2 requests.
- **Hub tests.** The 12 hub test files that touch the page, 392 tests, 0 failures, 7 skipped.

## Rolled

Each image is built FROM the hub's running image with one COPY (`Dockerfile`). `build.sh` refuses if the live page is
not the variant the patch was made for, then checks the file inside the image and that the hub serves it from `/app`.
It handles both `ui_assets` and the older `pages.py` path. Then `/root/hub-3160-main-20261021/roll.sh` on each host
backs up the database, swaps the container, checks health and rolls back by itself on a failure.

| Hub | Host | Before (rollback image) | After | Previous container | DB backup |
|---|---|---|---|---|---|
| uni.modelmarket.dev | factory-vps | `modelmarket-hub-uni:hf-20261101` | `:pr-20261102` | `modelmarket-hub-uni-security-prev-1793597459227998499` | `/app/data/hub-backup-pre-3160-20261102T053058Z.db` |
| modelmarket.dev | factory-vps | `modelmarket-hub:hf-20261101` | `:pr-20261102` | `modelmarket-hub-security-prev-1793597480477757269` | `/app/data/hub-backup-pre-3160-20261102T053119Z.db` |
| hub.modelmarket.dev | competing-lab | `modelmarket-hub:hf-20261101` | `:pr-20261102` | `modelmarket-hub-security-prev-1793597506333528895` | `/app/data/hub-backup-pre-3160-20261102T053145Z.db` |
| hunt.modelmarket.dev | competing-lab | `signal-hunt-hub:hf-20261101` | `:pr-20261102` | `signal-hunt-hub-1-security-prev-1793597525827273468` | `/root/hub-backups/signal-hunt-hub-1-pre-3160-20261102T053205Z.dump` |
| hub.attestedmemory.net | attested | `attested-memory-hub:hf-20261101` | `:pr-20261102` | `attested-memory-hub-hub-1-security-prev-1793597546963364033` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261102T053226Z.dump` |

Independent (independentai.network/hub) has no unapproved-hub panel on its page, so nothing to change.

**Verified at 05:32Z** (`outside-check.log`). Health and `/federation/peers` answer 200 on all five, and the public page
carries the refresh on four. hunt.modelmarket.dev serves the Signal Hunt game at `/`, not the hub page; the hub's own
page on `127.0.0.1:9084` carries it.

**Rollback**, per hub: `rollout_container.py <container> --image <before image> --health <url>` from
`/root/hub-3160-main-20261021`, or start the stopped previous container. The compose trap still applies: hunt and
attested are compose services, and `docker compose up` there would recreate them from the compose image
(`:hf-20261101`), dropping this page fix.

Logs: `build-*.log`, `roll-*.log`. Contexts: `/root/pr-20261102/` on each host.
