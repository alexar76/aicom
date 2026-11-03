# Production deployment of an independent AIMarket Hub

[English](production-deployment.md) · [Русский](production-deployment.ru.md) · [Español](production-deployment.es.md) · [Français](production-deployment.fr.md) · [中文](production-deployment.zh.md)

> Terminology follows the canonical [localization glossary](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md). Product names, protocol identifiers, URLs, CLI commands and environment variables are never translated.

This runbook is for an independent operator deploying a public Hub that can pass federation admission without a manual trust bypass. It covers a single Ubuntu host, nginx, TLS, an optional Alien Monitor, a paid signed capability and optional SKOPOS node-agent enrollment.

## 1. Target architecture and trust boundary

The smallest production layout is:

```text
Internet
  └─ nginx :80/:443
       ├─ /hub/      → AIMarket Hub on 127.0.0.1:9083
       ├─ /monitor/  → Alien Monitor on 127.0.0.1:9100 (optional)
       └─ provider   → capability backend on 127.0.0.1:<port>, not public
```

Use one unprivileged Unix account per service. Only nginx and SSH listen publicly. SQLite databases and Ed25519 keys live outside the Git checkout. The Hub's public origin is the security boundary: discovery, signed manifest and advertised `invoke` must use that same origin.

A dedicated hostname such as `hub.example.com` is simplest. A portal subpath such as `https://example.com/hub` also works, but requires every proxy rule in §7; missing one often produces a healthy API with broken UI assets, WebSocket or federation URLs.

## 2. Prerequisites

- Ubuntu 24.04 LTS or another supported systemd Linux.
- A public IPv4/IPv6 address and DNS `A`/`AAAA` records already pointing to the host.
- A non-expired domain under your control; do not request TLS before DNS resolves globally.
- SSH access with an Ed25519 key. Keep the first session open until a second key-only session succeeds.
- At least 2 CPU, 2 GB RAM and 10 GB free disk for Hub + Monitor.
- Outbound HTTPS for Git, ACME, federation crawl and SKOPOS enrollment.

Install the base packages:

```bash
sudo apt update
sudo apt install -y git nginx python3 python3-venv python3-pip \
  certbot python3-certbot-nginx sqlite3 ufw fail2ban unattended-upgrades
```

## 3. Pin source revisions

Never deploy a moving branch directly. Record and review a commit SHA, then check out exactly that revision:

```bash
sudo install -d -m 0755 /opt/aimarket/releases
sudo git clone https://github.com/alexar76/aimarket-hub.git \
  /opt/aimarket/releases/aimarket-hub-<sha>
sudo git -C /opt/aimarket/releases/aimarket-hub-<sha> checkout --detach <sha>
git -C /opt/aimarket/releases/aimarket-hub-<sha> rev-parse HEAD
```

Repeat for `alexar76/alien-monitor` and `alexar76/skopos` when those components are used. Save the SHAs in the deployment record. If a production hardening patch is applied on top, keep the patch and the pristine source outside the checkout and make `git status --short` explain only the intentional changes.

Before promotion:

```bash
python3 -m venv /opt/aimarket/venvs/hub
/opt/aimarket/venvs/hub/bin/pip install --upgrade pip
/opt/aimarket/venvs/hub/bin/pip install \
  "/opt/aimarket/releases/aimarket-hub-<sha>[pqc]"
```

The `[pqc]` extra installs the ML-DSA-65 signer and verifier. Leave it out and the hub fails closed on every hybrid signature, so it cannot federate with hubs that sign hybrid — the AIMarket hubs all do.

Run the repository test suite on the exact revision in CI or a build host. Do not install compilers and development dependencies permanently on the production host unless needed.

## 4. Users, directories and permissions

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin aimarket-hub
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin aimarket-provider
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin alien-monitor

sudo install -d -o aimarket-hub -g aimarket-hub -m 0750 /var/lib/aimarket/hub
sudo install -d -o aimarket-provider -g aimarket-provider -m 0750 /var/lib/aimarket/provider
sudo install -d -o root -g root -m 0700 /etc/aimarket
sudo install -d -o root -g root -m 0700 /var/backups/aimarket
```

Required permissions:

- Hub signing keys (`hub_signing_key` and, with post-quantum signing, `hub_signing_key_mldsa` beside it): `0600`, owned by `aimarket-hub`.
- Provider signing key: `0600`, owned by `aimarket-provider`.
- Environment files: `0600`, owned by root.
- SQLite directories: writable only by the service that owns them.
- Backups containing keys: `0600` inside a `0700` directory.

Never store a private key, admin token, enrollment ticket or database password in Git, a process argument, shell history or a public support log.

## 5. Hub configuration

Create `/etc/aimarket/hub.env`:

```dotenv
AIMARKET_HUB_NAME=Example Independent Hub
AIMARKET_HUB_URL=https://example.com/hub
AIMARKET_BIND_HOST=127.0.0.1
AIMARKET_DB_PATH=/var/lib/aimarket/hub/hub.db
AIMARKET_SIGNING_KEY_PATH=/var/lib/aimarket/hub/hub_signing_key
# Sign hybrid (Ed25519 + ML-DSA-65); needs the [pqc] extra (section 3). The ML-DSA key is written
# beside the classical one as <AIMARKET_SIGNING_KEY_PATH>_mldsa; peers pin it on first sight.
AIMARKET_PQC=1
AIFACTORY_PROD=1
# Trust forwarded client addresses only from nginx on this host; never use *.
AIMARKET_TRUSTED_PROXIES=127.0.0.1,::1
# The same resolved address decides SELF for the servers listed in ecosystem.json
# (next to the database): see docs/traffic-classes.md.
# Paid routes another service serves on this same origin (an x402 sidecar under /x402/)
# join /openapi.json, where x402 indexers (x402scan, AgentCash) look for them. Same origin as
# AIMARKET_HUB_URL only; hub routes are never overridden. Refreshed every 10 minutes.
# AIMARKET_OPENAPI_MERGE_URLS=https://hub.example.com/x402/openapi.json
# Stand-alone operators should not depend on another operator's reputation oracle.
AIMARKET_ORACLE_FAMILY_URL=off

AIMARKET_AUTO_CRAWL=1
AIMARKET_CRAWL_INTERVAL_S=3600
AIMARKET_CRAWL_REFRESH_MAX=64
AIMARKET_SEED_LIST=https://modelmarket.dev/.well-known/ai-market.json
# Pin the key read from, and verified against, the signed seed well-known document.
AIMARKET_SEED_PUBKEYS=https://modelmarket.dev/.well-known/ai-market.json=<seed-ed25519-public-key>

AIMARKET_FEDERATION_ASSAY=1
AIMARKET_FEDERATION_ASSAY_SANDBOX=1
AIMARKET_FEDERATION_AUTO_ADMIT=1

# A chainless production payment rail that can enforce a real 402.
AIMARKET_CREDITS_ENABLED=1
AIMARKET_CREDITS_OPEN_SIGNUP=1

# The signup grant, and the ceilings that make it safe to switch on.
# 0 = off, which is the production default. See "The signup grant" below.
AIMARKET_SIGNUP_GRANT_USD=0
AIMARKET_SIGNUP_GRANT_DAILY_USD=2.00
AIMARKET_SIGNUP_GRANT_TOTAL_USD=50.00

# Selling credit for a card through Stripe Checkout (docs/card-topup.md). Off by default; both
# secrets as docker secrets. The webhook endpoint is <hub>/ai-market/v2/stripe/webhook.
# AIMARKET_CARD_TOPUP_ENABLED=1
# STRIPE_SECRET_KEY_FILE=/run/secrets/stripe_secret_key
# STRIPE_WEBHOOK_SECRET_FILE=/run/secrets/stripe_webhook_secret
# Who owes the sales tax (docs/card-topup.md "Sales tax"): off | stripe_tax | managed_payments.
# AIMARKET_CARD_TOPUP_TAX=off

# Selling credit for USDC (5.3 below; docs/credits-topup.md). Off by default.
AIMARKET_TOPUP_ENABLED=1
# A wallet that receives top-ups AND NOTHING ELSE (its address only, never its key). Then the
# hub watches it and credits every deposit by itself; unset, top-ups go to AIMARKET_X402_PAY_TO
# and somebody has to present each one.
AIMARKET_TOPUP_PAY_TO=<dedicated top-up wallet>
AIMARKET_TOPUP_MIN_CONFIRMATIONS=2
# Where payments are read (comma-separated); public Base nodes when unset.
# AIMARKET_SETTLE_RPC_URL=https://mainnet.base.org,https://base-rpc.publicnode.com
# The deposit watcher — on whenever AIMARKET_TOPUP_PAY_TO is set; these are the defaults.
# AIMARKET_DEPOSIT_WATCH=1
# AIMARKET_DEPOSIT_WATCH_INTERVAL_S=60
# AIMARKET_DEPOSIT_WATCH_CHUNK_BLOCKS=500
# AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS=1800


### 5.1 The signup grant

A self-minted key normally starts at zero, so an open signup gives away nothing but a
row. `AIMARKET_SIGNUP_GRANT_USD` changes that: it hands every new account a small real
balance, which is worth real invoke. That is the point — at a few tenths of a cent per
call, five cents lets somebody run the thing before they own a wallet — and it is also
the risk, because an open signup hands that value to anyone who asks.

`AIMARKET_SIGNUP_GRANT_USD` is its own switch. It falls back to the older
`AIMARKET_CREDITS_FREE_GRANT_USD` so an existing deployment does not change behaviour,
but new configuration should use the new name: a grant is a growth experiment and has to
be killable in one edit without touching the rest of the rail.

#### Why a budget and not a bot filter

The hub cannot tell a person from a bot, and on this rail it should not try.

* Address heuristics lose. A residential-proxy pool hands out a fresh IP per request,
  and device fingerprints are forgeable; measured fleets have beaten every user-agent
  rule we wrote.
* The intended buyer is frequently **not** a person. Capabilities are sold to agents. A
  CAPTCHA would block the customer and pass the proxy fleet.

So the grant is bounded rather than guarded. `AIMARKET_SIGNUP_GRANT_DAILY_USD` caps
grants minted in a rolling 24 hours across every signup, and
`AIMARKET_SIGNUP_GRANT_TOTAL_USD` caps them for the lifetime of the ledger (`0` leaves
only the daily cap). A filter is something an attacker can pay to get around; a budget
simply runs out, so the worst case is a number the operator chose. **A daily budget of
`0` means no grants at all, never "unlimited".**

When the budget is spent the account is still created — at zero balance, with a
`grant_note` in the response saying why. A real buyer can still top up and work; only
the free part is gone until the window rolls.

#### What the budget counts

Three different movements land in `credit_ledger` as `kind='grant'`, because the money
moves the same way in each. Only the note tells them apart, and the budget counts just
the first:

| Note | What it is | Counts against the budget |
| --- | --- | --- |
| `signup grant` | a self-minted key's starting balance | yes |
| `operator opening balance` | an account the operator opened with a starting balance | no |
| anything else | an operator top-up after real money settled | no |

Counting by `kind` alone would let one settled $25 invoice spend a whole day of signup
grants — and silently, since a refused grant still returns a working account.

#### What the grant can still be spent on

A granted balance is ordinary credit: it can pay for this hub's own capabilities **and
for routed peer calls**. The second case is the only one where a farmed grant costs real
money to a third party rather than local CPU. Keeping grant money off routed calls needs
credit provenance in the invoke path, which is not implemented; until it is, the daily
budget is what bounds that exposure. Set it accordingly.

#### Operating it

* Turn it on: `AIMARKET_SIGNUP_GRANT_USD=0.05`, restart, confirm
  `payment_rails.credits.free_grant_usd` in `/.well-known/ai-market.json`.
* Turn it off: set it to `0`. The advertised value follows immediately, and existing
  granted balances are left alone — they are already the customers' money.
* Watch it: `credits.granted_usd` in `/ai-market/v2/stats/live` is the total handed out;
  compare it with `credits_earned_usd` to see whether the grant converts. If it does
  not, the switch is one edit.

### 5.2 Privileged fields are refused, not ignored

`POST /ai-market/v2/accounts` needs no authentication when open signup is on, but
`grant_usd` on that request is operator-only. A non-admin caller that sends it gets
`403`, rather than an account with the advertised grant instead of the balance it asked
for.

This is deliberate and it is worth stating why. Silently overriding a privileged field
is how a service comes to believe it is the operator: one held the wrong token, asked
for `grant_usd: 0`, was handed the signup grant, and everything looked healthy —
capability registration works with a lesser credential, and so does opening an account.
It found out it was not admin at the first call that moved money, which is the one call
that must not be the first to find out. A `403` at the first request instead of a
surprise at the first payment is the whole difference.

# Generate long random values; examples are deliberately omitted.
AIMARKET_ADMIN_TOKEN=<secret>
AIMARKET_PUBLISHER_TOKENS=<publisher-id>:<secret>
AIMARKET_ECOSYSTEM_LABELS=publisher-id=Display Name
AIMARKET_CORS_ORIGINS=https://example.com
```

Important rules:

1. `AIMARKET_HUB_URL` is the externally reachable URL, including `/hub` when a subpath is used. Never set it to `localhost` in production.
2. The Hub creates its Ed25519 key on first start. Back it up immediately. Replacing it changes federation identity and looks like a key takeover to pinned peers. With `AIMARKET_PQC=1` it also creates the ML-DSA-65 key `<key path>_mldsa`: back up both and keep them on one volume.
3. A seed key is public, but it is a trust decision. Obtain it from the signed well-known document over verified TLS and record the comparison.
4. An unset admin token must fail closed. Do not expose operator routes merely to simplify onboarding.
5. With SQLite, stop the Hub or use the SQLite backup API before copying files. PostgreSQL is preferable for multi-process/high-write installations.
6. Give every provider its own subject-scoped publisher token. Never reuse the Hub admin token as a provider credential. When several providers belong to this Hub, set `AIMARKET_ECOSYSTEM_LABELS=publisher-id=Display Name,...`; the Hub then publishes their relationship in the signed `ecosystem.nodes` extension without pretending that they are independent federation peers.
7. A crawler must refresh a bounded set of already trusted active peers on every cycle, even when they are no longer reachable from the current seed graph. Size `AIMARKET_CRAWL_REFRESH_MAX` for that roster; otherwise a valid 30-capability peer can remain indexed with an old one-capability manifest indefinitely.

### 5.3 Selling credit for USDC: a wallet of its own

With `AIMARKET_TOPUP_ENABLED=1` any agent buys credit with USDC on Base by itself
([credits-topup.md](credits-topup.md)). Give the door its own wallet, and nobody has to watch the
chain or credit anything by hand:

1. **Create a wallet that will receive top-ups and nothing else.** The hub needs only its address,
   never its key: nothing the hub does spends from it. Keep the key wherever the operator keeps
   treasury keys.
2. **Set the variables** above (`AIMARKET_CREDITS_ENABLED=1`, `AIMARKET_TOPUP_ENABLED=1`,
   `AIMARKET_TOPUP_PAY_TO=<address>`). Under systemd they go in the env file or a drop-in
   (`Environment=AIMARKET_TOPUP_PAY_TO=0x…`); under Docker Compose the container sees only what the
   compose file forwards, so add `AIMARKET_TOPUP_PAY_TO: ${TOPUP_PAY_TO:-}` to the hub's
   `environment:` and `TOPUP_PAY_TO=0x…` to `.env`.
3. **Back up the database and restart the hub.** Migration `050_deposit_watch` adds
   `payer_wallets`, `deposit_watch_cursor` and `hub_deposits`.
4. **Check it**: `pay_to` is the new wallet and `deposit_watch.enabled` is `true` (off, `reason`
   says what is missing). Link the wallet of every company that will pay by plain transfer, once.
   Read what arrived from nobody known:

```bash
curl -s "$AIMARKET_HUB_URL/.well-known/ai-market.json" | jq '.payment_rails.credits.topup | {pay_to, deposit_watch}'
curl -s "$AIMARKET_HUB_URL/ai-market/v2/accounts/$ACCOUNT_ID/payer-wallets" -H "Authorization: Bearer $AIMARKET_ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d '{"address": "0x…"}'
curl -s "$AIMARKET_HUB_URL/ai-market/v2/admin/deposits" -H "Authorization: Bearer $AIMARKET_ADMIN_TOKEN"
```

5. **Page on it**: add the hub to the ecosystem alerter's `AICOM_ALERT_DEPOSIT_HUBS` (only hubs
   inside the alerter's `AICOM_ALERT_SCOPE` are probed)
   (`deposit_watch_on:<hub>` — the hub should watch and does not; `deposits_unattributed:<hub>` —
   money arrived from a wallet nobody linked).

The first scan starts `AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS` (1800, about an hour on Base) behind
the head, one interval after the hub starts, so a transfer made shortly before the switch is still
found; an older one is credited by hand with its `tx_hash`. A new wallet gets a new cursor, and the
old wallet is no longer read.

Never point `AIMARKET_TOPUP_PAY_TO` at a wallet that receives other money: every incoming transfer
would be read as a top-up. The hub refuses its own x402 and payment-recipient wallets
(`AIMARKET_X402_PAY_TO`, `AIMARKET_PAYMENT_RECIPIENT`; `reason` in the well-known); it cannot know
what else another wallet receives, and it cannot know that another hub uses the same one.

## 6. systemd service

Create `/etc/systemd/system/aimarket-hub.service`:

```ini
[Unit]
Description=Independent AIMarket Hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=aimarket-hub
Group=aimarket-hub
WorkingDirectory=/opt/aimarket/releases/aimarket-hub-<sha>
EnvironmentFile=/etc/aimarket/hub.env
ExecStart=/opt/aimarket/venvs/hub/bin/python -m aimarket_hub serve
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
LockPersonality=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/lib/aimarket/hub
UMask=0027
MemoryMax=1G
TasksMax=256

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aimarket-hub
sudo systemctl status aimarket-hub --no-pager
```

Bind the application to loopback when the selected release supports a bind-host setting. If it listens on `0.0.0.0:9083`, UFW must still deny that port and nginx must remain the only public path.

## 7. nginx, subpaths and TLS

The following is the essential subpath shape; adapt certificate paths and rate-limit zones to your distribution:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name example.com;
    location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name example.com;

    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_tickets off;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    client_max_body_size 1m;

    location = /hub { return 301 /hub/; }
    location ^~ /hub/ {
        proxy_pass http://127.0.0.1:9083/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }

    # Current UI pages use several root-relative routes. Keep these on the Hub
    # or use a dedicated Hub hostname where no prefix translation is needed.
    location ~ ^/(ai-market|api|mcp|developers|examples|widget|plugins|operator|studio)(/|$) {
        proxy_pass http://127.0.0.1:9083;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
    location = /hub-ui-i18n.json { proxy_pass http://127.0.0.1:9083/hub-ui-i18n.json; }
    location = /cap-descriptions-i18n.json { proxy_pass http://127.0.0.1:9083/cap-descriptions-i18n.json; }
}
```

For Alien Monitor, build the frontend with `VITE_BASE_PATH=/monitor/`, proxy `/monitor/` to its loopback HTTP port and give `/monitor/ws` explicit WebSocket `Upgrade`/`Connection` headers with a long read timeout. A build made for `/` can return HTTP 200 while its JavaScript and CSS fail under a subpath.

If a provider also has a human UI, proxy only that UI publicly. Reject its raw invoke and execution routes at nginx (or require mTLS) so callers cannot bypass the Hub's payment, policy and receipt checks. Confirm the public provider URL returns `403`, while a paid call through `/hub/ai-market/v2/invoke` succeeds.

When the domain root hosts a separate portal, run it as another unprivileged loopback service and proxy it only as nginx's final fallback. Put portal API prefixes such as `/api/v1/` before the Hub's broad root-relative compatibility rule; otherwise the portal may render while its API silently goes to the Hub. Keep `/hub/`, `/monitor/` and provider paths explicit, and do not redirect `/` to `/hub/` when the portal is the intended entry point.

Issue and test the certificate:

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d example.com
sudo certbot renew --dry-run
systemctl is-enabled certbot.timer
```

Do not enable HSTS until HTTPS works correctly for every covered subdomain.

## 8. Publish a real capability without bypassing the payment gate

For the first local smoke capability, stop the Hub and run the shipped idempotent quickstart under the Hub account. It creates an executable static pack without a model or external provider; replace it with your own backend before presenting it as a product:

```bash
sudo systemctl stop aimarket-hub
sudo -u aimarket-hub env \
  AIMARKET_DB_PATH=/var/lib/aimarket/hub/hub.db \
  AIMARKET_HUB_URL=https://example.com/hub \
  AIMARKET_CREDITS_ENABLED=1 \
  /opt/aimarket/venvs/hub/bin/python -m aimarket_hub quickstart \
  --price 0.01 --grant 0
sudo systemctl start aimarket-hub
```

The generated buyer key is a secret and is printed once. With a zero grant it carries no balance; keep it in a password manager or revoke it. For a real provider, follow [Running this hub for yourself](operator-quickstart.md), register only a backend you control and preserve its provider signing key.

A production capability has two surfaces:

- an internal provider backend that performs work and signs the result;
- the public Hub gateway that validates safety, payment, routing and receipts.

The signed manifest must advertise the Hub gateway, for example:

```text
https://example.com/hub/ai-market/v2/invoke
```

It must not advertise a raw `/provider/invoke` URL. Restrict the provider route to loopback, a mutually authenticated connection or the host's own address. A release that exposes the provider URL in the manifest needs an upgrade or a reviewed backport before production.

For a paid-only capability, an unauthenticated request — including one carrying `X-AIMarket-Sandbox-Visitor` — must return `402`, name a usable payment rail and quote exactly the price in the signed catalogue. Alternatively, a genuinely free capability may return real work with a signed receipt. A brochure-only endpoint is not evidence.

Minimum conformance checks:

- `/hub/.well-known/ai-market.json` passes the shipped schema.
- `manifest_url` is public and same-origin.
- well-known and manifest signatures verify under the advertised Ed25519 key.
- manifest `generated_at` is fresh.
- the five-field manifest canonical covers capability count, timestamp, protocol version, `tools_hash` and `by_hub_hash`.
- every numeric schema field is a number, not `null`.
- advertised `invoke_url` is same-origin and enters the Hub gateway.
- the `402` price equals `price_per_call_usd`.
- a successful provider response carries a verifiable provider signature.

## 9. Federation admission

After all local checks pass, announce through the public protocol:

```bash
curl -fsS -X POST https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  --data '{
    "hub_url":"https://example.com/hub",
    "hub_name":"Example Independent Hub",
    "well_known_url":"https://example.com/hub/.well-known/ai-market.json"
  }'
```

Then read the public assay status:

```bash
curl -fsS 'https://modelmarket.dev/ai-market/v2/federation/assay?url=https%3A%2F%2Fexample.com%2Fhub'
```

Expected lifecycle:

```text
announce or inbound crawl → pending/quarantine → sandbox assay → pass → trusted/indexed
```

Do not use the operator panel, admin endpoint or a hand-edited peer table to bypass trust. A known pending peer may wait until the receiver's next crawl cycle; an hourly interval is normal. If the assay returns `review` or `fail`, fix the live evidence and wait for the documented re-run path. Preserve the dossier: it explains the exact failed check.

After admission, verify the peer roster, federated search result and Alien Monitor by name and `capability_id`, not only by HTTP 200.

## 10. Host security

Configure the firewall before exposing the service:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw limit 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Enable Fail2ban jails for `sshd`, `nginx-http-auth` and `nginx-botsearch`, and enable unattended security upgrades. Review bans and upgrade logs; installation alone is not monitoring.

SSH hardening order is load-bearing:

1. Install the operator's public key.
2. Open a second session with `BatchMode=yes` and the intended key.
3. Inspect `sshd -T`; earlier cloud-init drop-ins may override a later-looking file.
4. Set `PasswordAuthentication no`, `KbdInteractiveAuthentication no`, and `PermitRootLogin prohibit-password` (or disable root entirely and use sudo).
5. Reload SSH, keep the first session open, and test a third key-only login.

Never close the only working session before the independent test succeeds.

## 11. Backups and restore

Back up at least:

- Hub SQLite database and any separate channel/provenance databases;
- Hub and provider private keys: the Ed25519 key and, with `AIMARKET_PQC=1`, its ML-DSA companion `<key path>_mldsa`;
- root-owned environment files and systemd drop-ins;
- nginx site configuration;
- pinned SHAs and intentional patch files.

Use `sqlite3 /path/hub.db '.backup /staging/hub.db'` or stop the service before copying. Create a root-only compressed archive, retain several generations and move an encrypted copy off-host. A backup that has never been restored is unverified.

Restore procedure:

1. Stop Hub and provider services.
2. Restore databases and keys with their original ownership/modes.
3. Restore configuration, run `systemctl daemon-reload` and `nginx -t`.
4. Start services and verify that neither public key changed: `signature.public_key` and `signature.pq_public_key` in `/.well-known/ai-market.json`.
5. Re-run schema, signature, `402`, search and federation checks.

## 12. Alien Monitor and SKOPOS

Run Alien Monitor as a separate unprivileged service in LIVE mode. Point it to the local Hub URL, proxy its HTTP API and WebSocket separately, and verify that the tick counter advances after a reboot. Empty financial metrics may simply mean no traffic; a frozen tick or failed health endpoint is an outage.

Treat each independent Hub as a separate star system. Deduplicate objects by stable identity and normalized URL, enforce a minimum centre-to-centre distance between peer Hubs, and place `ecosystem.nodes` around their owning Hub. A Hub and an application may legitimately share an origin but must retain distinct identities. Older external Monitors may show the Hub before they understand the signed `ecosystem` extension; do not fake owned providers as federation peers merely to influence a third-party visualization.

Reserve the per-Hub child budget for signed `ecosystem.nodes` before drawing federated peer links, or a large peer roster can hide the Hub's own providers. The AI assistant must resolve names from the current live snapshot — including localized/transliterated queries — before it falls back to static help text, so newly deployed modules remain discoverable even when no external LLM key is configured.

SKOPOS uses a constrained push-only node agent. Enrollment must use an official single-use ticket:

1. Mint the ticket on the SKOPOS control plane for the exact server entry.
2. Run the generated installer as root on the node.
3. Enter the ticket through hidden stdin. Never pass it in argv, a URL, shell history or chat.
4. Confirm the ticket was burned, the credential file is root/agent-readable only, and the timers report successfully.

The node cannot mint its own ticket: it must come from the SKOPOS control plane. If no ticket exists, leave the prepared installer stopped and report enrollment as pending. Never guess a ticket, copy one from another node or modify a remote control-plane database.

Do not manually create a credential in the SKOPOS database and do not grant the agent the Docker group or unrestricted sudo.

## 13. Final acceptance checklist

```bash
# Services and reboot recovery
systemctl is-active aimarket-hub nginx fail2ban ufw unattended-upgrades
systemctl --failed

# TLS and discovery
curl -fsS https://example.com/hub/.well-known/ai-market.json
curl -fsS https://example.com/hub/ai-market/v2/manifest

# Paid door: must be 402 and quote the catalogue price
curl -sS -o /tmp/invoke.json -w '%{http_code}\n' \
  -H 'Content-Type: application/json' \
  --data '{"product_id":"example","capability_id":"example.echo@v1","input":{}}' \
  https://example.com/hub/ai-market/v2/invoke

# Firewall and SSH effective settings
ufw status verbose
sshd -T | egrep '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication) '
```

Finally reboot the host and repeat the checks from an external network. Acceptance requires:

- all services return automatically;
- only SSH, HTTP and HTTPS are public;
- TLS renewal dry-run succeeds;
- signatures still verify and the signer key is unchanged;
- the public provider backend cannot be bypassed;
- the Hub remains searchable on the federation;
- Alien Monitor reconnects and its LIVE tick advances;
- the newest backup exists and its restore procedure is documented.

## 14. Upgrades and rollback

1. Build a new immutable release directory and virtual environment; never `git pull` inside the live release.
2. Read migrations, especially SQLite channel/provenance path changes.
3. Back up databases and signing keys.
4. Run tests and the local federation assay against the candidate.
5. Change only the systemd `WorkingDirectory`/`ExecStart` target, restart, then run acceptance checks.
6. Roll back the code if needed, but do not roll back a database across an incompatible migration without the matching backup.

The signing identity (the Ed25519 key and, with post-quantum signing, its `_mldsa` companion) and the payment ledger are persistent state, not release artifacts. Losing or silently replacing either is not a routine redeploy.

## 15. Moving the hub to another host

The container and its data volume are the easy part. What breaks a move is what runs **next to**
the hub on the host: none of it is in the image, a healthy `/health` says nothing about it, and the
old host keeps running its copy against a hub that is no longer there. On 2026-10-01 the
modelmarket.dev hub moved hosts and the escrow signer tunnel and the settlement sweep stayed
behind: for two days no escrow debit reached the chain, and nothing paged, because the old sweep
kept publishing "ok, nothing to submit".

**Move together with the container**

| What | Where it lives | On the new host |
|---|---|---|
| Hub data (`hub.db`, channel ledger, escrow authorization store, deposit claims) | the data volume | copy from a fresh backup taken with the hub stopped (§11) |
| Signing identity | data volume / key path: `hub_signing_key` and `hub_signing_key_mldsa` | both keys, never new ones (§14): peers that pinned the post-quantum key reject a new one until each re-pins it |
| Escrow signer tunnel | `escrow-signer-tunnel.service` (SSH `-L` to the signer host) | new SSH key on the new host; on the signer host add it as `restrict,port-forwarding,permitopen="127.0.0.1:9500",command="/bin/false"`; pin the signer's host key by comparing its fingerprint with the old host's `known_hosts`; bind `127.0.0.1:9500` **and** the gateway of the hub container's Docker network; firewall: allow that network's subnet to the gateway on 9500, nothing else |
| Settlement sweep | `aicom-settlement-sweep.{service,timer}` + `/usr/local/lib/aicom-settlement/escrow_settlement_sweep.py` | install, point `--publish` at the directory the new host serves `verify.<domain>` from, run it once |
| Payment canary | `aicom-payment-canary.{service,timer}` (`scripts/payment_canary.py`) | install, publish into the same `verify.<domain>` directory; the alerter pages when `status.json` goes stale |
| Auditor (THEMIS) | joins the hub's network namespace | recreate it with `--network container:<hub>` after the hub (it is orphaned otherwise) |
| Verifier key for Pay-on-Verified | `/root/.metis-verify-key` (0600) → `AIMARKET_VERIFY_METIS_*` | copy server-to-server, never through a terminal |
| First-party providers | systemd units (`weather-witness`, `pov-demo`) | install, then re-check their nginx locations |
| nginx locations, TLS, renewal hooks | `/etc/nginx`, `/etc/letsencrypt` | re-check every `location` that proxies to a host port |

**One script does the first three rows and checks them:** `scripts/hub_host_companions.sh --install` on the new host (set `AICOM_SIGNER_SSH_HOST` when the hub signs through the external signer), `--verify` to check (it fails unless the units run, the hub container reaches the signer and both reports are fresh), `--disable` on the old host. `scripts/deploy_hub_rebuild.sh` runs `--verify` at the end of every deploy and exits 3 when anything is missing.

**Then switch the old host off** — every unit above, explicitly (`systemctl disable --now`). A sweep
left running there reads a store nobody writes to any more and reports success forever.

**Prove the money path before calling the move done**

```bash
# the hub container reaches the signer through the tunnel (prints the signer address)
docker exec <hub> python -c "import httpx;print(httpx.get('http://<gateway>:9500/health').text[:120])"
# the sweep ran HERE: checked_at is minutes old, errors is empty
curl -s https://verify.<domain>/settlement.json | jq '{checked_at, ok, errors}'
# nothing listens on the old host any more
ssh <old-host> 'systemctl is-active escrow-signer-tunnel aicom-settlement-sweep.timer'   # inactive, inactive
# Pay-on-Verified is still wired: enabled, your verifier, escrow_hub declared
curl -s https://<domain>/.well-known/ai-market.json | jq '.pay_on_verified.enabled, .contracts.entries'
```

The UNI bubble has its own list (its private chain, firewall, buyer settings):
[docs/uni-realm-runbook.md](https://github.com/alexar76/aicom/blob/main/docs/uni-realm-runbook.md).
