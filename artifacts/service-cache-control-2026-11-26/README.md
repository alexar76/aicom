# basanos, themis, skopos: validity instead of no-store on the catalogue — 2026-11-26

**Why.** After hub 3.22.3 (../hub-http-validity-2026-11-26) the hubs read a peer's Cache-Control on its catalogue.
These three of our services sent `Cache-Control: no-store` on every response, the signed catalogue included, which
the hubs read as "no validity": their entries were held only two crawl intervals after a failed read (10 minutes on
hub.modelmarket.dev and hunt, 2 hours elsewhere). Owner: «Да, исправь».

**Change** (main 97da44ad9, commit b789dd05b): `/ai-market/v2/manifest` → `public, max-age=300, stale-if-error=172800`,
`/.well-known/ai-market.json` → `public, max-age=60, stale-if-error=172800`, both with a weak ETag over the content
without `signature` and `generated_at` (re-signed per request) and 304 on If-None-Match. Every other response stays
`no-store` (basanos/themis middleware now sets it only where the route set nothing; skopos `_send_document` next to
`_send_json`). Tests: one per service; basanos 111 passed, themis 185 passed; skopos new test passes, its local suite
has the same 69 failures + 4 collection errors on main (environment), failure lists identical.

## Rollout (one-file overlays FROM the running image; `rollout_container.py`, kit `kit/`, hosts `/root/svc-cachectl-20261126`)

Each live file was byte-identical to main before the change (basanos agent.py `e8e34a2b90f7`, themis agent.py
`2f98288adb1e`, skopos api_server.py `6182e7d6dfae`). Dry runs: no env names dropped, no borrowers.

| service | host, container | switched (UTC) | image | rollback (previous container) |
|---|---|---|---|---|
| basanos.modelmarket.dev | admin-vps `basanos-basanos-1` | 17:52:35Z | `aicom-security:basanos-basanos-1-cachectl-20261126` | `basanos-basanos-1-security-prev-1795715555196588090` |
| themis.modelmarket.dev | factory-vps `themis` (in modelmarket-hub's network namespace) | 17:52:51Z | `themis:cachectl-20261126` FROM the running image, tagged `themis:running-pre-cachectl-20261126` (it had no tag) | `themis-security-prev-1795715572388276145` |
| skopos.modelmarket.dev | skopos-vps `metis-skopos` | 17:52:58Z | `aicom-security:metis-skopos-cachectl-20261126` | `metis-skopos-security-prev-1795715578642352053` |

Rollback: `cd /root/svc-cachectl-20261126 && python3 rollout_container.py <container> --rollback`. No data change.

## Checks

- All healthy after the switch (basanos 9470/health, themis 9460/health with the apex hub unaffected, skopos
  8502/healthz). Locally: the manifests carry the headers; /health and /agent/ping stay `no-store`.
- From outside, all six documents (manifest + discovery document on the three domains): the headers above and 304
  on a matching If-None-Match.
