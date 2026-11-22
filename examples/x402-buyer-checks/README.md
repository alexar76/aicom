# Two checks around an x402 payment

A buyer agent that pays over [x402](https://www.x402.org) signs a transfer on the strength of one HTTP response,
and learns from another whether it was charged. `checks.mjs` adds one question on each side of the payment:

| When | Question | Agent | Good verdict |
|---|---|---|---|
| Before signing | Should I pay this 402: is the asset real USDC, is the amount within my budget, who is the payee? | `x402.preflight@v1` | `looks_payable` |
| After the answer | Did that transaction pay that payee exactly that amount, and is it final? | `x402.settlement.check@v1` | `paid` |

Both agents run on the [HESTIA hearth](https://hestia.modelmarket.dev) and are free. The script signs nothing and
pays nothing; the payment itself stays with your x402 client. What each agent reads and checks:
[`hestia-agents/docs/AGENTS.md`](../../hestia-agents/docs/AGENTS.md#x402-preflight).

## Run it

Node 18 or newer, no dependencies. Checked on 2026-11-22 with Node 22.22.1.

```bash
node checks.mjs preflight https://tienda.textokit.store/api/translate-es --method POST --body '{"text":"hola"}' --max-usd 0.01
```

```text
offer:   $0.003 USDC on eip155:8453 to 0x6b5aF9924f4CD35643c11a9fd1C983f77261A6E1
verdict: review_first
  ok   asset_is_usdc: USDC on base
  ok   eip712_domain: names the token's own EIP-712 domain USD Coin / 2
  ok   within_budget: $0.003 within $0.01
  ok   pay_to: payTo 0x6b5aF9924f4CD35643c11a9fd1C983f77261A6E1 is a valid recipient
  ok   resource_on_this_host: the offer binds https://tienda.textokit.store/api/translate-es, on the host called
  ok   timeout: maxTimeoutSeconds 300 is ordinary
  FAIL payee_has_payments: no USDC received in the last 24 h
```

`review_first` is not a refusal: the offer is well formed, and the payee received nothing in the last day, which an
agent should not wave through on its own. The output changes with the seller's last 24 hours.

```bash
node checks.mjs settled 0xd8a41fb865beba51d9e795f556dc3b77e6ce5bb20a0dceb2e0691aa791997531 0xb73d8bc93b791510c4733c5c5ac2015a3c2930ec 0.022 --payer 0x9d24d267cf8d9a8b9ed104b4856cde8830c266ef --nonce 0x84428e7eae7b08cac1ec9186e338e14fa5056d9f62bb9d92e1ea927370b8e779
```

```text
verdict: paid
  ok   chain: the RPC serves chain 8453
  ok   succeeded: status 0x1
  ok   canonical_block: block 52165064 is the canonical one
  ok   transfer: a USDC transfer of 22000 to pay_to
  ok   authorization: AuthorizationUsed(payer, nonce) right before the transfer
```

Exit code 0 means the good verdict, 2 any other verdict, 1 an error.

## In an agent

The two functions are exported. The outline below shows where they sit; `payWithYourClient` stands for whatever
x402 client you already use and is not part of this example.

```js
import { preflight, settled } from './checks.mjs';

const before = await preflight({ url, method: 'POST', body, maxUsd: '0.01' });
if (before.verdict !== 'looks_payable') throw new Error(`not paying: ${before.verdict}`);
const offer = before.offers[0];

const { response, tx, payer, nonce } = await payWithYourClient(url, body);   // your client signs and sends

const after = await settled({ tx, payTo: offer.pay_to, amountUsd: offer.amount_usd, payer, nonce });
if (after.verdict !== 'paid') console.warn(`settlement: ${after.verdict}`);  // `paid_not_final`: on chain, not yet finalized
```

## Limits

- `x402.preflight@v1` makes one unpaid request to the address you name, so the seller sees that request.
- It checks the first `exact` USDC offer on Base or Base Sepolia.
- A good verdict says the offer is consistent and the payee is known on chain. It says nothing about the quality of
  the answer you will get.
