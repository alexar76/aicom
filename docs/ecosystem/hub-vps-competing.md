# Competing Hub VPS — federation lab galaxy
#
# Languages: [EN](hub-vps-competing.md) · [RU](hub-vps-competing-ru.md) · [ES](hub-vps-competing-es.md) · [FR](hub-vps-competing-fr.md) · [ZH](hub-vps-competing-zh.md)
#
# Host: `hunt.modelmarket.dev` (Timeweb)
# DNS: `hunt.modelmarket.dev` → that IP · `hub.modelmarket.dev` (A record; TLS when DNS propagates) · `use.modelmarket.dev`
#
# This is the operator runbook for a **second Hub galaxy** that the primary federation
# (`https://modelmarket.dev`) discovers, plus Signal Hunt and the use-cases portal on the
# same box. It is **not** `./start.sh --everything` (that tier wants ≥16 GB RAM; this host
# has ~8 GB + swap).

## What “done” looks like

| Surface | Public URL | Role |
|---------|------------|------|
| Competing Lab Hub | `http://hunt.modelmarket.dev:9083` (peer) | UNI-only Hub (`AIFACTORY_CRYPTO_ENABLED=0`), federated peer of primary |
| Signal Hunt | `https://hunt.modelmarket.dev` | Game + own Hub behind host nginx (Caddy off) |
| Use-cases portal | `http(s)://use.modelmarket.dev` | Static portal on the lab edge |
| Alien Monitor | primary Monitor | Second **galaxy** far from origin (`competing_hub` / `signal_hunt` / `use_cases`) |

Federation **mesh wiring** on this box is not automatic — operators run the scripts
below so each known Hub sees the others. After a knock, product admission is a
different path: sandbox assay auto-admits a `pass` (see
[`join-the-federation.md`](../join-the-federation.md)). The scripts still `approve`
explicitly so a lab peer is trusted even without a free sandbox SKU.

## Scripts (use these — do not freestyle curl)

| Script | Purpose |
|--------|---------|
| [`scripts/register_hub_upstream.sh`](../../scripts/register_hub_upstream.sh) | One peer: `announce → approve(trusted) → crawl` |
| [`scripts/register_federation_mesh.sh`](../../scripts/register_federation_mesh.sh) | Full mesh: primary ↔ lab ↔ hunt |
| [`signal-hunt/scripts/register-upstream.sh`](https://github.com/alexar76/signal-hunt/blob/main/scripts/register-upstream.sh) | Same as hub upstream **plus** asserts Signal Hunt tools on the upstream manifest |
| [`scripts/announce-platon-oracles.sh`](../../scripts/announce-platon-oracles.sh) | Register Platon oracle family on a local Hub |
| [`scripts/verify_federation_urls.py`](../../scripts/verify_federation_urls.py) | URL / well-known sanity checks |

Tokens stay in the **process environment only** — never commit them, never write them into docs.

## 1. Host harden (once)

```bash
ssh -i ~/.ssh/id_ed25519_factory -o IdentitiesOnly=yes root@hunt.modelmarket.dev
# PasswordAuthentication no · AuthenticationMethods publickey
ufw allow OpenSSH; ufw allow 80/tcp; ufw allow 443/tcp; ufw allow 9083/tcp; ufw --force enable
systemctl enable --now fail2ban
```

## 2. Monorepo

```bash
# from operator laptop
rsync -az --exclude '.git' --exclude 'node_modules' --exclude '.venv' \
  --exclude 'data' --exclude '.env' \
  ./ root@hunt.modelmarket.dev:/opt/aicom/
```

## 3. Competing Lab Hub (public peer on `:9083`)

```bash
# container modelmarket-hub · AIMARKET_HUB_URL=http://hunt.modelmarket.dev:9083
# AIFACTORY_CRYPTO_ENABLED=0 · admin token → /opt/aicom/data/secrets/aimarket_admin_token.txt
curl -sf http://hunt.modelmarket.dev:9083/.well-known/ai-market.json | head
```

Nginx site `deploy/nginx/hub.modelmarket.dev.conf` serves `hub.modelmarket.dev` over HTTPS.
`curl https://hub.modelmarket.dev/.well-known/ai-market.json` answers 200 from this Hub, and
port 80 redirects to it.

That was not true until **2026-09-03**. DNS had resolved for weeks — `hunt.`, `hub.` and `use.`
all point at this host — but certbot had never been run for `hub.modelmarket.dev`, so the vhost
was port-80 only and TLS on the name fell through to the box's first `443` server block: a
visitor to `https://hub.modelmarket.dev` got a certificate issued for **emberlinedesk.com** and
a hostname-mismatch error. Issued with the same authenticator as its siblings:

```bash
certbot certonly --webroot -w /var/www/certbot -d hub.modelmarket.dev
```

Renewal reloads nginx through the host's global deploy hook
(`/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`), which every certificate on this box
already relies on.

The advertised base followed the certificate the same day: `AIMARKET_HUB_URL` was
`http://108.165.32.182:9083` and is now `https://hub.modelmarket.dev`, so this Hub's
`.well-known` gives `manifest_url` and `mcp_endpoint` over TLS on its own name instead of
plaintext on a raw address.

The container is a bare `docker run` (no compose project label), so the swap went through
`/root/switch_lab_hub_url.sh` on the host — the same machinery as `redeploy_lab_hub.sh`:
the environment is captured off the live container rather than composed from scratch, the
previous container is kept as `modelmarket-hub-preurl`, and anything that fails rolls back.
It asserts one thing beyond health: `signer_public_key` must be identical before and after,
because a hub that comes back under a new identity is a hub whose peers have to re-approve
it. It was unchanged (`553K9ALuHZx4pdGhhcMW9fPk33ke2sfH0zmRn+2fAXo=`), the signed manifest
still carries the same 104 capabilities, and the 112 re-exported federated ones survived.

Peers that recorded the old address keep working: `:9083` is still published on `0.0.0.0`,
and `alien-monitor/backend/canonical_peers.py` folds `http://108.165.32.182:9083`,
`http://hunt.modelmarket.dev:9083` and `https://hub.modelmarket.dev` onto the one
`competing_hub` node.

## 4. Signal Hunt (`hunt.modelmarket.dev`)

Host nginx owns `:80/:443`; compose override `signal-hunt/docker-compose.nginx-edge.yml` disables public Caddy and publishes Hub/Game on loopback only.

```bash
cd /opt/aicom/signal-hunt
# SIGNAL_HUNT_DOMAIN=hunt.modelmarket.dev · AIMARKET_HUB_URL=https://hunt.modelmarket.dev
docker compose -f docker-compose.yml -f docker-compose.nginx-edge.yml --env-file .env up -d
```

TLS: `certbot certonly --webroot -w /var/www/certbot -d hunt.modelmarket.dev` then nginx `443 ssl`.

## 5. Use-cases portal

Static root `/var/www/use.modelmarket.dev` ← `use-cases-portal/`. Site: `deploy/nginx/use.modelmarket.dev.conf`.

## 6. Federation mesh

### One peer onto primary

```bash
UPSTREAM_ADMIN_TOKEN='…from primary Hub…' \
  ./scripts/register_hub_upstream.sh \
  http://hunt.modelmarket.dev:9083 \
  https://modelmarket.dev

UPSTREAM_ADMIN_TOKEN='…' \
  ./signal-hunt/scripts/register-upstream.sh \
  https://hunt.modelmarket.dev \
  https://modelmarket.dev
```

### Full mesh (all see all)

```bash
PRIMARY_ADMIN_TOKEN='…' \
LAB_ADMIN_TOKEN='…' \
HUNT_ADMIN_TOKEN='…' \
  ./scripts/register_federation_mesh.sh
```

What each step does:

1. `POST /ai-market/v2/federation/announce` — peer row from `/.well-known/ai-market.json`
2. `POST /ai-market/v2/federation/peers/approve` — `{url, trusted: true}` (or the `/operator` desk)
3. `POST /ai-market/v2/federation/crawl` — index capabilities under `source_hub`

Verify:

```bash
curl -sf https://modelmarket.dev/ai-market/v2/federation/peers | jq .
curl -sf http://hunt.modelmarket.dev:9083/ai-market/v2/federation/peers | jq .
curl -sf https://hunt.modelmarket.dev/ai-market/v2/federation/peers | jq .
```

**Capability reality check:** a second Hub that only re-crawls the same Family/GAIA peers does **not** invent new tools. Hunt Hub seeds should be **origin providers** (Family, GAIA, ATLAS, MOMUS, SKOPOS) — not relay hubs. Metis/LOGOS stay out until they serve a signed `/.well-known/ai-market.json`. New SKUs also appear when the lab publishes **its own** capabilities (e.g. Signal Hunt’s `signal.*@v1`).

## 7. Alien Monitor — second galaxy

On the **primary** Monitor host set (optional overrides; defaults match this lab):

```bash
ALIEN_COMPETING_HUB_URL=http://hunt.modelmarket.dev:9083
ALIEN_SIGNAL_HUNT_URL=https://hunt.modelmarket.dev
ALIEN_USE_CASES_URL=https://use.modelmarket.dev
```

Layout: `alien-monitor/backend/ecosystem_layout.py` → `COMPETING_GALAXY_ANCHOR ≈ (30, 12, −20)` — far from hub `(0,0,0)` and the oracle ring. Nodes: `competing_hub`, `signal_hunt`, `use_cases` (LIVE via `build_topology()`, UNI via `seed_entities()`). Frontend nebula tint matches the orange competing cloud.

### AI assistant — auto awareness + focus (no hand edits)

Once a node is on the graph with `id` / `label` (and optionally `galaxy: competing`):

1. **Knowledge** — `build_live_context()` prioritizes `galaxy=*` nodes and emits a `galaxies` map into the system prompt.
2. **Focus** — `resolve_nav_actions()` matches the question against **live** node ids/labels (plus curated aliases). «покажи Competing Lab Hub» / «show Signal Hunt» emits `focus_node` without adding `NODE_ALIASES`.
3. Frontend already flies the camera on `focus_node`.

New federated spheres therefore become askable/focusable the tick they appear — no alias PR.

## 8. SKOPOS node agent

Live fleet entry: **`competing-lab`** (`address: hub.modelmarket.dev`, `transport: agent-push`) in
`/opt/skopos-test/deploy/servers.yaml` on the SKOPOS control plane (and in-repo
`metis/deploy/skopos-test/servers.yaml`).

Onboarded 2026-08-11:

```bash
# on skopos.modelmarket.dev
docker exec metis-skopos python skoposctl.py node-installer \
  --server competing-lab --base-url https://skopos.modelmarket.dev --out /tmp/install.sh
TICKET=$(docker exec metis-skopos python skoposctl.py node-ticket --server competing-lab)

# on hunt.modelmarket.dev — ticket on stdin, never in argv
printf '%s' "$TICKET" | bash install.sh
```

Agent units: `skopos-node.timer` + `skopos-node-privdump.timer`. Collects nginx
`access.log` plus docker logs for `modelmarket-hub`, `signal-hunt-hub-1`,
`signal-hunt-game-1`. Verify: `docker exec metis-skopos python skoposctl.py node-list`
should show `competing-lab` with a recent `last=` and growing `reports`.

See `skopos/docs/en/guide/collection-transports.md`.

## Related

- [`docs/deploy-competing-lab-host.md`](../deploy-competing-lab-host.md) — host notes
- [`docs/ecosystem-autodiscovery.md`](../ecosystem-autodiscovery.md) — how Monitor discovers peers
- [`signal-hunt/docs/GUIDE.md`](https://github.com/alexar76/signal-hunt/blob/main/docs/GUIDE.md) — Hunt operator guide
