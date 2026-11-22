# ARD + AID stale cases on modelmarket.dev (2026-11-22)

For Balázs Nemethi's ARD + AID interop test (dawn@ietf.org thread "New drafts: Agentic Resource Discovery", private mail
"ModelMarket and AID"). He tested the healthy case (live ARD manifest, MCP Server Card at /mcp/server-card, AID record
`_agent.modelmarket.dev`) and asked for two stale cases, one fault each, at their own paths. Field agreed on 2026-11-22:
the streamable-http entry's `remotes[].url` in the card is compared with the AID `u`.

| Case | Manifest | Fault |
|---|---|---|
| healthy | https://modelmarket.dev/.well-known/ard.json | none |
| endpoint-mismatch | https://modelmarket.dev/interop/aid/endpoint-mismatch/ard.json | card `remotes[].url` = `/interop/aid/endpoint-mismatch/mcp`, not the AID u |
| card-digest-mismatch | https://modelmarket.dev/interop/aid/card-digest-mismatch/ard.json | entry digest pins card version 1.2.0; the card served is 1.3.0 |

List with expected results: https://modelmarket.dev/interop/aid/index.json

## How they were made

- `build_fixtures.py` ran inside the apex hub container (`modelmarket-hub:3.22.0-extblock-20261121` on factory-vps) on
  2026-11-22 ~06:00Z, with the live card as served (sha256 63557deb…, the digest the live manifest pins). The
  trustManifests are signed by the hub's key under `did:web:modelmarket.dev`, through the same `aimarket_hub.ard`
  functions as the live manifest; each manifest holds one MCP entry.
- The output is `fixtures/`, byte for byte what is served. Copy on the host: `/root/aid-stale-cases-20261122/fixtures`.
- Served as static files from `/var/www/interop/aid/` inside the existing `location ^~ /interop/` (CORS `*`,
  `Cache-Control: public, max-age=300`). The interop timer writes only `index.html` and `interop.json` there.
- Two nested nginx locations (owner «Да, правь nginx», 2026-11-22 ~06:15Z) give the manifests `application/ard+json`
  and the cards `application/mcp-server-card+json`, as on the live documents; `index.json` stays `application/json`.
  Change: `nginx-change.diff`; same block in `deploy/nginx/modelmarket.dev.conf`. Before-copy on the host:
  `/root/aid-stale-cases-20261122/modelmarket.dev.nginx.before` (restore it and `nginx -t && systemctl reload nginx`
  to undo). Checked after reload: `/interop/`, `/interop/interop.json`, `/.well-known/ard.json`, `/mcp/server-card`,
  `/blog/` and `/` unchanged; an unknown case path is 404.

## Check

`check_fixtures.py` (python3 + cryptography), run from skopos-vps: reads u from DNS over HTTPS, verifies each MCP
entry's trustManifest against the Ed25519 key in did.json, fetches the card, compares its bytes with the digest and
its streamable-http url with u. `check-2026-11-22.log`: all three give their expected result, exit 0.

## Removal

`rm -r /var/www/interop/aid` on factory-vps (files this session created; nothing else uses them) and the two
nested locations. The signatures stay
valid while the hub's Ed25519 key is unchanged; after a key rotation rerun `build_fixtures.py` and reinstall.
