# Run your own hub

<!-- sensor-operator-guide -->
> Own a weather station or air-quality sensor? [Sell your readings through your own Hub + GAIA](https://github.com/alexar76/aicom/blob/main/docs/sensor-operator.md).
<!-- /sensor-operator-guide -->

[English](operator-quickstart.md) · [Русский](operator-quickstart.ru.md) · [Español](operator-quickstart.es.md) · [Français](operator-quickstart.fr.md) · [中文](operator-quickstart.zh.md)

> Terminology follows the canonical [localization glossary](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md). Product names, protocol identifiers, URLs, CLI commands and environment variables are never translated.

You cloned it or installed it, and the fair question is what you get out of it. This page is
the whole path, in order: a hub on your machine in a minute, your own API on it, a public
address, a check that tells you in advance whether other hubs will admit you, and the knock.
No chain, no contract and no account with anyone is needed for any of it.

## 1. One minute, on your machine

```bash
pip install "aimarket-hub[pqc]"       # Python 3.11+. Or, with uv: uvx --from "aimarket-hub[pqc]" aimarket …
aimarket quickstart --name "My hub"
aimarket serve                        # → http://localhost:9083
```

`quickstart` does what a fresh hub cannot do on its own, and it is safe to run again:

1. **Saves the hub's settings** to `data/aimarket.env`, next to the database and the keys:
   the credits rail on, publisher trust scored by this hub (`AIMARKET_ORACLE_FAMILY_URL=off`),
   hybrid post-quantum signing, the name, and a generated **admin token**. Every `aimarket`
   command reads that file, so `serve` from a new terminal starts with the same settings. The
   file is `0600`: back it up with the keys. A variable set in the environment (systemd,
   `docker run -e`, `export`) always wins over it.
2. **Lists two capabilities that are really yours and really execute**, with no provider, model
   or network: `hub.ping@v1`, **free**, which answers with a receipt signed by your hub — this is
   what another hub's admission sandbox runs — and `hub.hello@v1`, priced, which a buyer pays for.
3. **Mints a buyer key** with a small balance and prints the curls of a complete sale.

Docker instead — from a clone of [this repository](https://github.com/alexar76/aimarket-hub):

```bash
docker compose run --rm hub quickstart --name "My hub"
docker compose up -d                  # → http://127.0.0.1:9083
```

Settings, keys and database live on the `hub_data` volume. Every command below works the same
way as `docker compose run --rm hub <command>`.

## 2. Your own API

```bash
aimarket add weather.now@v1 --url https://api.example.com/weather \
  --price 0.002 --pay-to 0xYourWallet --description "Current weather for a city"
```

The hub POSTs `{"input": …, "product_id": …, "capability_id": …}` to your URL and expects `200`
with a JSON object (or `{"result": …}`). Search, MCP, A2A, the x402 offer and the signed receipt
come from the hub. `--pay-to` is the wallet a buyer pays in USDC, seller-direct: the hub never
holds that money and takes nothing from it. Without `--pay-to` a priced listing can only be paid
from credit accounts on your own hub, which a buyer routed from another hub does not have.

`add` writes your own database, so there is no publisher stake to pay to yourself; strangers who
publish on your hub go through the gated door described [below](#letting-other-people-publish-on-your-hub).
In production mode (`AIFACTORY_PROD=1`) every provider response must be signed: pass
`--provider-pubkey`, and see [`examples/hello-capability/server.py`](../examples/hello-capability/server.py)
for the signature. Run `aimarket add --help` for every option.

## 3. A public address

Other hubs admit only an `https` address they can reach. Choose one:

- **A VPS and a domain.** Point the name at the host and put any TLS proxy in front of
  `127.0.0.1:9083`. With [Caddy](https://caddyserver.com/) the whole configuration is:

  ```
  hub.example.com {
      reverse_proxy 127.0.0.1:9083
  }
  ```

- **A platform with a persistent volume** — Railway, Render or Fly give you an `https` name
  without a domain of your own. Mount the volume at `/app/data`: keys, database and settings
  are your hub's identity, and a redeploy without them is a different hub. Ready files and steps:
  [run on a platform](run-on-a-platform.md).
- **The full production setup** — systemd, nginx, backups, monitoring:
  [production deployment](production-deployment.md).

Then tell the hub its address. It is inside every document the hub signs:

```bash
aimarket quickstart --url https://hub.example.com   # updates the saved settings; keeps the token and keys
```

## 4. Check before you knock

```bash
aimarket doctor
```

`doctor` runs the same admission assay other hubs run on you, against your public address,
and says what to fix for each failed check. On a local address it checks everything except
reachability and tells you the verdict you will get once the hub is public. The LLM veto is
not consulted here; a hub that uses one can still refuse.

## 5. The knock

```bash
curl -X POST https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  -d '{"hub_url": "https://hub.example.com", "hub_name": "My hub"}'
```

The answer carries `assay_url`, where you read the verdict. The receiving hub runs your free
`hub.ping@v1`; a signed receipt is the evidence. A `pass` on a hub with auto-admission puts your
own capabilities in its catalogue, its search and its routing, and puts your hub on its map —
modelmarket.dev admits automatically. Your hub reads the federation from the committed seeds
from the first start. The whole admission path: [join the federation](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.md).

## 6. What it earns, honestly

- **Your own API:** every sale is paid to your wallet, seller-direct. The hub keeps nothing.
- **Brokering:** `AIMARKET_ROUTING_FEE_BPS` (1% by default) when your hub routes a sale of
  another hub's capability on the credits rail. A sale the buyer pays the seller directly over
  x402 carries no fee.
- **Other people's sales:** a commission on the sellers who list on your hub — section 7.
- **Demand:** buyer traffic across the federation is still small. The live counters are public
  (`https://verify.modelmarket.dev/demand.json`); read them before you count on any of it.
  A hub costs a small VPS and pays off first as a storefront for your own API: MCP, x402, A2A
  and signed receipts with one command.

## 7. A marketplace of your own

A hub is also a storefront for other people's services — a niche catalogue under your name
(one field, one language, one region), with the federation's catalogue behind it from the
first day.

- **Your brand.** `AIMARKET_HUB_NAME` and `AIMARKET_HUB_URL` name every page; a deployment
  that is not the reference one shows no links to anyone else's site.
- **Sellers list themselves.** A credit account is a publisher identity: a seller mints a
  key, posts collateral from its balance and lists — see
  [letting other people publish](#letting-other-people-publish-on-your-hub). You set the
  collateral with `AIMARKET_SUPPLY_MIN_STAKE_USD`.
- **Your commission.** On a sale paid from a credit account, `AIMARKET_PUBLISHER_SHARE_BPS`
  (70 % by default) goes to the seller's balance and the rest is yours; routing a sale of
  another hub's capability adds `AIMARKET_ROUTING_FEE_BPS`. A seller who lists with its own
  wallet is paid seller-direct over x402 and you take nothing from that sale — that door
  stays theirs.
- **Buyers top up with USDC** to a wallet of yours ([credits top-up](credits-topup.md)), **or
  with a card** through your Stripe account ([card top-up](card-topup.md), off by default), or
  you credit them after any payment you take yourself.

What stays with you, not with the software:

- A balance is your customer's money in your ledger (`stats/live` → `outstanding_credit_usd`),
  and a seller's earned share is a balance too. Paying a seller out is a transfer you make:
  nothing in the hub sends value.
- Terms, refunds, taxes and whatever your jurisdiction asks of someone who holds prepaid
  balances or sells on behalf of others are yours to settle. The code takes no position on
  them.

## Post-quantum signatures from the first start

Post-quantum comes in two halves, and they do different jobs:

- **`[pqc]` lets the hub see its peers.** It installs the ML-DSA-65 verifier. Checking a
  post-quantum signature fails closed, so a hub without it never indexes a peer that signs
  hybrid — and the AIMarket hubs all do.
- **`AIMARKET_PQC=1` makes the hub sign hybrid** (quickstart saves it for a new hub). Its manifest, discovery document and receipts
  carry an ML-DSA-65 signature next to the Ed25519 one, and peers pin your post-quantum key the
  first time they see it.

The post-quantum key is a second file next to the classical one:
`<AIMARKET_SIGNING_KEY_PATH>_mldsa`, by default `data/hub_signing_key_mldsa`. Back up both
together and keep them on one volume. Lose the ML-DSA file and every peer that pinned it rejects
your hub until it re-pins (`POST /federation/peers/repin`). Background:
[post-quantum migration](https://github.com/alexar76/aicom/blob/main/docs/pqc-migration.md).

## How you get paid

There are two rails and you can run either or both.

| | Credits (`X-API-Key`) | Channels (`X-Payment-Channel`) |
|---|---|---|
| Setup | one env var | escrow contract you deploy on Base + 5 preflight settings |
| Smallest billable amount | $0.00001 | $0.01 (whole cents, rounded up) |
| Who holds the money | you, prepaid | you, prepaid (on-chain deposit) |
| Buyer needs | an HTTP client | a funded wallet and a typed-data signature |

**Credits** is the rail that works with `AIFACTORY_CRYPTO_ENABLED=0`, which is the default.
Turning it on makes a listed price mean money: a paid capability answers `402` with the
rails it accepts, and an invoke carrying a valid `X-API-Key` reserves the price before the
provider runs, captures it on success and hands it back on any failure.

```
POST /ai-market/v2/accounts                    # a buyer mints a key (rate-limited)
GET  /ai-market/v2/account                     # the buyer's balance
GET  /ai-market/v2/account/ledger              # every movement on their own money
POST /ai-market/v2/accounts/{id}/credit        # you top them up  (admin bearer)
POST /ai-market/v2/accounts/{id}/status        # you disable one  (admin bearer)
GET  /ai-market/v2/stats/live                  # summary.credits — earned vs. owed
```

Money enters only through `/credit`, and that route is yours alone. Whatever you use to
get paid — an invoice, a checkout, a stablecoin transfer you watched land — you call
`/credit` once you have the money. The hub does not pretend to have collected anything.

### What you are taking on

A prepaid balance is your customer's money sitting in your ledger. `stats/live` publishes
`outstanding_credit_usd` next to `credits_earned_usd` for exactly that reason: the first is
a liability, the second is revenue, and a hub that cannot tell them apart eventually spends
one thinking it is the other. Nothing in the hub can send value, so refunds are something
you do.

### Knobs

| Variable | Default | Meaning |
|---|---|---|
| `AIMARKET_CREDITS_ENABLED` | `0` | the rail itself |
| `AIMARKET_CREDITS_OPEN_SIGNUP` | `1` | may a stranger mint their own key |
| `AIMARKET_CREDITS_FREE_GRANT_USD` | `0.05` | starting balance for a self-minted key |
| `AIMARKET_CREDITS_SIGNUPS_PER_HOUR` | `5` | per-address cap on self-serve signup |
| `AIMARKET_ECOSYSTEM_FILE` | `ecosystem.json` next to the database | which accounts, servers and wallets are your own ecosystem: their calls are SELF, not external demand — see [traffic classes](traffic-classes.md) |
| `AIMARKET_OPERATOR_ACCOUNTS` | empty | older shortcut for `self.accounts` in that file (comma-separated account ids); merged into it |
| `AIMARKET_ROUTING_FEE_BPS` | `100` | your cut when you broker another hub's capability |
| `AIMARKET_PQC` | unset = auto | unset: a new hub signs hybrid (Ed25519 + ML-DSA-65), a hub that holds an ML-DSA key keeps signing with it, an Ed25519-only hub stays so; `1` / `0` force it |

## Letting other people publish on your hub

A credit account is an identity, not just a wallet, so it is also how somebody lists a
capability with you — no `.env` edit, no restart, no chain.

```bash
curl -X POST $HUB/ai-market/v2/accounts                      # they get a key
curl -X POST $HUB/ai-market/v2/accounts/<id>/credit \
     -H "Authorization: Bearer $ADMIN" -d '{"amount_usd": 30}'   # you take their money
curl -X POST $HUB/ai-market/v2/supply/stake \
     -H "X-API-Key: <key>" -d '{"amount_usd": 25}'               # they post collateral
curl -X POST $HUB/ai-market/v2/supply/register \
     -H "X-API-Key: <key>" -d @manifest.json                     # they list
```

The key speaks for exactly one publisher: its own account id. It cannot stake for, or
publish as, anybody else — which the shared publish token never could prevent.

The stake is a real debit against their balance, so it is money you are holding and can
slash. It is recorded as its own kind of collateral, distinct from the dev sentinel, and it
satisfies the production stake gate — the on-chain path still exists and still demands a
verified `tx_hash`, but a hub whose image does not ship the deposit verifier is no longer
forced to choose between "no collateral" and "an unusable gate".

Publisher trust: with `AIMARKET_ORACLE_FAMILY_URL=off` there is no oracle to consult, so
publishers get the documented neutral bootstrap and the trust gate does not apply. Point it
at a LUMEN instance you run if you want scoring.

## Paying your sellers

When a capability's publisher holds a credit account here, every completed sale splits
automatically: `AIMARKET_PUBLISHER_SHARE_BPS` (70% by default) is credited to them, the rest
is yours. That is the seller-earnings route the hub never had — the channel ledger cannot
send value, and the only obligations table refunds depositors rather than providers, so
before this a seller could list, be invoked, and still have to ask you to wire them a tenth
of a cent by hand.

`stats/live` reports the split honestly: `credits_earned_usd` is gross (what buyers spent),
`publisher_payouts_usd` is what went to sellers, and `operator_net_usd` is what you kept.
A failed call pays nobody — the payout runs on the same capture that charges the buyer.

## Brokering other hubs

When you route an invoke to a peer you did not sell for, the routing fee is **reserved
before the peer is asked to do anything**, on whichever rail the buyer is using. A caller
with no payment gets a `402` naming the fee; a peer that refuses costs the buyer nothing;
a peer that charges less than its published price is billed the smaller amount. If you do
not want to charge for brokering, set `AIMARKET_ROUTING_FEE_BPS=0` — that is the opt-out,
not a missing header.

An escrow-backed channel cannot authorize a routing fee (there is no signed authorization
for it), so that combination is refused rather than accrued as revenue you could never
collect. Buyers on that path should use a credit account.

### Reselling a peer that charges

Brokering only moves money if you can pay the other side. Hold a credit account at the peer
and name it:

```bash
export AIMARKET_PEER_API_KEYS="https://peer.example=aimk_your_key_there"
```

Now a routed call to that peer is a resale: your buyer is charged the catalogued price plus
your fee, you pay the peer out of your account there, and the fee is your margin. Without a
key the peer's `402` reaches a buyer who has no account there and cannot act on it, which is
why the live federation only ever contained peers that charge nothing.

Peer hubs are reached at their `/ai-market/v2/invoke`, not at their `mcp_endpoint` — that
endpoint speaks MCP JSON-RPC over SSE and answers a routed envelope with `Method not found`
inside a `text/event-stream` body. Hub-to-hub routing was impossible until that was fixed.

## Taking x402 payments

A catalogue sale is seller-direct. The 402 names the listing's `payout_address` and an
invoice `nonce`, and its JSON body alone carries a `payment_secret` with
`nonce = sha256(payment_secret)`. The buyer pays that wallet on-chain with an EIP-3009
`transferWithAuthorization` signed over the nonce, then retries with `X-Payment: <tx hash>`
(or `PAYMENT-SIGNATURE`), `X-Payment-Nonce` and `X-Payment-Secret`. The secret is what
shows the buyer is the one who paid: the transaction and its nonce are public once mined.
The hub verifies the transfer and never holds the money (`aimarket_hub/settle.py`): only
the transfer that authorization moved pays, and each authorization is its own claim, so
two in one transaction buy two calls. On a federated call, a payment travels next to your
peer key only when the hub settled it on that request, naming its own nonce and keeping the
secret. A hub with no key for that peer that settled nothing is a relay and passes the
buyer's payment headers through, the secret included. Every payment is bound (a plain
transfer to the seller is refused; `AIMARKET_SETTLE_REQUIRE_BINDING=0` is ignored), so buyer
tooling written against an earlier hub, which sent `X-Payment` and `X-Payment-Nonce` alone, is
refused until it sends the secret too; the MCP gateway takes it as `x_payment_secret`, and
the A2A bridge presents it itself. Migration `040` adds the invoice column that keeps it, and
`X-Payment-Secret` is in the CORS allow-list, so a browser client on an
`AIMARKET_CORS_ORIGINS` origin can redeem too. `AIMARKET_X402_ACCEPT=0` keeps discovery-only
mode.

Credits and payment channels remain prepaid conveniences. They are not how a
wallet publisher is paid.

## Letting strangers find you

Two observation doors are always available and both lead to quarantine rather than
immediate trust: an unauthenticated `POST /federation/announce`, and reciprocal discovery
when a peer crawls you and identifies itself. Either way the peer lands `pending` and
`trusted=false`. A sandbox assay then runs automatically; a `pass` indexes without an
Approve click. Fail and review stay pending for `/operator`. A separate preview table
holds what a pending peer claims to offer; those rows can never reach search or routing
because they are not in the `capabilities` table at all. See `docs/join-the-federation.md`.

## Standing on your own

Two defaults point at the reference deployment, and you probably want neither:

- **Publisher trust.** `AIMARKET_ORACLE_FAMILY_URL` defaults to another operator's LUMEN
  instance. Leave it and your ability to publish depends on their uptime — a capability
  published while it is unreachable is stored unscored and every invoke of it answers 502.
  `off` says this hub has no trust oracle: publishers get the documented neutral bootstrap
  and the gate does not apply. Point it at your own instance if you run one.
- **Federation seeds.** The shipped seed list is the reference hub's own satellites. They
  are a catalogue to browse, not supply you own — see `AIMARKET_SEED_LIST`.

## Naming

The code is Apache-2.0 (MIT elsewhere in the ecosystem) and you may run it commercially,
set your own fees and keep all of them; nothing routes a cut anywhere. There is no
trademark licence, so do not call your deployment "AIMarket" or imply endorsement.
"Implements the AIMarket Protocol" and "interoperates with <peer>" are accurate and fine.
Nobody may claim "certified" or "conformant" — there is no conformance suite yet.
