# Production domain — modelmarket.dev

Canonical public origin for the **AIMarket Federation Hub**: **`https://modelmarket.dev`**.

## DNS

Point **A/AAAA** records for `modelmarket.dev` and `www.modelmarket.dev` to the host running nginx (this fleet: `modeldev.modelmarket.dev`).

### Ecosystem landing — `modeldev.modelmarket.dev`

Public ecosystem map (`ecosystem-landing/`) plus **SEO landings** (`/learn/`, `/oracles/`, `/guides/`, `/encyclopedia/`, `sitemap.xml`). Built by `./scripts/build_ecosystem_landing.sh` before deploy. See [`seo-landings/README.md`](../seo-landings/README.md).

DNS at **Timeweb**:

| Host | Type | Value |
|------|------|-------|
| `modeldev` | A | `<origin-ip>` |

One-shot (root):

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-modeldev-ecosystem-landing.sh
```

Routine refresh after editing `ecosystem-landing/` (also runs automatically from `./scripts/deploy_ecosystem.sh`):

```bash
sudo ./scripts/deploy_ecosystem_landing.sh
```

Verify:

```bash
curl -sI https://modeldev.modelmarket.dev/ | head -5
curl -s https://modeldev.modelmarket.dev/ | grep -o '<title>[^<]*</title>'
curl -sI https://modeldev.modelmarket.dev/sitemap.xml | head -3
curl -sI https://modeldev.modelmarket.dev/oracles/platon/ | head -3
./scripts/verify_seo_landings.sh
```

### Provenance verifier — `verify.modelmarket.dev`

Static client-side receipt verifier (`docs/verifier/` — Ed25519 via tweetnacl, no backend). Served by the **factory host** (same fleet as modeldev). Receipts' `verify_url` (`AIMARKET_VERIFY_DOMAIN`) points here.

| Subdomain | Type | Value |
|-----------|------|-------|
| `verify` | A | `<origin-ip>` |

Deploy (on the factory host):

```bash
rsync -a --delete docs/verifier/ /var/www/verify.modelmarket.dev/

# FIRST TIME ONLY. The live conf is /etc/nginx/sites-available/verify.modelmarket.dev
# (no .conf suffix) and certbot has since added the TLS server block to it IN PLACE.
# Copying the repo template over it drops HTTPS — patch the live file instead.
sudo cp deploy/nginx/verify.modelmarket.dev.conf /etc/nginx/sites-available/
sudo ln -sf /etc/nginx/sites-available/verify.modelmarket.dev.conf /etc/nginx/sites-enabled/
sudo certbot --nginx -d verify.modelmarket.dev

sudo nginx -t && sudo systemctl reload nginx
```

**Deployed 2026-08-02 — AWR/2.** The host had been serving the pre-AWR/2 file (10 714 bytes
against 123 238 in the repo), i.e. a verifier that could not check a single AWR/2 receipt,
at the domain SPEC.md names as the place to check them. Now live and verified end to end: a
real receipt returns `valid: true` through the bytes served from the host, and the browser
tool loads the example and reports **Верифицировано**.

Two things shipped with it:

- `ns/awr/v2.jsonld`, served by a `location = /ns/awr/v2` block placed **before** the SPA
  fallback. `try_files $uri $uri/ /index.html` had been answering the namespace URI with the
  verifier's HTML page and a 200 — a JSON-LD consumer asking for a context got success and
  text/html. It now returns `application/ld+json` with CORS open, and a real `jsonld`
  processor expands every valid vector under it.
- Seven links to `hub.aimarket.org`, a domain this project does not own, replaced with
  `modelmarket.dev`. They were dead links on a live public page, including the one labelled
  "API Docs".

The live nginx conf is **patched in place, not overwritten**: certbot owns the TLS block in
it, and copying the repo template (HTTP-only) over it would drop HTTPS. A timestamped
backup sits beside it as `verify.modelmarket.dev.bak-<ts>`.


Verify:

```bash
curl -sI https://verify.modelmarket.dev/ | head -5
curl -s https://verify.modelmarket.dev/ | grep -o '<title>[^<]*</title>'
```

### Platon oracle — `oracles.modelmarket.dev`

**Platon Shadow Oracle** runs on **`oracles.modelmarket.dev`**. DNS at **Timeweb** points the subdomain **directly** to that host (no factory nginx proxy).

> **Note:** `oracles/` and `platon/` in this monorepo are **archival mirrors** of the external oracle stack. They are **not** deployed by `./scripts/deploy_ecosystem.sh` — run setup on the Platon host only.

| Host | Type | Value |
|------|------|-------|
| `oracles` | A | `<origin-ip>` |

After DNS propagates, on **the Platon server** (`oracles.modelmarket.dev`, root):

```bash
# Platon app: PUBLIC_URL=https://oracles.modelmarket.dev, listen 127.0.0.1:8080
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-oracles-platon-on-host.sh
```

From the factory host, register in federation:

```bash
./scripts/announce-platon-oracles.sh
```

Verify:

```bash
curl -s https://oracles.modelmarket.dev/.well-known/ai-market.json | jq '{hub_url, manifest_url, capabilities_count}'
curl -s https://oracles.modelmarket.dev/api/health | jq '{status, kappa, order_parameter}'
```

## Stack layout

| Service | Host port | Notes |
|---------|-----------|--------|
| AIMarket Hub (Docker) | `127.0.0.1:9083` → container `9080` | `modelmarket-hub` container |
| nginx | `:80` / `:443` | TLS termination, proxy to hub |

AI-Factory UI remains on **magic-ai-factory.com** (`:9080`). The hub seeds federation from  
`https://magic-ai-factory.com/.well-known/ai-market.json`.

## One-shot setup (root)

```bash
sudo CERTBOT_EMAIL=you@example.com /path/to/aicom/scripts/setup-modelmarket-ssl.sh
```

Or manually:

```bash
sudo cp deploy/nginx/modelmarket.dev.conf /etc/nginx/sites-available/modelmarket.dev
sudo ln -sf /etc/nginx/sites-available/modelmarket.dev /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

docker build -f aimarket-hub/Dockerfile -t modelmarket-hub:latest .
docker run -d --name modelmarket-hub --restart unless-stopped \
  -p 127.0.0.1:9083:9080 \
  -e AIMARKET_HUB_NAME=modelmarket.dev \
  -e AIMARKET_HUB_URL=https://modelmarket.dev \
  -e AIMARKET_SEED_LIST=https://magic-ai-factory.com/.well-known/ai-market.json \
  -v modelmarket_hub_data:/app/data \
  modelmarket-hub:latest

sudo certbot --nginx -d modelmarket.dev -d www.modelmarket.dev \
  --non-interactive --agree-tos --redirect -m you@example.com
```

## Pending deploy — hub federated transport (prepared 2026-08-01, NOT deployed)

Commit `0c0b7e65` fixes routed invokes of federated capabilities. **Not on prod:** the
running container is still `modelmarket-hub:prod-20260731-prices` (started 2026-07-31).
Nothing on the host was modified while preparing this — every check was a read.

**What it changes.** Transport for a routed invoke was picked by matching the peer's
self-declared categories against a hardcoded list (`oracle`, `simulation`, `math-viz`,
`randomness-beacon`); every other peer got the legacy
`/capabilities/{product}/{cap}/invoke` path regardless of what it advertised. GAIA
declares `["iot","sensors","physical-data","verification"]` and advertises
`mcp_endpoint: https://iot.modelmarket.dev/ai-market/v2/invoke`, so its readings answered
405 through the hub while working when called directly. Reproduce the bug against the
current prod build:

```bash
curl -s -X POST https://modelmarket.dev/ai-market/v2/invoke -H 'content-type: application/json' -d '{"product_id":"gaia.gateway","capability_id":"gaia.weather.read@v1","source_hub":"https://iot.modelmarket.dev","input":{"device_id":"nws-01"}}'
```

Today that returns `502 {"detail":"Provider returned 405"}`. After the deploy it should
return a signed reading. That curl is the acceptance test.

**The delta is exactly two runtime files.** Verified by hash: prod's
`aimarket_hub/api.py` and `crawler.py` are byte-identical to commit `88d8d66e`, the
parent of the fix, so nothing else in `/root/aicom-hub-build` needs to move.

```bash
rsync -a aimarket-hub/aimarket_hub/api.py aimarket-hub/aimarket_hub/crawler.py \
  factory-host:/root/aicom-hub-build/aimarket-hub/aimarket_hub/
```

**Then rebuild and restart with the configuration the running container actually has** —
it was started by `scripts/deploy_hub.sh`, but with `AIFACTORY_DATA_ROOT` pointing at the
factory checkout, not the build dir. Omitting it silently swaps the `/factory_data` mount:

```bash
ssh factory-host 'cd /root/aicom-hub-build && AIFACTORY_DATA_ROOT=/root/claudecode/aicom/data AIMARKET_HUB_IMAGE=modelmarket-hub:prod-20260801-fedtransport ./scripts/deploy_hub.sh'
```

Health is `/.well-known/ai-market.json` (there is no `/health` route — the container's own
healthcheck uses the well-known). Rollback is one command, since the previous image stays
on the host:

```bash
ssh factory-host 'docker rm -f modelmarket-hub && cd /root/aicom-hub-build && AIFACTORY_DATA_ROOT=/root/claudecode/aicom/data AIMARKET_HUB_IMAGE=modelmarket-hub:prod-20260731-prices ./scripts/deploy_hub.sh'
```

**Pre-deploy gate already run**, by building the image locally and running the suite
inside it — worth knowing that this is the only way to run these tests at all: the hub's
own venv is Python 3.9 (no `StrEnum`) and the root venv has a fastapi/starlette skew, so
both abort every app-building test at fixture setup. In the image: **1097 passed**, and
the 11 `test_db_backend::TestSplitAliasedDatabase` errors plus one
`test_supply_security` concurrency failure reproduce identically with the pre-change
sources mounted, so they are pre-existing. The gate also caught a real bug that local
runs could not see — a process-global endpoint cache leaking across app instances — now
cleared in `create_app()`.

### Clean-build gate (AWR/2 provenance plugin) — cleared

Both blockers that stopped shipping the AWR/2 provenance migration are resolved:

1. **`awr` is not on PyPI.** The Dockerfile copies `awr/reference/python` and
   `pip install`s it *before* the provenance plugin, so
   `awr>=2.0,<3` resolves from the build context rather than PyPI.
2. **`ResolutionImpossible` on `pip install -e ".[escrow]"`** was a transient PyPI
   resolver failure above the plugin change (it had succeeded on earlier builds the
   same day). A subsequent clean `docker build -f aimarket-hub/Dockerfile` exits 0:
   hub + escrow extras, `awr` 2.0.0, and the provenance plugin all install, and the
   app starts. The route-registration test was also brittle under FastAPI 0.141
   (`_IncludedRouter` has no `.path`); it now walks `original_router` so the suite
   passes in the shipping image, not only the older local venv.

## Automatic renewal

Ubuntu **`certbot.timer`** runs `certbot renew` twice daily and reloads nginx when a cert is renewed.

```bash
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer
sudo certbot renew --dry-run --cert-name modelmarket.dev
```

## Hub environment

| Variable | Example |
|----------|---------|
| `AIMARKET_HUB_NAME` | `modelmarket.dev` |
| `AIMARKET_HUB_URL` | `https://modelmarket.dev` |
| `AIMARKET_SEED_LIST` | `https://magic-ai-factory.com/.well-known/ai-market.json,https://oracles.modelmarket.dev/family/.well-known/ai-market.json,https://iot.modelmarket.dev/.well-known/ai-market.json` |
| `AIMARKET_SKIP_SEED` | `1` in production — otherwise a hub whose catalogue is empty seeds twelve showcase rows with no execution path, which inflate the storefront count without being invocable |

`AIMARKET_SEED_LIST` **replaces** the committed
[`federation_seeds.json`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/federation_seeds.json) rather than adding
to it, so a seed missing from the env var is a seed the deployed hub never crawls. Note the
oracle URL: `/family/.well-known/ai-market.json` is the aggregate of all 17 oracles (42
capabilities). The bare `https://oracles.modelmarket.dev/.well-known/ai-market.json` is **Platon
alone** (11) — seeding that one is why prod listed 11 while the docs described 42.

## Public URLs on the other hosts

Every node advertises its own reachable address in its `.well-known/ai-market.json`. These are
per-host env vars, not hub settings, and a wrong one is invisible to health checks — the node
answers 200, the hub records the peer, and only the *capabilities* silently never arrive.

| Host | Variable | Must be |
|------|----------|---------|
| factory (`magic-ai-factory.com`, `aicom-app`) | `AIFACTORY_PUBLIC_URL` | `https://magic-ai-factory.com` — it is copied verbatim into `manifest_url`/`mcp_endpoint`, so `http://localhost:9080` (the container-local default) publishes a URL only the factory itself can reach |
| oracle (`oracles.modelmarket.dev`, `platon-backend`) | `PLATON_PUBLIC_URL` | `https://oracles.modelmarket.dev` — the compose default is a raw-IP `http://` origin whose `/ai-market/v2/manifest` 404s |
| GAIA (`iot.modelmarket.dev`) | `GAIA_PUBLIC_URL` | `https://iot.modelmarket.dev` |
| oracle family | `ORACLE_FAMILY_PUBLIC_URL` | `https://oracles.modelmarket.dev/family` |

## Troubleshooting: catalogue shows 0 (or only demo rows)

Verify the advertised URLs before anything else — `deploy_hub.sh` runs this at the end of every
deploy, and it can be run on its own at any time:

```bash
python3 scripts/verify_federation_urls.py --hub https://modelmarket.dev
```

It checks that every advertised `manifest_url`/`mcp_endpoint` is a public https hostname (not
`localhost`, not a raw IP), that each manifest actually fetches and lists capabilities, that a
seed's pinned signer key matches the manifest's, and that the hub indexed something from peers
that advertise capabilities.

Symptoms and what they mean:

| What you see | Cause |
|---|---|
| `peers_count: 2`, `federated_capabilities_count: 0` | The peer row is written from `.well-known` **before** the manifest is fetched, so an advertised count survives while nothing is indexed. Either `manifest_url` is unreachable, or the crawl ended in `Invalid manifest signature` — the peer signs a different canonical than the hub verifies. A peer built against an older `oracle-core` signs the 4-field manifest canonical while the hub verifies 5 (`by_hub_hash`), and a peer whose manifest fails JSON-Schema validation is rejected the same way — GAIA published a measured float `p50_latency_ms` where the schema says `integer`. Rebuild the peer from current source. |
| `capabilities_count: 12` but `/manifest` returns `tools: []` and `/search` finds nothing | Those are `demo_seeder` rows with no `invoke_url` and no static pack: unfulfillable, correctly excluded from the manifest and search. Set `AIMARKET_SKIP_SEED=1` and clear them with `scripts/cleanup_hub_demo_catalogue.py /app/data/hub.db --apply --delete`. Since 2026-07-31 the live stats also publish `offerable_capabilities_count`, which is what the landing card shows. |
| `real_local_capabilities_count: 0` | No factory product is shipped. `import_factory_products` only imports products in a COMPLETED/DEPLOYED state that carry an `invoke_url` or a static pack; a `FAILED` product imports nothing, and the hub logs `skipped N capability(ies) with no invoke_url/static pack`. |
| A fresh deploy lost the whole catalogue and all invocation history | The hub keeps everything in the `modelmarket_hub_data` **volume** (`/app/data/hub.db`). Deploying with a different volume name, or with a bind mount, starts an empty database — the catalogue then rebuilds from the crawl, but invocations, channels and receipts do not come back. Check `docker inspect modelmarket-hub --format '{{range .Mounts}}{{.Source}}{{end}}'` before and after. |

## Related

- [`deploy/nginx/modelmarket.dev.conf`](../deploy/nginx/modelmarket.dev.conf) — nginx template (pre-certbot; live file is certbot-managed on server)
- [`aimarket-hub/README.md`](https://github.com/alexar76/aimarket-hub/blob/main/README.md) — hub operations
- [`docs/production-domain.md`](./production-domain.md) — magic-ai-factory.com TLS
