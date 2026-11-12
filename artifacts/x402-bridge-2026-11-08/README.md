# x402 bridge, honest map, onboarding funnel, knock verdicts, index-only admission, agent-factory kit — 2026-11-08

Owner: «да делай в лучшем виде используй пока доллар а там посмотрим можно сделать чтобы пополненный баланс сразу
давал лимит?», then the six onboarding items with «все делай на высочайшем уровне после того как сделаешь проверяй
по вулнетиксу и остальным, деплой на прод и тести на проде». All times are server clocks (UTC).

## What was built

| # | Item | Where |
|---|---|---|
| 1 | **x402 bridge.** A buyer paying modelmarket.dev in credits buys from an x402 seller; the hub pays the seller's 402 from its own wallet and charges the buyer what it paid, once the seller delivered. The limit is the wallet balance: a top-up raises it at once. | `aimarket_hub/x402_bridge.py`, `hub_routes/bridge.py`, federation path in `invoke_parts/federated_admission.py` / `federated_delivery.py`, migration 067, `credits.capture_hold(amount_mc=)` |
| 2 | **Knock verdict.** `POST /federation/announce` answers with the last assay verdict, its blockers and the funnel link. | `hub_routes/federation.py` |
| 3 | **Honest map.** A peer no crawl has reached for more than 7 days (`AIMARKET_PEER_SILENT_DAYS`) is `silent` on /hubs and in /federation/peers. Nobody is removed; it is live again on the next crawl. | `aimarket_hub/peer_liveness.py` |
| 4 | **Agent-factory kit.** One command next to a Multica self-host: hardened daemon, egress allowlist, WARDEN guard (npm checksums), the hub's MCP server, checks. | `multica/operator-kit/` (+ a pointer in the five manuals) |
| 5 | **Index-only admission.** A hub with nothing to probe passes when admitted hubs on two different sites list it as admitted under its advertised key. | `federation_assay.gather_index_witnesses` |
| 6 | **Onboarding funnel** on /hubs and `GET /federation/funnel`: knock → assay → admitted → first routed call → first paid call; totals count hubs that are not the operator's own. | `aimarket_hub/federation_funnel.py`, `database.peer_funnel_stats` |

Tests: `tests/test_x402_bridge.py` (46), `tests/test_federation_funnel.py` (10), `tests/test_index_witnesses.py` (12). The
whole hub suite: 3537 passed; the 21 failures and 17 errors are the same on the untouched base e716db661 in this venv
(no AWR/2 module, a macOS descriptor limit, two timing tests).

## How the bridge pays, and what keeps it safe

```mermaid
sequenceDiagram
  participant B as Buyer (credit key)
  participant H as modelmarket.dev
  participant S as x402 seller
  B->>H: invoke (listed price $0.001)
  H->>H: hold $0.001 on the buyer's credits
  H->>S: call, unpaid
  S-->>H: 402, offer: $0.001 USDC on Base to payTo
  H->>H: check the offer, reserve a ledger row under the lock
  H->>H: sign one EIP-3009 authorization, verify the signature
  H->>S: same call + PAYMENT-SIGNATURE / X-PAYMENT
  S-->>H: 200 + PAYMENT-RESPONSE (settled by its facilitator)
  H->>H: capture what was paid; the rest of the hold goes back
  H-->>B: result, paid_via: x402-bridge, tx hash
```

- Off unless `AIMARKET_X402_BRIDGE=1` and `AIMARKET_X402_BRIDGE_KEY_FILE` is readable by the hub and by nobody else
  (group/other bits refuse it; an unreadable file turns the bridge off, never the hub).
- Pays only `exact` USDC on Base, only to a payee the seller published before the 402 (its well-known
  `payment.accepts` or `payment_rails.seller_direct.payTo`, or the listing's signed `payout_address`), never more than
  the listed price that was held. The EIP-712 domain is USDC's own, whatever the offer's `extra` says.
- Caps: $0.05 a call, $0.50 per seller per UTC day, optional `AIMARKET_X402_BRIDGE_DAY_USD`, and the on-chain balance
  minus payments in flight (unsettled authorizations until they expire; settled ones for 120 s, in case another
  worker's balance read predates them). A seller that answers 402 to a payment still holds a signed authorization,
  so a refused payment keeps counting until it expires.
- Every payment is a row written before signing, under a lock row (`x402_bridge_state`) that queues concurrent
  purchases on SQLite and PostgreSQL alike; 40 concurrent reservations against $0.10 give exactly ten.
- **Free credit never pays a stranger.** A buyer's bridge purchases are bounded by what that buyer paid in (card or
  USDC top-ups, `topped_up_mc`); signup and operator grants keep buying this hub's own resources only. The operator's
  own accounts (ecosystem.json `self.accounts`, `AIMARKET_OPERATOR_ACCOUNTS`) and those named in
  `AIMARKET_X402_BRIDGE_GRANTED_ACCOUNTS` may spend granted credit: that is the operator's money.
- The buyer is charged only for a delivery: nothing when the bridge declines, the seller refuses, fails after taking
  the payment, answers for free, or the call breaks after paying (that is the bridge's loss, recorded, bounded by the
  caps). When the bridge declines, the buyer gets exactly what they got before it existed: the seller's own 402, which
  they can pay from their own wallet, with an `x402_bridge` note saying why the hub did not.
- One authorization per purchase, a fresh nonce, at most 300 s (never past the offer's `maxTimeoutSeconds`), no retries.
- `GET /ai-market/v2/x402-bridge` is public: wallet, balance, limits, today's spending, the last payments. No buyer
  identity, no key.
- `POST /ai-market/v2/observed/invoke` buys an observed seller's route (spec §2.7) the same way: credit key required,
  the invoke rate limit per account, only a route this hub serves now, only to the pinned or observed payee.

## Security review (Vulnetix classes and the rest)

| Class | Finding | Outcome |
|---|---|---|
| Open endpoints | `/x402-bridge` public, read-only; balance read cached 10 s. `/federation/funnel` public; it aggregated the whole invocation table per request. `/observed/invoke` needs a credit key. | Funnel cached 60 s; observed invoke rate-limited per account |
| Check-then-connect / SSRF | Paid resends use `safe_post`; observed routes `safe_request_capped`; witness reads the crawler's `_safe_get`; all pin the resolved address. Observed invoke only calls a URL this hub serves (an arbitrary URL is a 404 before any call). | No change needed |
| XFF trust | No new address-based decision. | — |
| Secrets in logs/errors | The key is never logged or returned; `keygen` prints the address only; refusal reasons carry no key material; the kit sends the hub key to curl on stdin, never in argv. | Kit fixed (`-H @-`) |
| Allowlist bypass | A 402 cannot choose the payee or the amount; the signing domain came from the offer's `extra`. | Domain fixed to USDC's |
| Overspend / double pay / replay | Caps under one lock; one nonce per purchase; refused authorizations count until expiry; settled ones for 120 s. | Two fixes (refused, settled lag) |
| Availability | An unreadable key file raised out of every credit-paid federated call. | Now turns the bridge off |
| Money policy | Grants could have become USDC in a stranger's wallet (the rule `test_federated_selling` pins for resale). | Paid-in bound |

Also found, not part of this change: in the live image some `/app/aimarket_hub` files belong to the hub user
(`hub_routes/invoke.py` was uid 10001), so a code-execution bug could rewrite the hub's own code. The files this
overlay touches are root-owned now; the rest is for the next image rebuild.

\* We thank Vulnetix for helping us improve our products.

## Production (modelmarket.dev, factory-vps)

The live hub runs 3.17.0 with overlays (label commit 0f438972e), not main: 9 of the 13 modules this change touches
differ from main. So the change was **ported onto the live files** (`kit/overlay/`, 17 files: 4 new, 13 live
modules patched; two hunks by hand), tested there (328 tests on the patched live tree), and built FROM the running
image `aicom-security:modelmarket-hub-public-20261108t064115z` (50dfcab2ac0e). The server runs `python -m aimarket_hub
serve` from `/app`, so it imports `/app/aimarket_hub`; the copy in site-packages is an older wheel. `kit/smoke.py`
imports `/app` the same way, inside the image with no network.

| Roll | Time | Image | Set | Previous container | DB backup |
|---|---|---|---|---|---|
| 1 | 09:17:29Z | `modelmarket-hub:xb-20261108` | `AIMARKET_X402_BRIDGE=1`, `AIMARKET_X402_BRIDGE_KEY_FILE=/app/data/x402-bridge.key` | `modelmarket-hub-security-prev-1794129440980181147` | `/app/data/hub-backup-pre-xb-20261108T091719Z.db` |
| 2 | 09:23:08Z | `:xb2-20261108` (funnel counts the operator's own domain) | `AIMARKET_X402_BRIDGE_GRANTED_ACCOUNTS=acct_3ef37d2abdef58ac` (the test account) | `…-1794129779612344791` | `…T092258Z.db` |
| 3 | 09:25:36Z | `:xb3-20261108` (seller_direct payee) | — | `…-1794129927729290632` | `…T092526Z.db` |

Each roll: the live files checked against `prod-before.sha256` first, then `kit/build.sh` (smoke + all 17 files in the
image equal the context), then `kit/roll.sh` (backup, `rollout_container.py`, THEMIS recreated, health of :9083 and
:9460). Rollback: `cd /root/hub-3160-main-20261021 && python3 rollout_container.py modelmarket-hub --image
aicom-security:modelmarket-hub-public-20261108t064115z --health http://127.0.0.1:9083/ai-market/v2/health --health
http://127.0.0.1:9460/health --set AIMARKET_X402_BRIDGE=` (the bridge settings are harmless on the old image).

**Bridge wallet:** `0xdE462c5F79665C6A758926BF0dBDF260B69A5E93` (Base). Key generated inside the hub's data volume by
the hub user (`/app/data/x402-bridge.key`, mode 600, in volume `modelmarket_hub_data`; not in the DB backups).
Funding it is the owner's step.

**nginx** (`/etc/nginx/sites-available/modelmarket.dev`, backup `/root/x402-bridge-20261108/modelmarket.dev.pre-xb-20261108`):
`location /ai-market/` got `proxy_buffer_size 16k; proxy_buffers 8 16k;`. agent-exec's 402 carries a 6.4 KB
`PAYMENT-REQUIRED` header; the default buffer turned the hub's passthrough of it into a 502 ("upstream sent too big
header"). Every buyer of agent-exec through modelmarket.dev hit that before today; `/x402/` and `/providers/esim/`
already had the same fix. Other hubs' live nginx not changed; the repo templates (`deploy/nginx/modelmarket.dev.conf`, `hub.modelmarket.dev.conf`, `hunt.modelmarket.dev.conf`, `aimarket-hub/nginx/nginx.conf`) carry the fix for the next deploy.

### Tested on production

- `GET /x402-bridge`: enabled, the wallet, balance $0.00, the limits.
- `/federation/peers`: `silent_after_days` 7; x402-gateway-production-1f21.up.railway.app `silent` (last crawl
  2026-10-31T17:24:24Z); 21 of 22 live.
- `/federation/funnel` and /hubs: hubs that are not the operator's: 6 came, 5 passed the assay, 5 admitted, 4 got a
  routed call, **0 got a paid call**; mach402.dev at the assay, agent-exec admitted with no routed call yet.
- A self-serve buyer key opened the normal way (`acct_3ef37d2abdef58ac`, $0.01 signup grant) bought agent-exec
  `execute` through modelmarket.dev: with the wallet empty, the answer was agent-exec's own 402 (offer and
  `PAYMENT-REQUIRED` header intact) with `x402_bridge.refusal: bridge_empty`; balance $0.01, held $0, spent $0.
- Not yet: a paid purchase. It needs the $1 in the wallet; then the same call should return `42` with
  `paid_via.tx_hash`, and the test account leaves `AIMARKET_X402_BRIDGE_GRANTED_ACCOUNTS`.

## Agent-factory kit

Tested 2026-11-08 against a stand-in Multica stack on Docker 29 (this Mac): the WARDEN package matched npm's sha1 and
sha512; every OpenCode session loaded the guard and the hub's MCP server from the mounted folder; example.com was
refused and modelmarket.dev answered through the proxy. Two checks could not pass there and said so: Docker Desktop
lets any container user write a bind-mounted folder, and the hub key was a dummy. The same run as root on a Linux
host (attested, a scratch folder and subnet) was refused by the session's permission classifier; nothing was left
there. A root run on a fresh Linux host is still to be done.

## Files

- `kit/`: Dockerfile, `overlay/` (the 17 files as deployed), `overlay.sha256`, `prod-before.sha256` (the live files
  they were ported onto), `smoke.py`, `build.sh`, `roll.sh`.
