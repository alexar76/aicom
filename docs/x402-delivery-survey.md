# x402 delivery survey — one paid call to 100 sellers

> 🌐 **English** · [Русский](x402-delivery-survey.ru.md) · [Español](x402-delivery-survey.es.md) · [Français](x402-delivery-survey.fr.md) · [中文](x402-delivery-survey.zh.md)

**More than twenty trust indexes check whether x402 sellers answer with a price. We checked what a buyer gets after paying.**

On 2026-10-05 we drew 100 sellers at random from the CDP Bazaar. We sent each one the example request from its own listing, paid for it in USDC on Base and checked the charge on chain. A five-model jury then judged every answer. Sellers are not named here; the reasons are under [Why no names](#why-no-names).

## Results

| Outcome | Sellers |
|---|---|
| Answer accepted by the jury | 74 |
| Answer rejected by the jury, buyer charged | 3 |
| Answer received, jury not confident either way | 8 |
| Error after payment, buyer **not** charged | 9 |
| Error after payment, buyer charged | 1 |
| Not bought | 5 |
| **Total** | **100** |

- **Purchases.** 95 payments were signed for $0.536 in total. 85 were executed on chain, for $0.489.
- **Accepted answers.** 74 of the 85 paid calls (87%) returned a genuine answer of the kind the listing promises.
- **Money for nothing.** 4 of the 85 paid calls (4.7%) charged the buyer for no useful answer, $0.022 in all.
- **Fair failures.** Nine sellers failed after payment and did not take the money; several said so in the error ("you were not charged").
- **Typical answer time.** Paid calls answered in 1.9 s at the median, 4.3 s at the 90th percentile and 40 s at most.

## What went wrong

| Problem | Sellers |
|---|---|
| The listing's own example fails: the service rejects it, or it leads to an error or an echo of the field description | 7 |
| The listing's own example cannot be sent: placeholders instead of values, or a body type HTTP clients do not send | 2 |
| Upstream failure after payment (gateway 502, RPC down, cold model, price feed reconnecting) | 4 |
| Error after the charge | 1 |
| Empty result for money | 1 |
| Incomplete result for money ("partial", "indeterminate") | 1 |
| An error report where the promised data should be | 1 |
| Settlement header says "paid", the chain says no transfer | 1 |
| Charged, but sent no settlement header | 1 |
| The 402 mixes x402 v1 and v2 fields, so the reference client refuses to pay | 1 |
| Payee in the 402 differs from the payee in the listing | 1 |
| Live price above the listed price | 1 |
| No answer to the unpaid request within 20 s | 1 |

One seller can have more than one problem.

There is little to call fraud. The commonest defect is the listing itself: about one seller in ten advertises an example request that does not work. A buyer agent copying the documented call gets an error. Usually it is not charged for it, but it gets no answer either.

## What a 402 probe cannot see

Every index we found sends an unpaid request and reads the 402. In our sample, 96 of 100 sellers passed that test. Several things show up only when someone pays:

- whether the documented example works;
- whether the seller settles on an error;
- whether the settlement it reports reached the chain;
- whether a 200 response is an answer or an empty list.

The figures in this survey come from 95 paid calls, not from the 402.

## The bigger finding: demand

The Bazaar publishes its own 30-day counters. Of 34,768 listings, 22,559 (65%) had exactly one paying wallet in 30 days, most likely the seller paying once to get indexed. Only 396 (1.1%) had ten or more. In our sample, 23 of the 74 sellers whose answer was accepted had exactly one payer.

The x402 market does not look short of trust. It looks short of buyers.

## Method

- **Catalogue.** CDP Bazaar discovery API on 2026-10-05 19:47 UTC: 34,768 listings. The snapshot is kept, sha256 `6de6966927e5cc5b83f55f7c128c48861eab4cebf1e3fb61c2c9cb0d583d876c`.
- **Eligible listings.** x402 v2, HTTPS, a declared example request (`extensions.bazaar.info.input`), and an `exact` USDC offer on Base mainnet of at most $0.01. Our own hosts and wallets, and those of our sibling ecosystems, were excluded. That leaves 28,382 listings at 1,466 hosts. One host counts as one seller.
- **Sample.** 100 hosts drawn by sha256 of the seed `aimarket delivery survey 2026-10-05` and the host name. One listing per host was drawn the same way. Anyone holding the snapshot and the seed draws the same sellers.
- **Request.** Exactly the seller's declared example: method, path parameters, query and body. Declared headers were not sent; they are mostly the seller's own API keys.
- **Dry run.** The same request without payment, to read the 402 and compare it with the listing. 96 sellers could be paid within the cap and to the listed payee.
- **Purchase.**
  - The 402 is read again, and payment goes ahead only if its terms are exactly those of the dry run.
  - The buyer is the reference x402 client 2.28, with its own spend cap set to $0.01. It may sign only an EIP-3009 `transferWithAuthorization`: never Permit2, never an approval.
  - The whole run had a hard budget of $0.55. Every answer was kept as evidence.
- **Charge.** USDC's `authorizationState(payer, nonce)` on Base for every signed payment. This is the chain's record, not the seller's word.
- **Judgement.**
  - The jury is Metis, five models from five vendors. Its prompt and verdict reader are the ones that release escrow in [Pay-on-Verified](pay-on-verified-demo.md); see also [jury-3-vs-5.md](jury-3-vs-5.md).
  - The question: is the answer a genuine, complete response to this request, of the kind the listing promises — not an error, an empty or placeholder result, a demand for more payment or credentials, or unrelated content?
  - A verdict counts only when the jury's own confidence is at least 0.7.
  - We spot-checked 12 accepted answers by hand. All were real: a 768-number embedding, a Wikipedia article, Product Hunt data, a correct inverse Web Mercator projection.

## Limits

- **One moment, one call.** Each seller got one call on one day. A seller that was down at that minute counts as down.
- **The seller's own example only.** A trivial example ("parse the user agent `example`") gets a trivial answer, and that passes.
- **Not a fact check.** The jury judges whether the answer is genuine and of the promised kind. Where it could check a fact (a projection, an article), it did; in general it does not.
- **A narrow slice of the market.** Sellers at $0.01 or less, on Base, with a declared example. Listings at higher prices or without an example are not covered.
- **Our interest in the answer.** We run [AIMarket](https://modelmarket.dev), a market where agents pay agents, and we sell verification. That is why the seed, the tool and the anonymized data are public, and why this report says what it found: most sellers deliver.

## Why no names

A paid call on one day is a small piece of evidence about a business, and our request may not be the use a seller had in mind. Instead of a public list:

- **The data.** The anonymized row for every seller is in [`scripts/delivery-survey/results/2026-10-05.json`](../scripts/delivery-survey/results/2026-10-05.json). Rows are shuffled within each outcome, prices and payer counts are given as bands, and there are no hosts or transactions.
- **The private evidence.** The full file — host, request, answer, transaction and verdict — hashes to sha256 `f55c952d752319d1a862c7154f8d93ca0aa675b5cd1172b368846e5fbe2f5cf9`, so it cannot change after publication. Each seller can be shown its own row.
- **Contacting sellers.** We are writing to the sellers whose listings had a problem, each with its own evidence.

A seller can also check itself with the same tool. The unpaid step costs nothing:

```bash
cd scripts/delivery-survey && npm ci
node survey.mjs catalog --out bazaar.json
node survey.mjs sample --catalog bazaar.json --host your.host --cap 0.01 --seed self --out plan.json
node survey.mjs probe --plan plan.json --out probe.jsonl      # unpaid: your own example and your 402
node survey.mjs buy --plan plan.json --probe probe.jsonl --out buy.jsonl --budget 0.05 \
  --payer 0xYourBuyer --key-file wallet.json                   # one paid call per listing
node survey.mjs chain --buy buy.jsonl --out chain.json         # charged or not, by the chain
```

`wallet.json` holds `{"mnemonic": "…"}` of a throwaway buyer wallet (`--address-index` picks the account). Use a separate wallet with a few cents on it.

## Tool and data

- Tool: [`scripts/delivery-survey/`](../scripts/delivery-survey/). It covers sampling, the dry run, purchase, the chain check and the report, with 22 tests. The tests include a local seller that verifies the EIP-712 signature for real.
- Jury step: [`judge_in_hub.py`](../scripts/delivery-survey/judge_in_hub.py). It runs inside our hub, where the verifier key lives.
- Anonymized data: [`results/2026-10-05.json`](../scripts/delivery-survey/results/2026-10-05.json).
