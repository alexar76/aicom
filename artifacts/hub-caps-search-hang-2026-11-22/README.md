# Hub page: the capability search froze the tab (2026-11-22, live 07:01–07:04Z)

Owner, 22.11, with a screenshot of the "Available capabilities" panel on modelmarket.dev and "4" typed in its search
box: «зависает на хабе при попытке поиска».

## Cause

The panel loads the catalogue 250 capabilities a page. Typing in its search box called `drainCaps()`:

```js
async function drainCaps() {
  while (capsHasMore) await loadCapsPage(false);
}
```

`loadCapsPage()` returned at once when a page was already loading (`if (capsLoadingMore) return;`). A second
keystroke, or a scroll, while the next page was in flight made that loop await an already-resolved promise forever:
an endless chain of microtasks, so the tab stopped answering and the pending request could never complete. The code
is old (hub 3.17); it began to bite once a hub listed more than one page: modelmarket.dev 310, hub.modelmarket.dev
310, hunt.modelmarket.dev 280, hub.attestedmemory.net 284 (uni has 92 and was not affected).

Reproduced in a browser before the fix: on the unpatched page (served locally, the second page held 1.5 s), two
keystrokes 150 ms apart and the tab no longer ran even a one-line script (45 s timeout).

## Change (`patch.py`)

- One page request at a time, shared by every caller: `loadCapsPage()` returns the request in flight instead of
  returning early.
- `drainCaps()` stops when a page adds nothing (and after 40 pages), so a hub that keeps answering `has_more` cannot
  keep the tab busy.
- The search box paints the matches among what is already loaded at once, and only the latest keystroke repaints
  after the remaining pages arrive.

The three production variants of the page carry this code byte for byte, so one patch fits all:

| Variant (sha256 of the live page) | Hubs | Patched |
|---|---|---|
| `c8a005ac…` (= main) | modelmarket.dev | `a4168f86…` |
| `a915a3af…` | hub.modelmarket.dev, hunt.modelmarket.dev | `6a50b031…` |
| `32962117…` | hub.attestedmemory.net | `9236ad14…` |

`aimarket-hub/terminal-home.html` gets the same edit (it is the c8a0 variant).

## Checks

- `node --check` on every page script of the four patched pages.
- Browser, patched page served locally with live data from modelmarket.dev and the second page held 1.5 s
  (`test_server.py`): three keystrokes in 230 ms, no freeze, the second page requested once, "7 of 310 for «x4»".
- `aimarket-hub/tests/terminal_caps_search.test.cjs` runs the page's own functions with a late fetch: keystrokes during
  a page load finish and find matches from every page; a hub stuck on `has_more` stops; concurrent loads share one
  request. 3/3 on the new page; on the old page the run hangs and is killed by its timeout. Hub node tests 22/22.

## Rolled (owner: «Да, на все три», after the canary)

Kit on each host: `/root/hub-capsfix-20261122/kit`. `build.sh CONTAINER VARIANT TAG` builds FROM the container's
running image with the one file, and refuses unless the live page is that variant; `roll.sh` backs up the database
and swaps the container with `rollout_container.py` (restores the previous container if a health URL fails).

| Hub | Host, container | Switched (UTC) | Image | Previous container (rollback) | Database backup |
|---|---|---|---|---|---|
| hub.modelmarket.dev (canary) | competing-lab, `modelmarket-hub` | 07:01:19 | `modelmarket-hub:3.22.0-capsfix-20261122` | `modelmarket-hub-security-prev-1795330880107265315` | `/root/hub-backups/modelmarket-hub-pre-capsfix-20261122T070119Z.db` |
| modelmarket.dev | factory-vps, `modelmarket-hub` (+ THEMIS) | 07:02:41 | `modelmarket-hub:3.22.0-capsfix-20261122` | `modelmarket-hub-security-prev-1795330962833642645` | `/root/hub-backups/modelmarket-hub-pre-capsfix-20261122T070241Z.db` |
| hunt.modelmarket.dev | competing-lab, `signal-hunt-hub-1` | 07:03:12 | `signal-hunt-hub:3.22.0-capsfix-20261122` | `signal-hunt-hub-1-security-prev-1795330993273441961` | `/root/hub-backups/signal-hunt-hub-1-pre-capsfix-20261122T070312Z.dump` |
| hub.attestedmemory.net | attested, `attested-memory-hub-hub-1` | 07:03:57 | `attested-memory-hub:3.22.0-capsfix-20261122` | `attested-memory-hub-hub-1-security-prev-1795331038683754892` | `/root/hub-backups/attested-memory-hub-hub-1-pre-capsfix-20261122T070357Z.dump` |

The first canary attempt stopped before the swap (the kit lacked `service_env.py`; the container was untouched). On
attested the container ran from a bare image id, which BuildKit cannot take in `FROM`; `build.sh` now tags it
`attested-memory-hub:capsfix-base-20261122` first.

**Verified** (`outside-check.log`; its first line is the Mac clock, about 58 min fast: server time about 07:04Z): the four public pages (hunt's hub page on its host's
127.0.0.1:9084; hunt.modelmarket.dev serves the game at `/`) carry the fix; all four containers healthy, 0 restarts,
0 tracebacks. Browser on https://modelmarket.dev/: five quick searches ending in "attest" gave "86 of 310", no freeze.

**Rollback**, per hub: `python3 rollout_container.py <container> --rollback` in the host's kit folder, or start the
kept previous container. The compose trap still applies to hunt and attested: `docker compose up` there recreates
them from the compose image and drops this page fix.

Logs: `roll-*.log`, `outside-check.log`.
