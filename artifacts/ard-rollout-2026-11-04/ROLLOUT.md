# ARD door on all six hubs — 2026-11-04

Owner: «выкатывай на хабы, проверяй всё вживую». Code: aicom 48502f8d3 (aimarket-hub 3.18.0, the ARD door,
`aimarket-hub/docs/ard.md`) and 5afc6a48b (search results carry `version`). Both on Gitea main. All times are server
clocks (UTC).

## What changed on the hubs

Each hub serves `/.well-known/ard.json` (`application/ard+json`), `Link: <…/.well-known/ard.json>; rel="ard"` on
`HEAD /`, `/.well-known/did.json` (`did:web`) and the ARD registry at `/ard/v1`. Nothing else in a hub changed;
AIMarket Protocol v2 is untouched.

The live hubs run two `api.py` variants that are not main's: modelmarket.dev `ccd534b4f320` (3.17.0), the other
five `a344cb9f4760` (3.16.0). Every module the door imports (`hub_routes/catalog.py` search with scores,
`catalog.catalogue_display_name`, `access_policy.capability_access_mode`, `public_cache.PublicDocumentCache`,
`Signer.sign`, `Capability.tool_name`, `awr.jcs`, `api._catalogue_snapshot`) was checked in each image and venv
before building (`verify_live.py`'s sibling probe, see the session notes). So the overlay is three files:
`ard.py`, `hub_routes/ard.py` (both new) and the live `api.py` with the door registered by `kit/patch_api.py`,
which refuses any other variant or a missing anchor.

## Two rounds

1. **08:34–08:41Z, `:ard-20261104`.** `kit/build.sh` built FROM each hub's running `:pr-20261102` image, ran
   `kit/smoke.py` inside it with no network and no hub settings (a throw-away hub on a temp DB: manifest, signatures,
   digests, search, problem details, health, the discovery document), and compared the three files in the image with
   the context. `/root/hub-3160-main-20261021/roll.sh` backed up each database and swapped the container.
2. **08:44–08:45Z, `:ard2-20261104`.** The outside check on modelmarket.dev found that a signed search result did not
   carry `version`, which its `trustManifest` subject binds: a verifier comparing the subject with the result
   (draft-bu-dawn-ard-discovery-00 §3.5.1) would reject every signed local result. Fixed in 5afc6a48b (the test now
   compares the whole subject), rebuilt with `fix2/` (only `ard.py`, FROM `:ard-20261104`; the smoke checks the
   whole subject too) and rolled again. The other hubs' first-round checks had passed only because their "weather"
   results were all from peers, which are unsigned.

| Hub | Host | Before | After | Previous containers (round 1 / round 2) | DB backups (round 1 / round 2) |
|---|---|---|---|---|---|
| uni.modelmarket.dev | factory-vps | `modelmarket-hub-uni:pr-20261102` | `modelmarket-hub-uni:ard2-20261104` | `modelmarket-hub-uni-security-prev-1793781257535751906` / `-1793781850321562740` | `/app/data/hub-backup-pre-3160-20261104T083416Z.db` / `…T084409Z.db` |
| hub.modelmarket.dev | competing-lab | `modelmarket-hub:pr-20261102` | `modelmarket-hub:ard2-20261104` | `modelmarket-hub-security-prev-1793781379507463958` / `-1793781856365804324` | `/app/data/hub-backup-pre-3160-20261104T083619Z.db` / `…T084415Z.db` |
| hunt.modelmarket.dev | competing-lab | `signal-hunt-hub:pr-20261102` | `signal-hunt-hub:ard2-20261104` | `signal-hunt-hub-1-security-prev-1793781409442984098` / `-1793781862093537953` | `/root/hub-backups/signal-hunt-hub-1-pre-3160-20261104T083648Z.dump` / `…T084421Z.dump` |
| hub.attestedmemory.net | attested | `attested-memory-hub:pr-20261102` | `attested-memory-hub:ard2-20261104` | `attested-memory-hub-hub-1-security-prev-1793781619605041223` / `-1793781883028766879` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261104T084018Z.dump` / `…T084442Z.dump` |
| modelmarket.dev | factory-vps | `modelmarket-hub:pr-20261102` | `modelmarket-hub:ard2-20261104` | `modelmarket-hub-security-prev-1793781673431410815` (+ THEMIS `themis-security-prev-1793781673431410815`) / `-1793781921559209746` | `/app/data/hub-backup-pre-3160-20261104T084112Z.db` / `…T084520Z.db` |
| independentai.network/hub | indep (venv) | `/root/ard-20261104/indep/backup-api.py` (a344cb9f4760); no `ard.py` | the three files in `hub-3.16.0-rpc-security-20261031` | — | none needed |

Apex was checked on :9083 and THEMIS :9460/health; THEMIS borrows the hub's network namespace and was recreated
healthy both times. No OS rollout was running before any roll. The alerter showed nothing new.

Independent: the smoke ran on a patched copy of the venv's package under the venv's Python, then the three files
were installed (api.py `2af1af8d4fbd`, ard.py `0457a7cd44ef`, hub_routes/ard.py `6b562d6121e5`) and the service was
restarted in a separate command at 08:46:23Z; healthy after about 6 s.

## nginx

- **hunt.modelmarket.dev** (competing-lab, `/etc/nginx/sites-available/hunt.modelmarket.dev`): `location /` is the
  game, so the hub paths are named. Added exact locations for `/.well-known/ard.json`, `/.well-known/did.json`,
  `/.well-known/mcp/server-card.json` (it was going to the game and answering 404, so the manifest's digest of the
  MCP card could not have matched) and `^~ /ard/`; then `location = /` with the game proxy, the four server-level
  security headers repeated (an `add_header` in a location drops the inherited ones) and the `Link`. Backups:
  `/root/ard-20261104/hunt.modelmarket.dev.pre-ard-20261104` (before both) and `…pre-ard-root-20261104` (before the
  root block). `kit/hunt_root_link.py` made the root edit. The repo template `deploy/nginx/hunt.modelmarket.dev.conf`
  has the same blocks.
- **independentai.network** (indep, `/etc/nginx/sites-enabled/independentai.network`, a plain file): the hub lives
  under `/hub`, so the origin's `/.well-known/ard.json` answers one 302 to `/hub/.well-known/ard.json` (initial
  contact allows one redirect). Backup `/root/ard-20261104/indep/independentai.network.pre-ard-20261104`;
  `kit/indep_root_redirect.py`. The hub-under-a-path example in `aimarket-hub/docs/production-deployment*.md` has the
  same line.

Right after each nginx reload, the first request or two can still reach an old worker (a 404, or a response without
the new header); a few seconds later every request has the new configuration.

## Verified from outside (after the second round and the Independent restart)

`verify_live.py` on each hub, with `rfc8785` and `cryptography` (not the hub's code): the well-known as
`application/ard+json`, cacheable; `Link rel="ard"` on `HEAD /`; every digest against the bytes served at its url
over the internet; every trustManifest of the hub's own entries under the key of the live `did.json`, subject equal
to the entry or result; peers' listings unsigned with the peer as `source`; search, agents paging, explore, problem
details for an unknown filter; health. Logs in `verify/`.

| Hub | Result |
|---|---|
| modelmarket.dev | ALL OK, 43 checks (a signed local result, weather.witness@v1, verifies) |
| uni.modelmarket.dev | ALL OK, 35 |
| hub.modelmarket.dev | ALL OK, 41 |
| hunt.modelmarket.dev | ALL OK, 41 |
| hub.attestedmemory.net | ALL OK, 41 |
| independentai.network/hub | ALL OK, 32 (no did:web, entries unsigned as designed; origin redirect works) |

The live manifest, agents page and search response of modelmarket.dev, hub.attestedmemory.net and
independentai.network/hub validate against the drafts' CDDL (`aimarket-hub/docs/ard-conformance/`; the samples there
are now the live modelmarket.dev responses). On all six hubs health, both discovery documents, `/ai-market/v2/search`,
the A2A card, the MCP card and `/ai-market/v2/manifest` answer 200.

## Rollback

Per container hub: `cd /root/hub-3160-main-20261021 && python3 rollout_container.py <container> --image <before
image> --health <url>` (or start the stopped previous container). The databases are unchanged by the door (no
migration). Independent: copy `/root/ard-20261104/indep/backup-api.py` back over the venv's `api.py`, delete
`ard.py` and `hub_routes/ard.py`, restart `independentai-hub`. nginx: restore the backups above, `nginx -t`, reload.

The compose trap still applies: hunt and attested are compose services, and `docker compose up` there would recreate
them from the compose image, dropping the door.

## Files

`kit/` (round 1: Dockerfile, build.sh, patch_api.py, smoke.py, the two nginx edit scripts), `fix2/` (round 2),
`verify_live.py`, `logs/` (build and roll logs of both rounds from each host), `verify/` (outside checks).
Contexts: `/root/ard-20261104/` on each host.

## Follow-up: links in the DAWN mail (2026-11-04, about 10:15Z server time)

The feedback mail went out with "(https://histor.modelmarket.dev/datasets/mcp-protocol-eras-2026-11-01/)." and two URLs
followed by a full stop; a mail client glued ")" and "." into the links, which answered 404. Server-side fixes, the clean
addresses unchanged (200, no redirect):

- **histor.modelmarket.dev** (admin-vps, `/etc/nginx/sites-available/histor.modelmarket.dev`): inside
  `location ^~ /datasets/`, a trailing `) . , ;` is dropped with a 301 (`kit/histor_trailing_punct.py`; backup
  `/root/histor.modelmarket.dev.pre-trailing-20261104`).
- **modelmarket.dev** (factory-vps, `/etc/nginx/sites-available/modelmarket.dev`): `location = /.well-known/ard.json.`
  301 to the manifest (`kit/apex_ard_trailing_dot.py`; backup `/root/ard-20261104/modelmarket.dev.pre-trailing-20261104`).
- The GitHub link with a full stop is GitHub's to answer; it cannot be redirected from here.

The repo copies (`histor/deploy/nginx/histor.modelmarket.dev.conf`, `deploy/nginx/modelmarket.dev.conf`) carry the
same lines. Lesson: in plain-text mail never put a URL in parentheses or right before punctuation.
