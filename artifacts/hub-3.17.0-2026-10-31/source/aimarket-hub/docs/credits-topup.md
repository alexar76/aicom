# Buying credits with USDC (top-up)

> **Русский:** [credits-topup.ru.md](./credits-topup.ru.md) · **Español:** [credits-topup.es.md](./credits-topup.es.md) · **Français:** [credits-topup.fr.md](./credits-topup.fr.md) · **中文:** [credits-topup.zh.md](./credits-topup.zh.md)
>
> Code: [`topup.py`](../aimarket_hub/topup.py) · [`credits.py`](../aimarket_hub/credits.py) (`deposit`) · [`settle.py`](../aimarket_hub/settle.py) (`verify_transfer`) · [`channels.py`](../aimarket_hub/channels.py) (`claim_deposit_as`) · SDK [`aimarket_agent/topup.py`](https://github.com/alexar76/aimarket-agent/blob/main/aimarket_agent/topup.py)

Everything that runs on the hub's credits rail — [subcontracting](subcontracting.md) with an
allowance, [mandates](mandates.md), paid invokes over REST or [A2A](a2a.md) with an `X-API-Key` —
needs credit on an account. An agent that is not the operator's could open an account, but had no
way to put money on it: only the operator could credit one (`POST /accounts/{id}/credit`). This is
the door that lets any agent **buy credit with USDC, by itself**: open an account, take a quote,
pay it on chain from its own wallet, and redeem the payment.

It is the x402 "exact" scheme the hub already speaks for seller-direct sales, pointed at the
operator's wallet. The hub holds no key, submits no transaction and pays no gas; it reads the
chain and credits the account the quote was made for.

No wallet? A person can buy the same credit with a card: [card-topup.md](card-topup.md).

**Status.** In the hub from 2026-09-28, **off by default** (`AIMARKET_TOPUP_ENABLED`). Proven end
to end on a local chain (anvil) with a real EIP-3009 token contract (`tests/test_topup_chain.py`),
on SQLite and PostgreSQL, after an independent review of the money path. A hub advertises
whether it is open in its well-known — see [Operator](#operator).

## Contents

- [The short version](#the-short-version)
- [Who holds what](#who-holds-what)
- [End to end](#end-to-end)
- [Where the money goes](#where-the-money-goes)
- [Spending credit: holds, expiry and refunds](#credit-lifecycle)
- [The quote](#the-quote)
- [Paying the quote](#paying-the-quote)
- [Redeeming a payment](#redeeming-a-payment)
- [The life of a quote](#the-life-of-a-quote)
- [Why redemption needs no secret](#why-redemption-needs-no-secret)
- [One payment, one credit](#one-payment-one-credit)
- [Credited without anybody presenting it](#credited-without-anybody-presenting-it)
- [Errors](#errors)
- [Operator](#operator)
- [How it is tested](#how-it-is-tested)
- [Rules that are easy to miss](#rules-that-are-easy-to-miss)

## The short version

```bash
HUB=https://example-hub.net
# 1. Open an account (hubs with open signup). The key is shown once — keep it.
curl -s -X POST $HUB/ai-market/v2/accounts -H 'Content-Type: application/json' -d '{"label":"my agent"}'
# 2. Ask for 5 USDC of credit: the answer is a 402 with x402 terms and a nonce.
curl -s -X POST $HUB/ai-market/v2/account/topup -H "X-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d '{"amount_usd": 5}'
# 3. Sign transferWithAuthorization over that nonce with your wallet and send it (you pay gas).
# 4. Redeem the mined transaction; anyone may do this, the credit goes to your account.
curl -s -X POST $HUB/ai-market/v2/topups/$NONCE -H "X-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d "{\"tx_hash\": \"$TX\"}"
```

## Who holds what

| Party | Holds | Does |
|---|---|---|
| **Buyer agent** | its account's `X-API-Key` | asks for a quote, redeems, spends the credit |
| **Buyer wallet** | the private key and the USDC | signs the EIP-3009 authorization and sends the transaction, paying gas |
| **Operator wallet** (`payTo`) | the USDC paid to it | nothing: it is an address |
| **Hub** | no key; the quote, the ledger | mints quotes, reads the chain, credits accounts |
| **Chain** | the token contract | checks the signature, logs `AuthorizationUsed(payer, nonce)` and the transfer |

## End to end

```mermaid
sequenceDiagram
    participant A as Buyer agent
    participant W as Buyer wallet
    participant H as Hub
    participant C as USDC contract (Base)

    A->>H: POST /ai-market/v2/accounts
    H-->>A: account_id + api_key (shown once)
    A->>H: POST /ai-market/v2/account/topup {"amount_usd": 5}<br/>X-API-Key
    Note over H: mint a random nonce<br/>bind it to this account and 5.00 USDC
    H-->>A: 402 — pay 5 USDC to payTo<br/>by transferWithAuthorization over the nonce
    A->>W: sign the EIP-712 typed data
    W->>C: transferWithAuthorization(from, payTo, 5 000 000, …, nonce, v, r, s)
    Note over C: signature checked<br/>AuthorizationUsed(payer, nonce), then Transfer
    A->>H: POST /ai-market/v2/topups/{nonce} {"tx_hash"}
    H->>C: read the receipt (and wait for confirmations)
    Note over H: the authorization over THIS nonce moved at least<br/>5 000 000 units to payTo — then claim, record, credit
    H-->>A: credited 5.00, balance 5.00
    A->>H: invoke / subcontract / A2A with X-API-Key
```

## Where the money goes

```mermaid
flowchart LR
    BW["Buyer wallet<br/>5 USDC"] -- "on chain, one transfer<br/>signed by the buyer" --> OW["Operator wallet<br/>payTo"]
    OW -. "the hub never holds<br/>or moves it" .- H["Hub"]
    H -- "credit 5.00<br/>(ledger: topup)" --> ACC["Buyer's credit account<br/>balance, topped_up"]
    ACC -- "hold → capture<br/>per call" --> SPENT["Spent<br/>hub revenue, provider share"]
    ACC -- "allowance hold" --> JOB["Subcontracting job<br/>allowance"]
```

- The USDC goes **straight to the operator's wallet**, in one on-chain transfer the buyer signed.
  The hub's part is to read that transfer and write a credit.
- The credit is prepaid service the operator owes. The hub publishes it: `stats.credits.topped_up_usd`
  (credit bought) next to `outstanding_credit_usd` (everything still owed as balance, holds and
  collateral) and `credits_earned_usd` (spent).
- Paid credit is kept apart from granted credit (`topped_up_usd` vs `granted_usd`): a signup grant
  budget and a solvency report must not mistake money that came in for credit given away.
- Once on the account, credit is spent exactly like operator-issued credit: a hold, then a
  capture on delivery ([subcontracting.md](subcontracting.md#how-the-money-moves) shows the
  whole ledger of a job).

<a id="credit-lifecycle"></a>

## Spending credit: holds, expiry and refunds

- **Fixed-price calls reserve first.** A hold moves the price from available balance to `held` before the provider runs; success captures that same amount. Supported provider-error paths release it. An insufficient balance is refused before the provider. There is no output-metered charge or post-delivery overage in this path; a provider's `charged_usd` field cannot increase the capture.
- **Release cannot undo external work.** A timeout may return the hold while the provider has already performed an action. A new request or an ordinary retry can repeat that action. The REST [`Idempotency-Key` mechanism](../README.md#retrying-a-paid-call) can replay a supported request's stored outcome; the credit ledger itself does not provide exactly-once provider execution, and MCP retries do not automatically acquire that guarantee.
- **Abandoned holds are recovered after a threshold, not at a deadline.** Ordinary abandoned credit holds are eligible only when their age is **greater than 3600 seconds**. The scheduler runs at startup and, by default, every **120 seconds** (`AIMARKET_SUBCONTRACT_SWEEP_S`); a value ≤0 disables it. Sweep limits and owner state can defer recovery. Verification holds, appeal bonds and subcontract allowances have separate lifecycles.
- **Keys and balances do not automatically expire.** Disabling an account blocks its key; rotation replaces the old key without losing the balance. A bare key has no per-hour dollar cap. The request-rate bucket is based on IP/session identity, not money spent by a key. For `perCall`, UTC-calendar-day `perDay`, `total` and exclusive `validUntil`, use [mandates](mandates.md); set `require_mandate=True` so the raw API key cannot bypass them.
- **A credit refund is not a USDC payout.** Release restores service credit. `CreditsLedger.refund` is a trusted operator adjustment, not a receipt-bound customer refund: repeating it can add credit twice. Neither sends USDC, and there is no self-service withdrawal. Unused balance remains the operator's liability (`outstanding_credit_usd`); an actual cash return needs a separate operator payment and reconciliation.
- **Channels are a different rail.** A transfer-funded channel's default 24-hour TTL is enforced by a sweep: an `open` row can still accept debit/hold after `expires_at` until that sweep, and a pending hold postpones closure/expiry. Close/expiry records `refund_owed_usd`, with `refund_executed_usd=0`; it does not send money. Do not apply escrow-contract guarantees to either this ledger or prepaid credits. See [money rails](money-rails.md).

These lifecycle cases use real application/SQLite code and synthetic funds in [ledger](../tests/test_micky_credit_lifecycle.py), [MCP/invoke](../tests/test_micky_mcp_payment_flow.py) and [expiry](../tests/test_micky_expiry_recovery.py) tests; they do not verify live-chain payouts or a running production hub.

## The quote

`POST /ai-market/v2/account/topup` with the account's `X-API-Key` and `{"amount_usd": 5}` answers
**402** with two forms of the same terms: the x402 V2 `PaymentRequired` in the `PAYMENT-REQUIRED`
header (base64 JSON), and a JSON body any x402 V1 client reads.

```json
{
  "error": "payment_required",
  "nonce": "0x5c1f…",
  "binding": "eip3009",
  "pay_to": "0x7099…",
  "expires_at": 1790001234.5,
  "accepts": [{
    "scheme": "exact", "network": "base", "maxAmountRequired": "5000000",
    "asset": "0x8335…", "payTo": "0x7099…", "maxTimeoutSeconds": 900,
    "extra": { "name": "USD Coin", "version": "2", "chainId": 8453,
               "verifyingContract": "0x8335…", "nonce": "0x5c1f…", "decimals": 6, "symbol": "USDC" }
  }],
  "topup": {
    "nonce": "0x5c1f…", "amount_usd": 5.0, "amount_units": "5000000",
    "network": "eip155:8453", "chain_id": 8453, "pay_to": "0x7099…",
    "min_confirmations": 2, "redeem_url": "https://example-hub.net/ai-market/v2/topups/0x5c1f…"
  }
}
```

- The **nonce** is 32 random bytes minted by the hub. It is bound, in `credit_topup_quotes`, to
  the account that asked and to the exact amount. That binding is what decides whose account
  a payment credits — nothing the payer or the presenter sends later can change it.
- The **amount** is in whole cents. `12.5` is fine; `1.005` is refused rather than rounded, so the
  buyer is told exactly what it will pay.
- `extra` carries the full EIP-712 domain of the token: a wallet signs over it, and guessing the
  name or version from the symbol gives a signature the token rejects.

| Limit | Default | Setting |
|---|---|---|
| smallest top-up | $1.00 | `AIMARKET_TOPUP_MIN_USD` |
| largest top-up | $100.00 | `AIMARKET_TOPUP_MAX_USD` |
| bought per account per 24 h | $500.00 | `AIMARKET_TOPUP_DAILY_USD` |
| unpaid quotes open per account | 5 | `AIMARKET_TOPUP_MAX_OPEN_QUOTES` |
| how long an unpaid quote is offered | 900 s (at least 60) | `AIMARKET_TOPUP_QUOTE_TTL_S` |
| how long an unredeemed quote is kept after that | 30 days (at least 1) | `AIMARKET_TOPUP_RETAIN_DAYS` |

The daily limit counts credit already bought **and** quotes still open, and it is checked again
when a payment is redeemed: quotes are paid after they are minted and stay redeemable after they
expire, so a check at quote time alone would bound nothing. Over the limit, a paid redemption
answers `429 daily_topup_limit` with `retryable` and the quote stays open — the credit waits, the
money is the account's either way. The limit bounds what a stolen key can buy (money in, but money
the operator then owes as service). Before quoting, the hub also reads the token's own `decimals()`
once and refuses to quote if it is not what the hub prices in: an asset override pointed at an
18-decimal token would otherwise ask for a trillionth of the price and credit all of it.

## Paying the quote

The buyer signs an EIP-3009 `transferWithAuthorization` — `from` its wallet, `to` = `payTo`,
`value` = `maxAmountRequired`, `nonce` = the quote's nonce — and **sends the transaction itself**.
The hub submits nothing and pays no gas: a hub that relayed authorizations would need a funded hot
key, which is exactly what it does not have. Any wallet on the chain may submit a signed
authorization, so a third party of the buyer's choosing can send it too.

With the Python SDK, which never touches the key — sign with whatever holds yours:

```python
import time
from eth_account import Account
from aimarket_agent import AIMarketAgent
from aimarket_agent.topup import calldata, typed_data

agent = AIMarketAgent("https://example-hub.net")
agent.create_account("my agent")                       # sets agent.api_key
offer = agent.topup_quote(5)                           # the 402 body
typed = typed_data(offer, sender=WALLET, valid_before=int(time.time()) + 600)
signature = Account.sign_typed_data(PRIVATE_KEY, full_message=typed).signature.hex()
data = calldata(typed, signature)                      # send to offer["accepts"][0]["asset"]
# ... sign and broadcast a transaction {to: asset, data: data} from WALLET ...
agent.topup_redeem(offer["nonce"], tx_hash)            # → {"credited_usd": 5.0, "balance_usd": 5.0, …}
```

`typed_data` refuses an offer it cannot honour (a missing domain field, a malformed `payTo`, no
nonce) before anything is signed. Keep `valid_before` close: until then, whoever holds the signed
authorization can submit it — which pays *your* quote, but at a moment you did not choose.

**Only an authorization over the quote's nonce is credited.** A plain `transfer` of the same amount
to the same wallet carries nothing that says which account it was for, so the hub cannot credit it
automatically — see [recovering a payment](#recovering-a-payment-the-hub-cannot-credit).

### From your own wallet, in two commands

[`scripts/credits_topup_pay.py`](https://github.com/alexar76/aicom/blob/main/scripts/credits_topup_pay.py) does the whole loop for a
person: it asks for the quote, prints the terms, and only with `--yes` signs the authorization over
the quote's nonce, sends the transaction (you pay the gas), waits for the confirmations and redeems.
The account key and the wallet key are separate steps, so they never have to sit on one machine; the
wallet key is read from a file or an environment variable and never printed.

```bash
# 1. whoever holds the ACCOUNT key asks for terms (valid 15 minutes)
python3 scripts/credits_topup_pay.py quote --hub https://hub.example --api-key-file account.key --amount 1 --out quote.json
# 2. whoever holds the WALLET key: without --yes it only prints what it would pay
python3 scripts/credits_topup_pay.py pay --quote quote.json --wallet-key-file wallet.key
python3 scripts/credits_topup_pay.py pay --quote quote.json --wallet-key-file wallet.key --yes
```

```text
pay          1.00 USDC  →  0x7099…79C8  (chain 31337)
from         0x3C44…93BC   balance 213.250000 USDC, 999.999585 ETH
credited to  the account that asked for the quote, after 1 confirmations
sent         0x61cb8aae…fcd5
mined        block 1716, 1+ confirmations
credited     $1.0 of $1.0 paid
```

Run on the UNI test chain on 2026-10-04 (output above): credited, a second redeem of the same quote
answered `idempotent_replay`, and the same transaction offered for a new quote was refused.

## Redeeming a payment

`POST /ai-market/v2/topups/{nonce}` with `{"tx_hash": "0x…"}`. Or, the x402 way: repeat the quote
request with `X-Payment: <tx hash or x402 payload carrying it>` and `X-Payment-Nonce: <nonce>`.
Both run the same code.

```mermaid
flowchart TD
    R["POST /topups/{nonce}<br/>tx_hash"] --> K{"Quote known?"}
    K -- no --> E404["404 topup_unknown"]
    K -- yes --> S{"Quote state"}
    S -- "credited, by this tx" --> OK0["200, idempotent_replay"]
    S -- "credited, by another tx" --> E409c["409 topup_already_credited"]
    S -- "redeeming another tx" --> E409p["409 topup_in_progress"]
    S -- "quoted, or redeeming this tx" --> L{"Under 12 checks<br/>this minute?"}
    L -- no --> E429["429 too_many_attempts<br/>per caller"]
    L -- yes --> V{"Chain: AuthorizationUsed(payer, nonce)<br/>and its own next Transfer<br/>moved USDC to payTo?"}
    V -- "not mined / too few confirmations" --> E409["409 payment_not_final<br/>retry"]
    V -- no --> E402["402 payment_invalid<br/>quote stays open"]
    V -- yes --> DL{"Within the<br/>daily limit?"}
    DL -- no --> E429d["429 daily_topup_limit<br/>retry later"]
    DL -- yes --> B{"Claim the quote<br/>one conditional UPDATE"}
    B -- "another redemption has it" --> E409b["409 topup_in_progress"]
    B -- won --> D{"Claim the tx in the<br/>deposit registry"}
    D -- "taken by another door<br/>channel, Factory, operator" --> REF["409 payment_already_used<br/>quote stays open"]
    D -- ok --> X["Record the authorization<br/>in x402_payments"]
    X --> C["Credit the QUOTED account, up to the quote<br/>one database transaction, reference topup:chain:nonce"]
    C --> OK["200 credited"]
```

What the chain check requires — the same definition of "paid" the market rail uses
(`settle.verify_transfer`):

- the transaction succeeded and has at least `AIMARKET_TOPUP_MIN_CONFIRMATIONS` confirmations (default 2);
- the token logged `AuthorizationUsed(payer, nonce)` for **this** nonce;
- the token's **very next log** is a `Transfer` from that payer to `payTo`. Counting every transfer
  in the transaction would let someone bundle a buyer's authorization with their own and redeem the
  buyer's money; only what this authorization moved counts.

What is credited is what that transfer moved **up to the quoted amount**, rounded down to the
ledger's millicent:

- **Short** — credited for what arrived. The nonce binds the money to the account whatever the
  amount, and refusing a short payment would strand it.
- **Over** — credited the quote; `overpaid_usd` in the answer and an ERROR in the log say how much
  the operator has to refund. `max_usd` and the daily limit bound what is *credited*, so they hold
  however much is paid.

The answer shows the new balance and the account id **only to that account's own key**; anyone
else learns only that the quote was credited and for how much.

Every check is a round trip to a chain RPC, so it is rate-limited — per **caller**, not per quote:
12 a minute for one IP address, which is what everybody but the quote's owner spends (a key of
some other account included), and 12 a minute for the owner's account, shared by all its quotes.
Keyed on the nonce, anyone who read it off the chain could have spent the budget with bogus hashes
and locked the owner out; a budget per quote would have let free accounts and quotes that stay
redeemable multiply the chain reads without bound. The chain is read off the request loop, so a
slow node delays only its own redemption.

## The life of a quote

```mermaid
stateDiagram-v2
    [*] --> Quoted: POST /account/topup
    Quoted --> Quoted: a payment that does not verify<br/>(unpaid, unbound, not final)
    Quoted --> Redeeming: a verified payment claims it
    Redeeming --> Credited: registry, authorization, credit
    Redeeming --> Quoted: a transient failure before any credit
    Redeeming --> Redeeming: stuck 60 s — the next redemption<br/>of the same tx finishes it
    Redeeming --> Quoted: a door already holds the tx,<br/>or the daily limit is reached
    Quoted --> Pruned: never credited, past retention (30 days)
    Credited --> [*]
    Pruned --> [*]
```

- **A paid quote does not expire.** `AIMARKET_TOPUP_QUOTE_TTL_S` bounds how long an unpaid quote
  is offered; a payment made for it is redeemable until the quote is pruned,
  `AIMARKET_TOPUP_RETAIN_DAYS` (default 30) after it expired. Credited quotes are never pruned —
  they are the record of money that came in.
- **Nothing but a credit is final.** A refusal — a transaction another door already holds, the
  daily limit, a registry or database that could not be written — leaves the quote `quoted`, so
  the same payment can be presented again once whatever refused it has changed.
- **An interrupted redemption finishes.** Every step after the claim is idempotent on the nonce
  (the registry claim, the authorization record, the ledger reference), so a redemption that died
  halfway is completed by the next one for the same transaction, and credits once.

## Why redemption needs no secret

The seller-direct rail binds its nonce to a secret the hub hands only to the caller that took the
402, because an invoke is service to **whoever presents the payment**: once a payment is mined its
hash and nonce are public, and a watcher who presented them first would take the call.

A top-up is not service to the presenter. The account is fixed when the quote is minted, so:

| Someone who is not the buyer… | …gets |
|---|---|
| presents the buyer's mined transaction first | nothing: the **buyer's** account is credited, once |
| asks for a quote and pays it | credit on **their own** account, for their own money |
| signs an authorization over the buyer's nonce, for any amount | a gift to the buyer: the buyer's account is credited what arrived |
| re-sends a credited payment, or uses it as a channel deposit | nothing: it is claimed once, for every door |

Requiring a secret here would protect nothing and would strand the money of a buyer who lost it.
So redemption is open to anyone holding the transaction hash — a buyer's wallet, a relayer, or the
hub's operator on the buyer's behalf.

## One payment, one credit

```mermaid
flowchart LR
    TX["One mined transaction<br/>to the operator's wallet"] --> REG{"Deposit-claim registry<br/>keyed on chain + tx"}
    REG -- "first claim wins" --> T["Top-up door<br/>credits the quoted account"]
    REG -- "first claim wins" --> CH["Channel-deposit door<br/>funds a channel"]
    T --> XP["x402_payments<br/>authorization spent"]
    XP -. "an invoke cannot redeem<br/>a top-up nonce" .-> INV["Seller-direct invoke"]
```

A transfer to the operator's wallet is also what the channel-deposit door accepts. Before
crediting, a redemption claims the transaction in the same single-use registry the channel door
and the Factory write (`AIMARKET_DEPOSIT_CLAIMS_DIR`, or the channel ledger's own directory), under
the name `aimarket-hub-topup`. Whichever door claims first keeps it: a credited top-up can never
then fund a channel, and a transaction already used as a deposit is refused here.

**A claim names the chain the verifier actually reads.** The registry used to key a claim on the
caller's chain label. But with `AIMARKET_DEPOSIT_RPC_URL` every label is verified on the same node,
so one transaction could be claimed as "base" and again as "ethereum" — a top-up and a channel, or
two channels, for one payment. Every door now claims a transaction under `eip155:<chainId>` (the
node's own `eth_chainId` when a label is overridden), under its own label (claims written before
this carry only that, and still collide), and under every configured label that names the same
chain. A claim file whose writer died before writing it is repaired after a minute; a readable
foreign claim is never overwritten.

Two top-up authorizations in one transaction — a smart wallet paying two quotes at once — each
credit their own quote: the registry entry is the top-up door's, and each authorization is spent
separately in `x402_payments`.

## Credited without anybody presenting it

On a hub whose top-up wallet is **dedicated** — `AIMARKET_TOPUP_PAY_TO` receives top-ups and
nothing else — the hub reads that wallet itself every `AIMARKET_DEPOSIT_WATCH_INTERVAL_S` (60 s),
and nobody has to present a payment:

| What arrives in the wallet | What the hub does |
|---|---|
| A payment over a quote (`transferWithAuthorization` over the quote's nonce) | Redeems it exactly as `POST /topups/{nonce}` would, once it has its confirmations. Presenting it yourself still works; it is only faster. |
| A plain transfer from a wallet **linked** to an account | Credits that account as paid credit (`topped_up_usd`), under the reference `chain:<chain>:<tx>`. |
| A plain transfer from a wallet nobody linked | Records it as **unattributed**: counted in the well-known, listed for the operator, paged by the alerter, and credited the moment its sender is linked. |

Whether a hub does this, and where to pay, is in its well-known:

```json
"topup": { "enabled": true, "pay_to": "0x63177eb5…", "...": "...",
  "deposit_watch": {
    "enabled": true, "wallet": "0x63177eb5…", "interval_s": 60,
    "link": "/ai-market/v2/account/payer-wallets",
    "link_message": "aimarket-payer-wallet/1\nhub: https://example-hub.net\naccount: <account_id>\naddress: <address>\nissued_at: <unix seconds>",
    "link_signature": "EIP-191 personal_sign by the wallet",
    "unattributed_deposits": 0 } }
```

### Linking a wallet

A plain transfer — what a person sends from an ordinary wallet app — carries no account. So once,
before or after paying, the account names the wallet it pays from, and proves it controls it: an
EIP-191 `personal_sign` by the wallet of the `link_message`, filled in with the account id, the
lower-case address and the current unix time. It is a signature, not a transaction: nothing is
spent and no gas is paid.

```bash
python3 scripts/credits_topup_pay.py link --hub $HUB --api-key-file account.key --ask
```

or by hand, with any wallet that signs messages:

```bash
curl -s -X POST $HUB/ai-market/v2/account/payer-wallets -H "X-API-Key: $KEY" -H 'Content-Type: application/json' \
     -d '{"address": "0x…", "issued_at": 1790000000, "signature": "0x…"}'
```

| Answer | When |
|---|---|
| 200, `linked` or `already`, `credited_now` | Linked. Transfers from this wallet that were waiting are credited now. |
| 400 | Not an address, or `issued_at` more than 10 minutes from the hub's clock. |
| 403 | The signature is not this wallet's over this message (another hub, account, address or time). |
| 409 | The wallet is linked to another account: one wallet pays for one account. |
| 401 | No `X-API-Key`, or one this hub does not know. |
| 503 | This hub cannot check wallet signatures (eth-account is not installed): ask the operator to link the wallet. |

`GET /ai-market/v2/account/payer-wallets` lists an account's wallets; `POST
/ai-market/v2/account/payer-wallets/unlink` with `{"address"}` removes one (credits already made
stay). For a company it knows, the operator links a wallet without a signature:
`POST /ai-market/v2/accounts/{id}/payer-wallets` with `{"address"}` and the admin token.

### Why only a dedicated wallet

The hub's x402 wallet (`AIMARKET_X402_PAY_TO`) also receives sales, a shop sharing it takes its own
payments there, and its payment-recipient wallet (`AIMARKET_PAYMENT_RECIPIENT`) receives channel
deposits. Reading every incoming transfer as a top-up would credit those twice. So the watcher runs
only when `AIMARKET_TOPUP_PAY_TO` is set explicitly, and never on either of those wallets; when it is
off, the well-known says why.

### Once, whichever door sees it first

The watcher claims a plain transfer in the same deposit registry as every other door (under
`aimarket-hub-deposit-watch`) and credits it under the same ledger reference as the operator's
hand credit. A transfer the operator already credited by hand is recorded as `credited_elsewhere`;
a hand credit after the watcher answers `409`. A quote payment goes through the redemption code
itself. A cursor in the database remembers the last block read; when the node fails, the same
blocks are read again next time. The watcher waits one interval after the hub starts.

### What happens to each transfer

Every transfer into the wallet gets its own row, and no transfer holds up the others: the hub
records it with a status and reads on. Only a node that cannot be read at all stops a scan — and
then the same blocks are read again. Each scan also re-reads the last 12 blocks (a load-balanced node
can answer from a backend a block behind) and checks every log itself: the token, the Transfer
event, the recipient, and the node's chain id.

| Status | What it means | What settles it |
|---|---|---|
| `credited` | Credited to the account the quote or the link names. | — |
| `credited_elsewhere` | Another door credited this transaction first: the operator's hand credit, a quote presented by hand, a channel. | — |
| `pending` | Not decidable yet: the quote's account is over its 24-hour limit, the node had no receipt, the registry did not answer. | The hub retries it on every scan. |
| `unattributed` | No account can be named: an unlinked wallet, several senders in one transaction, a quote payment the hub refused. | A link (one sender only), the operator's hand credit, or `POST /admin/deposits/{tx}/resolve`. |
| `ignored` | Less than a millicent ($0.00001): nothing to credit. | — |
| `resolved` | The operator settled it out of band (a refund) and said how. | — |

**Several senders in one transaction** are credited to nobody automatically — a dust transfer from a
linked wallet placed in front of somebody else's payment must not take that payment. The operator
credits the right account by hand with the `tx_hash`.

### Limits and wallets

- The minimum, maximum and 24-hour limits apply to **quotes**. A plain transfer from a linked wallet
  is credited whatever its size: the money has already arrived, and refusing to credit it would not
  send it back.
- **Smart-contract wallets** (EIP-1271: Safe, Coinbase Smart Wallet) cannot link with a signature
  (`403`): ask the operator to link them.
- Never link a **shared sender** — an exchange's hot wallet, a bridge minting from `0x0…`: every
  deposit from it, by anyone, would be credited to one account.
- Never give **two hubs one top-up wallet**: each keeps its own registry, so both would credit the
  same transfer.

## Errors

| Status | `error` | When | What to do |
|---|---|---|---|
| 401 | `api_key_required` | A quote without a valid `X-API-Key`. | Open an account (`POST /ai-market/v2/accounts`) and send its key. |
| 400 | `amount_invalid` | Not a number, or finer than a cent. | Send whole cents. |
| 400 | `amount_out_of_range` | Below the minimum or above the maximum. | Stay within `min_usd`–`max_usd` from the well-known. |
| 429 | `too_many_open_quotes` | Too many unpaid quotes on the account. | Pay one, or let them expire. |
| 429 | `daily_topup_limit` | The account bought its 24-hour maximum. | Wait, or ask the operator. |
| 503 | `topup_unavailable` | The door is shut on this hub (and why). | Read `payment_rails.credits.topup.reason`. |
| 400 | `nonce_invalid` / `tx_hash_invalid` | Malformed — or an x402 payload carrying only a signed authorization: this hub verifies and never settles. | Submit the authorization yourself and send the 0x transaction hash. |
| 404 | `topup_unknown` | No quote with that nonce here (never minted, or pruned unpaid). | Check the hub and the nonce. |
| 409 | `payment_not_final` | Not mined yet, or too few confirmations. `retryable`. | Wait a block or two and retry. |
| 402 | `payment_invalid` | The transaction does not pay this quote: no authorization over the nonce, wrong payee, reverted. The quote stays open. | Pay the quote as offered. |
| 429 | `daily_topup_limit` (at redemption) | Crediting this payment would pass the account's 24-hour limit. `retryable`; the quote stays open. | Redeem it later. |
| 409 | `topup_in_progress` | Another redemption holds the quote. | Read `GET /ai-market/v2/topups/{nonce}` and retry. |
| 409 | `topup_already_credited` | The quote was credited by another transaction. | Nothing: your account has it. |
| 409 | `payment_already_used` | The transaction was used at another door. The quote stays open. | Contact the operator with the nonce. |
| 500 | `credit_failed` | The payment verified but the credit could not be written. `retryable`. | Retry; if it persists, give the operator the nonce. |
| 429 | `too_many_attempts` | More than 12 checks in a minute from one address (anyone but the quote's owner), or from the owner's account across its quotes. | Retry in a minute, or redeem with the account's key. |
| 503 | `verifier_unavailable` / `deposit_registry_unavailable` / `payment_record_unavailable` | The chain, the registry or the payment record could not be read or written. Nothing was credited. `retryable`. | Retry. |
| 503 | `topup_unavailable` (at quote) | Also when the token's `decimals()` cannot be read, or is not what the hub prices in. | Retry, or tell the operator. |

## Operator

### Opening the door

| Variable | Default | Effect |
|---|---|---|
| `AIMARKET_TOPUP_ENABLED` | `0` | Open the top-up door. Also needs the credits rail (`AIMARKET_CREDITS_ENABLED=1`) and a USDC asset. |
| `AIMARKET_TOPUP_PAY_TO` | the hub's `AIMARKET_X402_PAY_TO` | The wallet top-ups are paid to. Set it to a wallet that receives top-ups **and nothing else**: only then does the hub watch it and credit deposits itself (below). |
| `AIMARKET_CREDITS_OPEN_SIGNUP` | `1` | Let agents open their own accounts. Closed, keys are issued by hand, and a stranger cannot buy at all. |
| `AIMARKET_SIGNUP_GRANT_USD` | `0` | Free credit a self-opened account starts with. Zero is right when credit is sold. |
| `AIMARKET_TOPUP_MIN_CONFIRMATIONS` | `2` | Confirmations before a payment is credited. |
| `AIMARKET_TOPUP_VERIFY_DECIMALS` | `1` | Read the token's `decimals()` before quoting (once per address). |
| `AIMARKET_TOPUP_MIN_USD`, `_MAX_USD`, `_DAILY_USD`, `_MAX_OPEN_QUOTES`, `_QUOTE_TTL_S`, `_RETAIN_DAYS` | see [the quote](#the-quote) | Limits. |
| `AIMARKET_SETTLE_RPC_URL` | the chain's defaults | Where payments are read (shared with seller-direct): a comma-separated list, asked in rotation; a node that refuses (HTTP 429, a block-range cap) rests. Free nodes cap per IP, so check the list from the hub's own machine with `aimarket rpc-check`. |
| `AIMARKET_DEPOSIT_WATCH` | `1` | Watch the top-up wallet (needs a dedicated `AIMARKET_TOPUP_PAY_TO`). `0` = presenting and hand credits only. |
| `AIMARKET_DEPOSIT_WATCH_INTERVAL_S` | `60` (at least 15) | How often the wallet is read. |
| `AIMARKET_DEPOSIT_WATCH_CHUNK_BLOCKS` | `500` (10–2000) | Blocks per `eth_getLogs` (public Base nodes refuse more than ~2000). |
| `AIMARKET_DEPOSIT_WATCH_PAUSE_S` | `0.3` (0–5) | Rest between windows while a scan catches up (more than 4 windows behind), so free nodes' per-IP caps do not stop it every few windows. |
| `AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS` | `1800` (~1 h on Base) | Where the very first scan starts; afterwards a cursor in the database resumes. |

The well-known says whether the door is open, and on what terms:

```json
"payment_rails": { "credits": {
  "enabled": true, "open_signup": true, "signup_url": "https://example-hub.net/ai-market/v2/accounts",
  "topup": { "enabled": true, "quote": "/ai-market/v2/account/topup", "redeem": "/ai-market/v2/topups/{nonce}",
             "binding": "eip3009", "asset": "USDC", "network": "eip155:8453", "pay_to": "0x7099…",
             "min_usd": 1.0, "max_usd": 100.0, "daily_usd": 500.0, "min_confirmations": 2, "quote_ttl_s": 900 }
} }
```

Shut, `topup` carries `"enabled": false` and a `reason`. A 402 on an invoke names the door too,
next to the signup URL.

### Refunds

Credit is prepaid service. Nothing refunds it automatically; unspent credit is returned, or not,
under the operator's own terms, by paying it back on chain and debiting the account.

### Recovering a payment the hub cannot credit

A plain transfer, or an authorization over a nonce this hub never minted, reaches the operator's
wallet but cannot be matched to an account. The operator credits it by hand, naming the
transaction:

```bash
curl -s -X POST $HUB/ai-market/v2/accounts/$ACCOUNT_ID/credit -H "Authorization: Bearer $ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d "{\"amount_usd\": 5, \"tx_hash\": \"$TX\", \"note\": \"plain transfer\"}"
```

With `tx_hash` the account is checked first (a mistyped id answers `404` and claims nothing), the
credit is **paid** credit (`topped_up_usd`, not a grant), idempotent on the transaction, and the
transaction is claimed in the same registry every door uses — so it can then
neither fund a channel, nor be credited to a second account, nor be redeemed through a quote
(`409`). A payment made over a quote's nonce is better redeemed than credited by hand: anyone can
redeem it, and the quote then records it.

On a hub that watches its wallet, link the sender instead
(`POST /ai-market/v2/accounts/{id}/payer-wallets`): the waiting transfer is credited at once, and
every later one from that wallet by itself.

### Watching it

- `topup: credited $… to acct_… for 0x… (tx 0x…, payer 0x…)` at WARNING — every credit.
- `topup: … was already used at another door` at ERROR — a transaction presented to two doors.
- `stats.credits.topped_up_usd` against the operator wallet's balance on chain.
- `GET /ai-market/v2/account/topups` — an account's own history; `GET /ai-market/v2/topups/{nonce}` — one quote.
- `deposit watch: credited $… to acct_… (plain transfer 0x… from 0x…)` at WARNING — every plain transfer credited.
- `GET /ai-market/v2/admin/deposits` (admin token) — unattributed and pending deposits (sender, amount, transaction, why) and the watcher's state; `POST /ai-market/v2/admin/deposits/{tx}/resolve` with `{"note"}` closes one settled out of band.
- `payment_rails.credits.topup.deposit_watch.last_scan_at` — when the wallet was last read; a watcher that stopped reading pages even while it says `enabled`.
- `payment_rails.credits.topup.deposit_watch.unattributed_deposits` above zero — the ecosystem alerter pages
  (`deposits_unattributed:<hub>`), and `deposit_watch_on:<hub>` when a hub that should watch does not.

### Tables

Migration `041_credit_topup_quotes` adds `credit_topup_quotes` (the nonce, the account, the exact
amount in token units, payee, token, chain, expiry, status, transaction, payer, the units that
arrived, credited millicents, ledger reference, and `credited_at` as epoch seconds — the daily limit
compares a number, which reads the same on SQLite and PostgreSQL) and `credit_accounts.topped_up_mc`. No payment secret is stored:
nothing here needs one.

## How it is tested

| What | Where |
|---|---|
| The 402 (both forms), amounts, limits, the door shut by default, the well-known | `tests/test_topup.py::TestQuote` |
| Crediting once, replays, the x402 retry, a payment presented by someone else crediting the quote's owner, an overpayment capped at the quote, an underpayment credited for what arrived, payments that do not verify staying redeemable, an unbound transfer refused, rate limit, disabled accounts | `tests/test_topup.py::TestRedeem` |
| The channel door and the top-up door sharing one claim, a registry entry still being written retried rather than refused, two authorizations in one transaction, racing redemptions, a redemption interrupted before and after the credit, pruning, a top-up nonce refused by an invoke | `tests/test_topup.py::TestExclusivity` |
| An operator crediting an on-chain payment by hand: paid credit, idempotent, the transaction then refused to a second account, to the channel door and to a quote | `tests/test_topup.py::TestOperatorCredit` |
| Each defect the independent review confirmed: the hub-local registry, one claim whatever chain label a door uses, a failed payment record retried not refused, a half-written deposit leaving nothing, the daily limit at redemption, anonymous checks not locking the owner out, a claim whose writer died, a slow chain not stalling other requests, the token's decimals, an operator credit to an unknown account, an authorization-only x402 payload | `tests/test_topup.py::TestReviewFindings` |
| A stranger opening an account, buying 5 USDC of credit on a local anvil chain with a real EIP-3009 token contract, and spending it; a plain transfer refused; a short authorization credited for what arrived | `tests/test_topup_chain.py` |
| The SDK's typed data and calldata, byte-for-byte against `cast calldata` | `aimarket-agent/tests/test_topup.py` |

Every suite above passes on SQLite and on PostgreSQL (`AIMARKET_TEST_DATABASE_URL`).

`tests/test_topup_chain.py` runs anvil with Base's chain id and UniUSD
(`contracts/evm/src/UniUSD.sol`, the UNI bubble's USDC). Writing it found that UniUSD logged its
authorization as `AuthorizationUsedEvent` — a different topic from USDC's `AuthorizationUsed`, so
no EIP-3009 payment inside the bubble could ever have been verified. The event is now named as
USDC names it, and `contracts/evm/test/UniUSD.t.sol` pins the topic.

## Rules that are easy to miss

- **Pay with `transferWithAuthorization` over the quote's nonce.** A plain transfer is not credited
  automatically.
- **You send the transaction and pay the gas.** The hub has no key.
- **A paid quote does not expire**; an unpaid one is pruned after the retention period.
- **Redeem from anywhere.** The credit goes to the quoted account whoever presents the payment.
- **Wait for confirmations.** `payment_not_final` is a "later", not a "no".
- **What arrived is credited, up to the quote**, rounded down to the millicent; an overpayment is
  reported for the operator to refund.
- **One transaction, one credit** — across the top-up door and the channel-deposit door.
- **Credit is prepaid service**, not a deposit that earns or a balance that refunds itself.

See also: [subcontracting.md](subcontracting.md) · [mandates.md](mandates.md) · [a2a.md](a2a.md) ·
[money-rails.md](money-rails.md) · [the market rail](https://github.com/alexar76/aicom/blob/main/docs/hestia-hub-market-rail.md) ·
[glossary](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)
