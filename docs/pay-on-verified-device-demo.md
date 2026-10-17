# Pay-on-Verified for a physical effect — an agent pays a plug only after the meter proves it switched

> 🌐 **English** · [Русский](pay-on-verified-device-demo.ru.md) · [Español](pay-on-verified-device-demo.es.md) · [Français](pay-on-verified-device-demo.fr.md) · [中文](pay-on-verified-device-demo.zh.md)

Base mainnet, 2026-10-16, hub modelmarket.dev (release `899ecbdb4`). A buyer agent paid **$0.05** to
switch a plug on for 60 seconds. The price sat in escrow until GAIA's verifier had checked the signed
command and the meter readings before and after. Nobody appealed within the hour, so the hub debited
$0.05 on chain and the buyer got **$0.95** of its $1.00 deposit back. The first demo, an agent hiring two
strangers to factor a number, is [here](pay-on-verified-demo.md); how device control works is
[in GAIA's docs](https://github.com/alexar76/gaia/blob/main/docs/ACTUATION.md).

## Who is who — read this first

- **The seller is ours.** GAIA (`gaia.gateway`, publisher `gaia`) is run by the modelmarket.dev operator.
- **The plug is simulated.** `plug-sim-01` is a 1500 W heater that exists only in software, and every
  answer says so (`"simulated": true`). This proves the money and verification path, not hardware.
  Real hardware is a Tasmota plug with an energy chip ([ACTUATION.md](https://github.com/alexar76/gaia/blob/main/docs/ACTUATION.md#operators)).
- **The buyer wallet is separate but funded by us:** `0x097e3F339D0b023605e12A6B81E2d6Cb7571475a`, the
  same wallet as in the first demo. For this run the owner topped it up with 0.50 USDC from the operator
  wallet `0x1218…Ad0a`. This proves the mechanism, not third-party demand.
- **The judge is the seller's own verifier.** The hub sends `gaia.actuate@v1` to `gaia.verify@v1`, GAIA's
  exact check, instead of its LLM jury. That makes GAIA both seller and judge. It is acceptable only
  because the check is deterministic over signed evidence anyone can re-run, and because the buyer can
  appeal a pass to the hub's appeal court, a different verifier. See "What this does not show".

## What had to change first, and why

The capability went on sale earlier the same day. Five things stood between it and a paid,
verified call.

| # | Problem | What we did | Why |
|---|---|---|---|
| 1 | The hub had one verifier for everything: the Metis LLM jury. | Verifier routes per capability, `AIMARKET_VERIFY_ROUTES` (hub `71be57610`). `gaia.actuate@v1` → `gaia.verify@v1`; everything else stays with Metis. | A language model cannot check an Ed25519 signature or a meter's physics, and a jury can abstain and leave an honest effect unpaid. A route that cannot be used **refuses** to verify; it never quietly falls back to Metis. |
| 2 | GAIA's verify endpoint answered 503 to every caller in production: the compose file never passed `GAIA_VERIFY_TOKEN` into the container. | Token created on GAIA's host and passed through (`c718f810e`); the hub sends it as a Bearer from the env var the route names. | A passing verdict advances GAIA's anti-replay mark, so an open verify endpoint could refuse every pending settlement. Only the hub may call it. |
| 3 | modelmarket.dev ran an older, hand-patched build with no routing code. | Hashed every file in the live container and compared it with git: no fix existed only on the host. Then a full release from main with `deploy_hub_rebuild.sh`, the previous container kept for rollback. | The code has to be in what actually runs, and a release must not silently drop a patch that lives only on the server. |
| 4 | `gaia.actuate@v1` was listed only as a federated capability, and Pay-on-Verified holds money only for capabilities the hub executes itself. | A local listing: publisher `gaia` (first-party operator publisher), GAIA's signing key pinned, response signatures required. | Without it a verify block is skipped and nothing is held. |
| 5 | The payment canary paged "paid work served for free". | It was Independent's own free trial on a peer the hub only brokers. The canary now knows which peers the hub sells for (`899ecbdb4`). | A false alarm about money teaches people to ignore real ones. |

Before spending anything, the route was proven with a free sandbox trial: the plug drew 1491 W, and the
verdict was `passed`, signed `verifier: gaia.verify@v1` (trace `gaia_c12c4efa209ea762`). No money moved.

## The paid run, step by step

| # | Step | What happened |
|---|---|---|
| 1 | The task and the limit | "Switch plug-sim-01 on for 60 s." Limit: a $1.00 escrow deposit, which the contract will not let the agent exceed. |
| 2 | Find the seller | `GET /ai-market/v2/search` returned `gaia.actuate@v1`, `gaia.gateway`, $0.05, publisher `gaia`. The buyer takes only the **local** listing, because the federated one is never verified. |
| 3 | The work, with evidence | GAIA signed the command (`act_0aec0a640ed36476`), read the meter before, switched, and read it again. Expected ≥ 1000 W within 20 s; **observed 1506.2 W**. The plug switched itself off at 10:53:15 UTC. The whole invoke took 15.5 s. |
| 4 | The verdict | `gaia.verify@v1`: **passed**, score 1.0, at the hub's 0.7 bar (trace `gaia_e34da88c0a648c51`). It was provisional until the appeal window closed at 11:52:29 UTC; nobody appealed, so it became final. |
| 5 | The money | The hub's signer debited **$0.05** on chain at 12:03 UTC. The buyer asked to close, waited out the one-hour settle window, and settled: **$0.05 to the hub, $0.95 back**. |

Cost to the buyer: **$0.05** and about 0.000007 ETH of gas. Balance 1.094148 → 1.044148 USDC.
The run log is [`pov-demo/runs/2026-10-16T105204Z.json`](../pov-demo/runs/2026-10-16T105204Z.json).

## Transactions (Base mainnet)

Contracts: escrow AIMarketEscrowV2 [`0xa4cb6ef7…1B2Eb`](https://basescan.org/address/0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb),
debited by the hub's signer [`0xBE0bBE44…C5f1`](https://basescan.org/address/0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1),
USDC [`0x833589fC…02913`](https://basescan.org/address/0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913).
Escrow channel `0x8c89c278…e8f3`.

| Step | Who | Block | Tx |
|---|---|---|---|
| `USDC.approve(escrow, 1.00)` | buyer | 52679290 | [`0xf765fe99…b52d`](https://basescan.org/tx/0xf765fe99e6570fb7590abb4f9a492b8544d52f96185eb8990931215e3e01b52d) |
| `openChannel` $1.00 | buyer | 52679291 | [`0x6ed3cdb4…19c8`](https://basescan.org/tx/0x6ed3cdb421b1a1619d8a695f857feb34dceac398f27cf9fabd678f9e7c1b19c8) |
| verdict **passed** by `gaia.verify@v1`, final after the appeal window | — | — | — |
| `debitChannel` $0.05 | hub signer | 52681416 | [`0x6973d111…fe10`](https://basescan.org/tx/0x6973d11160f4f58951f42c8ee65ba3639d2b376b02e037e5747663ea7d28fe10) |
| `requestClose` | buyer | 52681422 | [`0xbfb451bd…52cf`](https://basescan.org/tx/0xbfb451bd33db3af0db7f3258c6f0fab56ded47204e9c4f9a28540df575db52cf) |
| `settleChannel`: $0.05 to the hub, **$0.95 back** | buyer | 52683232 | [`0x1e2b0aa7…9f25`](https://basescan.org/tx/0x1e2b0aa794924a373635dc651e20afd6a1baa2be5e5f3d80724fbff1fcef9f25) |

## What went wrong on the way

1. **The trust oracle was out of reach.** The link from the hub's host to the oracle host was degraded
   that day: LUMEN answered in 4 to 35 seconds or not at all. The hub asks LUMEN about a publisher it has
   no stored trust for, so the first five free trials were refused with "trust oracle unavailable" and
   nothing was charged. The sixth got an answer, the hub stored trust 0.70 for `gaia`, and the paid run
   used that stored value. The network problem itself is still open.
2. **Too short to be safe.** The trial that got through asked for 5 seconds, and GAIA refused it: `plug-sim-01`
   accepts 10 to 900 seconds, so nothing stays on unbounded. Nothing was charged.
3. **The first debit submission failed** and the next sweep, 15 minutes later, landed it. The signed
   authorization outlives the appeal window by two hours precisely so that a retry still works.
4. **The release had its own trap.** The hub's release check requires the published pipeline client
   to match the hub version. The served client was 3.15.1 and the hub 3.15.28, so the release would have
   rolled itself back. The client was rebuilt first.

## What this does not show

- Real hardware: the plug is simulated. A Tasmota plug signs what its meter reports — custody of the
  report, not proof that the hardware cannot lie.
- An independent judge: GAIA sells and verifies. The evidence is signed with keys GAIA holds, so no
  verifier, GAIA or an LLM, could catch evidence forged by the key holder. The buyer's protection is
  that the check can be re-run by anyone (`POST /v1/verify`, or `gaia.verify@v1` with the bundle), plus
  the appeal court.
- Third-party demand: the seller and the buyer's money are ours.

## Run it yourself

```bash
python3 pov-demo/buyer.py --key-file <your wallet json> --task actuate --duration 60 --yes
```

You need $1.00 USDC and about 0.00005 ETH on Base. With the one-hour appeal window and the one-hour
settle window the run takes about two hours; everything except $0.05 comes back.
