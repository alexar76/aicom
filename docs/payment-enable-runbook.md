# Runbook — turning on real payments at `modelmarket.dev`

Closes the gap behind `payment_configured: false` on the public hub. §1–§4 are
operator-only: they need the server's `.env` and a wallet the repo must never see.
§5 is the verification anyone can run afterwards.

Related: [`docs/known-issues.md`](known-issues.md) KI-11, [`contracts/DEPLOY.md`](../contracts/DEPLOY.md),
[`security/prod_startup_guard.py`](../security/prod_startup_guard.py).

## ✅ Re-applied on modelmarket.dev, 2026-08-04

Payment env had been unset on the host; re-enabled via `deploy/hub-payment.env` (loaded
after shared `.env` by `scripts/deploy_hub.sh`) and image
`modelmarket-hub:prod-20260804-payments` (hub **3.2.1**). Also set
`AIMARKET_SELLS_FOR=https://oracles.modelmarket.dev/family` so federated oracles actually
402 without a channel. Real-money smoke (operator self-test): [`onchain-journal.md`](onchain-journal.md) §3k.

```
payment_configured   true      payment_testnet  false      channels.demo_mode  false
image                modelmarket-hub:prod-20260804-payments
federated_caps       48
```

## ✅ Applied on modelmarket.dev, 2026-07-27

Everything below was executed. Live state then:

```
payment_configured   true      payment_testnet  false      channels.demo_mode  false
image                modelmarket-hub:prod-20260727-escrow
rollback image       modelmarket-hub:prod-20260726-a42aa97adc
.env backup          /root/claudecode/aicom/.env.bak-20260727-204713
```

Both refusal paths verified against the live endpoint:

```
tx_hash 0xdeadbeef…   → "on-chain verification unavailable — refusing to credit channel …"
escrow_channel_id 0x11…→ "no escrow channel 0x1111… at 0x0606983c… — the depositor must
                          call openChannel before the hub can credit it"
```

Deploy method: the code was rsynced to `/root/aicom-hub-build` and the image built there.
`/root/claudecode/aicom` was deliberately left untouched — it sits on `a42aa97a` with six
local modifications to `alien-monitor/` and `apps/pulse-terminal/`, and two incoming
commits touch those same files, so a pull would have clobbered hand-fixes.

`AIFACTORY_PROD=1` is passed **only as a `-e` flag to the hub container**, not written to
`.env`: four other services share that file, and `aicom-app` does ship the `security`
package, so the full guard would refuse its next start over SQLite/LLM-key findings that
have nothing to do with payments.

Escrow-funded channels are enabled read-only — `AIMARKET_ESCROW_BRIDGE_ENABLED=1`,
`AIMARKET_ESCROW_NETWORK=base`, `AIMARKET_ESCROW_CONTRACT` and
`AIMARKET_ESCROW_HUB_ADDRESS` set, strategy left at `plan` with `may_broadcast: false`.
The hub verifies funding against the contract but never broadcasts; debit/settle stay
manual, as in [`onchain-journal.md`](onchain-journal.md) §6.

**Remaining for a real invoke:** the tx-hash funding path cannot work in this image at
all — its verifier lives in `web.backend.services.ai_market_protocol.on_chain`, which the
hub Dockerfile does not copy. Escrow is the only live funding path, so a first paid invoke
needs a depositor to call `openChannel` on `0x0606983c…72C25D` and pass the resulting
`escrow_channel_id`. That requires a key and is an operator action.

## ⚠ Blocker found on the host (2026-07-27) — do not flip the stub

The live hub's environment already has crypto **on** and testnet **off**, and its payment
recipient is an **Anvil/Hardhat development address**:

```
AIFACTORY_CRYPTO_ENABLED       1
AIFACTORY_PAYMENT_TESTNET      0                                            ← mainnet
AIFACTORY_PAYMENT_VERIFY_STUB  1                                            ← only thing holding the door
AIMARKET_PAYMENT_RECIPIENT     0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266   ← Anvil account #0
AIMARKET_ESCROW_EVM_ADDRESS    0x9fe46736679d2d9a65f0992f2272de9f3c7fa6e0   ← no code on Base
AIFACTORY_AI_MARKET_CONTRACT   0x3Df85a639EAB8B50DD14f09bdeB46D5FeF163017   ← real, 14 758 bytes
AIFACTORY_PROD                 <unset>
```

`0xf39Fd6…2266` is the first account of the standard dev mnemonic. Its private key is
printed by every local Anvil/Hardhat node and reproduced in countless tutorials, so
**anyone in the world can sweep whatever settles there**. `0x9fe4…a6e0` is a
deterministic dev-chain contract address and holds no code on Base — escrow would target
nothing.

Setting `AIFACTORY_PAYMENT_VERIFY_STUB=0` on this host as it stands would not "turn on
payments"; it would start directing real mainnet USDC to a wallet with a public key. The
stub flag is currently the only thing preventing that.

**Fix three addresses first** — the contract address is stale too. Per
[`docs/onchain-journal.md`](onchain-journal.md) §1, the LIVE set was redeployed
2026-07-26 and one wallet holds every role (deployer / owner / operator / oracle-signer /
hub / treasury):

| Variable | Set to | Why |
|---|---|---|
| `AIMARKET_PAYMENT_RECIPIENT` | `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a` | the escrow's authorized hub — `settleChannel` already pays out here by contract, so any other value splits revenue across two destinations |
| `AIFACTORY_AI_MARKET_CONTRACT` | `0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D` | current `AIMarketEscrow`; the configured `0x3Df85a…163017` is the superseded June deploy |
| `AIMARKET_ESCROW_EVM_ADDRESS` | `0x0606983cbEc6D0C12a0B750f72Ceb6032c72C25D` | same contract; the bridge and the verifier must point at one escrow |

`0x1218` is a hot key (`~/.aicom-base-deployer-v4.json`) that also signs deploys and
settlements, so revenue accumulating there shares a blast radius with the operator role.
That is a deliberate trade-off of the current one-wallet design, not an oversight —
worth revisiting when volume stops being demo-sized.

Verify any candidate before use:

```bash
curl -s -X POST https://mainnet.base.org -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_getCode","params":["0xADDR","latest"]}'
```

Both dev addresses are now blocklisted in **two** places, because the standalone hub
image does not ship the `security` package (verified: `security importable: False`
inside the running container) and would otherwise skip the check entirely:

- [`security/prod_startup_guard.py`](../security/prod_startup_guard.py) →
  `_WELL_KNOWN_DEV_ADDRESSES`, for the factory/web stack;
- [`aimarket_hub/config.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/config.py) →
  `is_dev_chain_address()`, used by `payment_readiness()` and by the standalone
  fallback in [`cli.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/cli.py), which previously
  checked only the four stub flags.

With either value set, a hub started with `AIFACTORY_PROD=1` now refuses to boot, and
the manifest reports `payment_configured: false` rather than inviting deposits.
`scripts/payment_preflight.sh` names both explicitly.

## 0. Current state (measured 2026-07-27)

```
https://modelmarket.dev/.well-known/ai-market.json
  hub_version                   3.0.0
  capabilities_count            27      (+38 federated)
  plugins_loaded                14
  payment_configured            false   ← AIFACTORY_PAYMENT_VERIFY_STUB=1 on the host
  payment_testnet               false   ← already mainnet
  channels.demo_mode            true    ← was hardcoded; now tracks config
```

`docker-compose.prod.yml` pins `AIFACTORY_PAYMENT_VERIFY_STUB: "0"`, but the live hub
reports the stub as on. **The public hub is not running the prod overlay** — it is a
plain `docker run` from [`scripts/deploy_hub.sh`](../scripts/deploy_hub.sh) with
`--env-file .env`, and `AIFACTORY_PROD` is absent from that env. Had the overlay ever
been used with the current `.env`, the stub would have been `0` and the deposits above
would already be flowing to the Anvil address.

## 1. Deploy current code FIRST — the flags alone will not work

The running container is `modelmarket-hub:prod-20260726-a42aa97adc`, built from commit
`a42aa97a` (2026-07-21) — **42 commits behind `main`**, and the missing set includes
`75a13fba` (escrow settlement bridge + hub hardening) and `ba024fdf` (pay-on-verified).
The prod checkout at `/root/claudecode/aicom` is on that same commit with local
modifications. Rebuild with [`scripts/deploy_hub.sh`](../scripts/deploy_hub.sh), which
builds from the monorepo root and restarts the container on `:9083`.

The gap is exactly in the payment path. Compare the deployed OpenAPI to
[`api_models.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/api_models.py):

```bash
curl -s https://modelmarket.dev/openapi.json \
  | python3 -c 'import json,sys; print(list(json.load(sys.stdin)["components"]["schemas"]["ChannelOpenRequest"]["properties"]))'
# live: ['deposit_usd', 'token', 'chain', 'wallet', 'tx_hash']
# repo: + payer_signature, escrow_channel_id
```

`ChannelOpenRequest.payer_signature` carries the EIP-191 proof that the depositor
controls the paying wallet. In production `channels.open()` **refuses** an
on-chain-verified deposit without it (short of the
`AIMARKET_CHANNEL_ALLOW_UNPROVEN_PAYER=1` escape hatch, which reopens deposit
front-running). A transport that cannot carry the field makes every production channel
open fail — so flipping the payment flags on the current image converts
"payments off" into "payments broken", not "payments on".

`escrow_channel_id` is missing for the same reason: the escrow bridge (KI-11) is not in
the deployed image at all.

**Order of operations: promote the current build, verify the two fields appear in the
live OpenAPI, and only then set the variables in §2.** The known-pending promotion of
the federated-transport fix from `:9085` to prod `:9083` belongs in the same deploy.

Two further advertisements from the live manifest that do not resolve, worth fixing in
the same pass:

- `mcp_endpoint: https://modelmarket.dev/ai-market/mcp` → **404**. No such route exists
  anywhere in the hub package; peers that use the `mcp_endpoint` transport get nothing.
- `channels.demo_mode` was hardcoded `true` in the plugin manifest, so a fully
  configured hub still advertised demo channels. Fixed in this change set.

## 2. Confirm what the hub is actually running

```bash
docker compose ps && docker compose config --services
```

```bash
docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' <hub-container> | grep -E 'AIFACTORY_(PROD|PAYMENT|CRYPTO)|AIMARKET_(PAYMENT|ESCROW|ALLOW)'
```

If `AIFACTORY_PROD` is absent, the hub is on the base `docker-compose.yml` and the
production startup guard has never run. Bringing it up with the prod overlay is the
real change here; the payment flags are downstream of it.

## 3. The interlock set

`AIFACTORY_PAYMENT_VERIFY_STUB=0` on its own does **not** enable payments. The deposit
path in [`channels.py`](https://github.com/alexar76/aimarket-hub/blob/main/aimarket_hub/channels.py) verifies on-chain only
when the stub is off **and** the process is in production mode; with the stub off and
`AIFACTORY_PROD` unset it fails closed and refuses every deposit. All of these must be
set together, in the host `.env`:

| Variable | Value | Why |
|---|---|---|
| `AIFACTORY_PROD` | `1` | activates the startup guard and the on-chain verifier |
| `AIFACTORY_CRYPTO_ENABLED` | `1` | master switch; off means free tier, no 402, no escrow |
| `AIFACTORY_PAYMENT_VERIFY_STUB` | `0` | otherwise any `tx_hash` is accepted |
| `AIFACTORY_PAYMENT_TESTNET` | `0` | already `0` on the live host |
| `AIMARKET_PAYMENT_RECIPIENT` | canonical owner wallet | where deposits settle |
| `AIFACTORY_AI_MARKET_CONTRACT` | deployed AIMarket address | what the verifier queries |
| `AIMARKET_ALLOW_DEMO_CREDIT` | **unset** | set to `1` it credits unverified deposits |
| `AIMARKET_ESCROW_EVM_ADDRESS` | escrow address | optional; enables escrow-funded channels (KI-11) |

The guard refuses to start on a half-set combination, and it also refuses the inverse —
recipient/contract configured while `AIFACTORY_CRYPTO_ENABLED=0`, i.e. a hub that would
quote prices and collect nothing.

Addresses come from [`docs/onchain-journal.md`](onchain-journal.md). Use the canonical
owner wallet as the recipient, never the exposed burner. **Do not put any private key in
`.env`** — the hub only needs the recipient *address*; signing keys belong to the
escrow-bridge signer configuration.

## 4. Apply

```bash
./scripts/payment_preflight.sh
```

Run it on the host first — it reads the same defaults the hub reads and prints exactly
which interlock is missing. When it says READY:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d hub
```

The startup guard aborts the boot with an explicit list if anything is inconsistent;
a hub that starts has passed every payment interlock.

## 5. Verify from outside

```bash
./scripts/payment_preflight.sh https://modelmarket.dev
```

Expected after the flip:

```
payment_configured=True   channels.demo_mode=False   payment_testnet=False
```

Then a real end-to-end deposit — small, from a wallet you control:

1. `POST /ai-market/v2/channel/open` with the real deposit `tx_hash`, the paying wallet,
   and `payer_signature` over `payer_proof_challenge(payer, tx_hash, chain, deposit_usd)`.
   Deposits are single-use and bound to the wallet that actually paid, so an unsigned or
   mismatched claim is refused by design.
2. Invoke one capability against the channel.
3. `POST /ai-market/v2/channel/close` and confirm settlement on-chain.

Record the tx hashes in [`docs/onchain-journal.md`](onchain-journal.md), the same way the
earlier Base demo deployments are logged.

## 6. Rollback

Set `AIFACTORY_PAYMENT_VERIFY_STUB=1` and restart: the manifest returns to
`payment_configured: false`, `channels.demo_mode: true`, and consumers stop being told
this hub takes money. Open channels keep their balances; only new deposits are affected.
