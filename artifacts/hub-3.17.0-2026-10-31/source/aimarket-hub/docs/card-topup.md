# Buying credits with a card (Stripe Checkout)

> **Русский:** [card-topup.ru.md](./card-topup.ru.md) · **Español:** [card-topup.es.md](./card-topup.es.md) · **Français:** [card-topup.fr.md](./card-topup.fr.md) · **中文:** [card-topup.zh.md](./card-topup.zh.md)
>
> Code: [`card_topup.py`](../aimarket_hub/card_topup.py) · routes in [`hub_routes/accounts.py`](../aimarket_hub/hub_routes/accounts.py) · [`credits.py`](../aimarket_hub/credits.py) (`deposit`) · tests [`test_card_topup.py`](../tests/test_card_topup.py)

[USDC top-ups](credits-topup.md) let an agent with a wallet fund its credit account. A person
with a card and no wallet could not. This door takes a card the way any shop does and lands the
money on the **same** ledger line a USDC top-up does (`CreditsLedger.deposit`, kind `topup`), so
everything on the credits rail — paid invokes, [mandates](mandates.md), subcontracting, A2A — works
the same afterwards.

**Status.** Available since 2026-10-20 (3.16.0), **off by default**. Verified against the official Stripe sandbox on 2026-10-20–21: payments without tax, a Managed Payments payment with nonzero VAT, full refunds with and without tax, and a dispute. The exact coverage and remaining gaps are below. No real money moved.

<a id="sandbox-verification"></a>
## Verified in the official Stripe sandbox

These checks used Stripe-hosted Checkout, test cards, real Stripe API responses and signed events forwarded by the official Stripe CLI to an isolated local hub. They are separate from unit tests that mock Stripe at the HTTP boundary. [Recorded evidence](evidence/stripe-sandbox-2026-10-21.json) contains amounts, event IDs, delivery outcomes and ledger checks; timestamps in the evidence are UTC.

| Scenario | Observed result |
|---|---|
| `off`: payment without tax | $5 paid, $5 credited exactly once through `checkout.session.completed`; redelivery did not add credit. |
| `stripe_tax` | Checkout creation/opening was checked in the sandbox. Payment, nonzero tax, refund and dispute in this mode have **not** been verified. |
| `managed_payments` + `exclusive` | Test buyer in the Netherlands: $5 subtotal + $1.05 VAT (21%) = $6.05 USD; `paid`, tax calculation `complete`, liability `stripe`. The hub's `refresh` credited exactly $5 once. The initial payment webhook was not exercised in that run. |
| Full refund with tax | Stripe API returned `succeeded` for $6.05, including the $1.05 tax. Signed `charge.refunded` returned HTTP 200 and changed the hub status to `refunded`. This was an operator-requested refund, not an automatic refund initiated by Stripe. |
| Full refund without tax (`off`) | $5 returned with `succeeded`; signed `charge.refunded` returned HTTP 200 and changed the hub status to `refunded`. |
| Dispute without tax (`off`) | Card `4000 0000 0000 0259` produced a real sandbox dispute for $5, reason `fraudulent`, Stripe status `needs_response`; `charge.dispute.created` set the hub status to `disputed`. |
| Repeated and delayed events | Stripe redelivered payment, refund and dispute events. Final `refunded`/`disputed` statuses survived late payment events, each account retained one $5 `topup` ledger entry, and no replay added credit. |
| `inclusive` tax | Amount validation is covered by local tests; an actual paid sandbox checkout and its refund are **not** verified. |

**An ordering bug found and fixed.** In the first dispute run, Stripe delivered the dispute before the payment completion; the old handler acknowledged it as `ignored`. The handler now finds the Checkout Session by PaymentIntent, verifies its association with a local top-up and reconciles it under the row's original tax mode before recording the reversal. Lookup failures return a retryable error. A real refund was then deliberately delivered before its payment event: it was recorded correctly, and Stripe's later redelivery of the payment event preserved `refunded`. The early-dispute order is also covered by a regression test; replay recovered the first dispute, and a new payment/dispute run passed. Session and amount checks still apply.

**Historical balance policy (before 2026-10-25):** these sandbox runs recorded reversals without freezing the account. Current code preserves the balance but freezes new spending until operator review, as described below. The new freeze and upgrade behavior is covered by local SQLite and PostgreSQL regression tests; it has not been rerun against Stripe's official sandbox.

**Not verified in the official sandbox:** partial refunds, asynchronous failed refunds, winning/losing a dispute, disputes under Managed Payments, or paid/refunded `stripe_tax` and `inclusive` checkouts. Sandbox success does not establish production eligibility for Managed Payments. The production mode remains the operator's decision.

References: [Stripe test cards and disputes](https://docs.stripe.com/testing#disputes), [refund API](https://docs.stripe.com/api/refunds/create), [Checkout Session lookup by PaymentIntent](https://docs.stripe.com/api/checkout/sessions/list).

## Contents

- [Verified in the official Stripe sandbox](#sandbox-verification)
- [The short version](#the-short-version)
- [What the buyer sees](#what-the-buyer-sees)
- [What the hub checks](#what-the-hub-checks)
- [Sales tax: three modes](#sales-tax-three-modes)
- [A webhook that never arrived](#a-webhook-that-never-arrived)
- [Refunds and disputes](#refunds-and-disputes)
- [Limits](#limits)
- [What this door does not do](#what-this-door-does-not-do)
- [Operator](#operator)
- [Testing in the Stripe sandbox, step by step](#testing-in-the-stripe-sandbox-step-by-step)

## The short version

```bash
# 1. Open a checkout for $10 of credit on your account.
curl -s -X POST $HUB/ai-market/v2/account/topup/card -H "X-API-Key: $KEY" \
     -H 'Content-Type: application/json' -d '{"amount_usd": 10}'
# → 201 {"topup_id": "ctp_…", "checkout_url": "https://checkout.stripe.com/…", "status": "open",
#        "amount_usd": 10, "charge_usd": 10, "fee_usd": 0, "expires_at": "…", "status_url": "…"}

# 2. A person opens checkout_url and pays. Stripe sends them back to status_url.

# 3. The credit lands when Stripe confirms; read where it stands any time:
curl -s $HUB/ai-market/v2/card-topups/ctp_…
```

An agent cannot pay by card itself: it hands `checkout_url` to its human and waits (or polls the
status). That is the point of this door — the human pays, the agent spends within its
[mandate](mandates.md).

## What the buyer sees

A Stripe-hosted page (`checkout.stripe.com`) with one line: "Prepaid credit on <hub host>: $10.00"
(plus "incl. $x card fee" when the operator sets one). With a tax mode on, the page also asks for a
billing address and shows the tax; under Managed Payments Stripe's own terms and seller name
appear. The page expires after **one hour**; a new checkout is one request away. After paying,
Stripe sends the buyer to `status_url`, which answers JSON with the top-up's status.

No card number ever reaches the hub — it never sees one. PCI scope stays with Stripe.

## What the hub checks

Stripe calls `POST /ai-market/v2/stripe/webhook`. Before anything in the event is read, the
`Stripe-Signature` must verify: HMAC-SHA256 over `t.payload` with the endpoint secret, `t` within
five minutes, constant-time comparison (several `v1` signatures are accepted while a secret is
being rolled). Then the session in the event is checked against the row the hub opened — never
the other way round:

| Check | Why |
|---|---|
| the top-up id is one this hub opened | an event names a top-up; it cannot create one |
| the session id equals the one Stripe gave when the hub opened it | a paid session of some other checkout cannot be presented for this one |
| `payment_status == "paid"` | a completed but unpaid (async) session credits nothing yet |
| `currency == "usd"` and the amounts match the charge the hub asked for, under the tax mode the checkout was opened with ([below](#sales-tax-three-modes)) | the amount and the account are the hub's, not the event's |
| with a live key (`sk_live_…`, `rk_live_…`), the session is `livemode` | test money never credits a live hub |

The credit goes to the account bound when the checkout was opened, for the amount of credit asked
for. A card fee and any tax are not credited. The ledger line is referenced by the session id, so a
redelivered event — or two deliveries racing — credits once. Stripe learns the top-up id, never
the account.

Events about anything else are acknowledged (`200`) and ignored, so Stripe does not retry them for
days. `checkout.session.expired` closes the row.

## Sales tax: three modes

Who computes and owes the sales tax (VAT, GST, US sales tax) is the operator's decision. It is one
setting, `AIMARKET_CARD_TOPUP_TAX`, and the hub keeps the mode **on each checkout's row**: a
checkout opened under one mode is checked under that mode even if the operator changes the
setting before it is paid.

| Mode | Who is the seller | Who computes the tax | Who files and pays it | Stripe fee on top of card fees |
|---|---|---|---|---|
| `off` (default) | the operator | nobody, in Stripe | the operator, outside Stripe | — |
| `stripe_tax` | the operator | Stripe Tax, from the buyer's billing address | the operator (Stripe Tax reports what to file) | Stripe Tax pricing |
| `managed_payments` | **Stripe** (merchant of record) | Stripe | Stripe | 3.5 % per transaction |

**What changes in the checkout the hub opens:**

| Mode | Extra Checkout Session parameters | API version |
|---|---|---|
| `off` | none | `2024-06-20` |
| `stripe_tax` | `automatic_tax[enabled]=true`, `billing_address_collection=required`, `price_data[tax_behavior]`, `product_data[tax_code]` | `2024-06-20` |
| `managed_payments` | `managed_payments[enabled]=true`, `price_data[tax_behavior]`, `product_data[tax_code]`. Not `automatic_tax`, `billing_address_collection` or payment-method parameters: Stripe refuses them next to Managed Payments, because it collects the address and chooses the methods itself. | `2025-03-31.basil` (the oldest that has Managed Payments); the hub also reads such a checkout back under it |

**Tax on top or inside.** `AIMARKET_CARD_TOPUP_TAX_BEHAVIOR`:

- `exclusive` (default) — tax is added on top. A $10 top-up for a buyer in a country with 21 % VAT
  costs the buyer $12.10; the hub checks that the session's `amount_subtotal` is exactly $10 and
  that `amount_total` is exactly `amount_subtotal + total_details.amount_tax` — no discount, no
  other line may move it. $10 of credit is credited; the $2.10 is recorded on the row as
  `tax_usd`.
- `inclusive` — tax is inside the price. The buyer pays $10, the tax is part of it, the operator
  receives less; the hub checks `amount_total` is exactly $10 and that the tax is not negative.
  $10 of credit is credited.

**The product tax code** — `AIMARKET_CARD_TOPUP_TAX_CODE`, default `txcd_10000000` ("General —
Electronically Supplied Services"). For an AI capability marketplace `txcd_10105002` ("Artificial
Intelligence as a Service — cloud based — business use") or `txcd_10701410` ("Electronically
delivered information services — business use") may fit better; the right code is a question
for the operator's accountant. Under Managed Payments the code must be one Stripe lists as eligible.

**A setting the hub does not understand shuts the door** rather than opening checkouts under a
guess: an unknown mode, a tax code that is not `txcd_` + 8 digits, or a behavior other than
`exclusive`/`inclusive` makes the well-known say `"enabled": false` with the reason.

**What the buyer and the well-known see.** `payment_rails.credits.topup_card.tax` is
`{"mode": "off"}`, or `{"mode", "behavior", "seller_of_record": "operator" | "stripe"}`. A top-up's
status carries `tax: {mode, behavior, tax_usd}` once paid.

### Managed Payments: read before switching it on

Stripe decides who may use it, and its conditions matter here:

- **Direct sales only.** Stripe's eligibility page says the product must be sold "directly to
  customers, not through a platform or marketplace". The hub is a marketplace: credit bought here
  is spent on capabilities of independent providers. Whether Stripe accepts prepaid credit on a
  marketplace under Managed Payments is Stripe's call — ask Stripe before relying on it.
- **Digital, automated products only**, with an eligible tax code; business location in a
  supported country (the EU countries, the UK, Switzerland, Norway, the US, Canada, Australia, Hong
  Kong, Japan, Singapore are listed).
- **Stripe may refund** a purchase within 60 days to prevent a chargeback, and applies consumer
  cooling-off rules. Each refund reaches the hub as `charge.refunded` ([below](#refunds-and-disputes)).
- Switch it on in the Dashboard (Settings → Managed Payments) before setting the mode, or Stripe
  refuses to open the checkout (`502 stripe_refused`, nothing charged).

### Stripe Tax: before switching it on

In the Dashboard: Tax → settings (the origin address, the default tax code) and **registrations**
— Stripe Tax collects tax only where the operator is registered. Without a registration for the
buyer's country the tax is zero, which the hub accepts (`amount_tax: 0`).

## A webhook that never arrived

`POST /ai-market/v2/card-topups/{id}/refresh` asks Stripe for the session and runs the same checks.
Anyone holding the id may call it (rate-limited per caller): it can only credit the account the
checkout was bound to. A paid top-up is therefore never stranded by a lost delivery.

## Refunds and disputes

- **`charge.refunded`** — a refund made in Stripe (by the operator, or by Stripe itself under
  Managed Payments) marks the top-up `refunded` and disables new credit spending on its account.
- **`charge.dispute.created`** — a chargeback marks the top-up `disputed` and applies the same
  spending freeze. Both changes and a zero-amount `review_freeze` ledger entry commit together.

The freeze covers API-key invokes, mandates and new subcontract spending from existing
allowances. Balances are preserved; calls already reserved may complete or release their
holds. A trusted operator reconciles the refund/dispute, then may reactivate the account
through the existing admin-only `POST /accounts/{id}/status` route. Duplicate events do not
undo that review. The hub does not issue a refund or confiscate credit automatically.

Migration 062 applies this review freeze once to accounts with historical `refunded` or
`disputed` top-ups. It preserves their balances and reservations. Normal restarts after
operator reactivation do not freeze the account again; rolling back the migration does not
reactivate an account automatically.

## Limits

| Variable | Default | Effect |
|---|---|---|
| `AIMARKET_CARD_TOPUP_MIN_USD` | `5` | Smallest top-up (never under Stripe's $0.50). |
| `AIMARKET_CARD_TOPUP_MAX_USD` | `100` | Largest single top-up. |
| `AIMARKET_CARD_TOPUP_DAILY_USD` | `200` | Most one account may buy by card in 24 hours. Open checkouts count until they expire (1 hour), since any of them may still be paid; a refunded or disputed top-up keeps counting, since its credit stays on the account. Checkouts opened at the same instant are checked against each other: they cannot together pass the limit. |
| `AIMARKET_CARD_TOPUP_FEE_PCT` | `0` | A surcharge in percent, shown before paying and not credited. `0`: the operator absorbs the card fee. Where surcharging cards is restricted, keep `0`. |
| `AIMARKET_CARD_TOPUP_FEE_FIXED_USD` | `0` | A fixed surcharge per checkout. |
| `AIMARKET_CARD_TOPUP_TAX` | `off` | `off`, `stripe_tax` or `managed_payments` ([above](#sales-tax-three-modes)). |
| `AIMARKET_CARD_TOPUP_TAX_BEHAVIOR` | `exclusive` | `exclusive` (on top) or `inclusive` (inside the price). |
| `AIMARKET_CARD_TOPUP_TAX_CODE` | `txcd_10000000` | The Stripe product tax code. |

The daily limit is what bounds a stolen card: a dispute arrives after the credit may have been
spent, and the hub cannot recall spent credit.

## What this door does not do

- **Take credit back** after a refund or a dispute — recorded and logged, corrected by hand.
- **Issue invoices.** Stripe sends its own receipt to the payer's e-mail if the Stripe account is
  set to (under Managed Payments, always). A legal invoice in the operator's name, and how the
  sale is booked, are the operator's business and depend on its jurisdiction.

## Operator

### Opening the door

1. A Stripe account in the operator's name. Its **country cannot be changed later**; for real money
   it must be the country of the legal entity that receives the payouts.
2. A **restricted key** with one permission, *Checkout Sessions: Write* (Developers → API keys →
   Create restricted key → Custom permissions). It is all the hub needs: create a checkout and read
   it back. Put it in `AIMARKET_STRIPE_SECRET_KEY_FILE` (a docker secret), or
   `AIMARKET_STRIPE_SECRET_KEY`.
3. A webhook endpoint in the Dashboard: `https://<hub>/ai-market/v2/stripe/webhook`, events
   `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
   `checkout.session.expired`, `charge.dispute.created`, `charge.refunded`. Its signing secret goes
   in `AIMARKET_STRIPE_WEBHOOK_SECRET_FILE` (or `AIMARKET_STRIPE_WEBHOOK_SECRET`).
4. `AIMARKET_CARD_TOPUP_ENABLED=1`; the credits rail must be on (`AIMARKET_CREDITS_ENABLED=1`).
5. Optionally a tax mode (`AIMARKET_CARD_TOPUP_TAX`) after the Dashboard steps of that mode.

The shared service environment filter forwards only the hub's `AIMARKET_STRIPE_*`
credentials. It rejects unscoped `STRIPE_*` names to keep the Factory's merchant account
out of the hub. Standalone deployments still accept those legacy names when no scoped
name is configured. An explicitly empty scoped value or an unreadable scoped secret
file keeps the card door closed; it never falls back to a different merchant.

The well-known says whether the door is open and why not:
`payment_rails.credits.topup_card` = `{"enabled", "provider": "stripe-checkout", "create",
"status", "currency", "min_usd", "max_usd", "daily_usd", "fee_pct", "fee_fixed_usd", "tax"}` or
`{"enabled": false, "reason": "…"}`.

### Routes

| Route | Who | What |
|---|---|---|
| `POST /ai-market/v2/account/topup/card` | the account's `X-API-Key` | open a checkout (`{"amount_usd"}`) → `201` with `checkout_url`; 6 per minute per account |
| `GET /ai-market/v2/card-topups/{id}` | anyone with the id | status; the account only to its own key |
| `POST /ai-market/v2/card-topups/{id}/refresh` | anyone with the id | reconcile with Stripe, credit if paid |
| `POST /ai-market/v2/stripe/webhook` | Stripe (signed) | events |
| `GET /ai-market/v2/account/topups` | the account's key | lists `card_topups` beside the USDC `topups` |

### Errors

| Status | `error` | Meaning |
|---|---|---|
| 400 | `amount_invalid`, `amount_out_of_range` | not whole cents, or outside min/max |
| 400 | `signature_invalid` | the webhook's signature does not verify (nothing is read) |
| 401 | `api_key_required` | no or unknown `X-API-Key` |
| 429 | `daily_topup_limit`, `too_many_attempts` | over the daily limit (open checkouts count), or too many checkouts a minute |
| 502 | `stripe_refused` | Stripe would not open the checkout (for instance Managed Payments not switched on, or a missing key permission); nothing was charged |
| 503 | `card_topup_unavailable`, `stripe_unavailable` | the door is shut (the reason says why), or Stripe could not be reached |

The webhook answers `{"received": true, "outcome": …}`: `credited`, `already_credited`, `pending`,
`refused` (figures do not match — logged as an error, nothing credited), `expired`, `disputed`,
`refunded` or `ignored`.

### Table

`card_topups` (migrations 056 and 057): one row per checkout — `topup_id`, `account_id`,
`amount_cents` (credit), `charge_cents` (what the card pays before tax), `status` (`new` → `open` →
`credited` / `expired` / `failed` / `disputed` / `refunded`), `session_id`, `payment_intent`,
`livemode`, `credited_mc`, `tax_mode`, `tax_behavior`, `tax_cents`, timestamps.

## Testing in the Stripe sandbox, step by step

This is how the door was proven on 2026-10-20; repeat it before going live and after changing the
tax mode. Nothing here moves real money.

1. **A sandbox.** Sign up at stripe.com; skip every activation step (documents, bank account). In
   the Dashboard open the sandbox (a "Sandbox" banner at the top).
2. **A restricted key** with *Checkout Sessions: Write* only. Copy it and save it straight from the
   clipboard, so it is never pasted into a chat or a terminal: `pbpaste > ~/.aimarket-stripe-test-key && chmod 600 ~/.aimarket-stripe-test-key`.
3. **The Stripe CLI**, to bring the sandbox's events to a hub on your machine. If Homebrew
   refuses (outdated Command Line Tools), take the macOS build from the official GitHub
   releases and check its checksum against `stripe-mac-checksums.txt`. Then `stripe login` and
   choose the **sandbox** (not the live account, not the legacy "Test mode").
4. **The webhook secret** the CLI uses: `stripe listen --print-secret > ~/.aimarket-stripe-whsec`.
5. **A local hub** with `AIMARKET_CREDITS_ENABLED=1 AIMARKET_CARD_TOPUP_ENABLED=1
   STRIPE_SECRET_KEY_FILE=~/.aimarket-stripe-test-key STRIPE_WEBHOOK_SECRET_FILE=~/.aimarket-stripe-whsec`
   (and the tax mode under test).
6. **Forward events:** `stripe listen --forward-to http://127.0.0.1:<port>/ai-market/v2/stripe/webhook
   --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.expired,charge.dispute.created,charge.refunded`.
   `stripe trigger checkout.session.completed` must show `[200]`: the signature verified (a wrong
   secret shows `[400]`).
7. **A checkout:** `POST /ai-market/v2/account/topup/card {"amount_usd": 5}` with an account key;
   a person opens `checkout_url` and pays with `4242 4242 4242 4242`, any future date, any CVC.
8. **Check:** the CLI shows `checkout.session.completed` → `[200]`; the top-up is `credited`; the
   account's ledger has exactly one `topup` line for it. Then `stripe events resend <evt_…>`: `[200]`
   again, and the balance does not move.
9. **Optional:** a dispute with the card `4000 0000 0000 0259` → the top-up turns `disputed`; a
   refund made in the Dashboard → `refunded`.
