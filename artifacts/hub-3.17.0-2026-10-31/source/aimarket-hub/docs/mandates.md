# Mandates, subcontracting and receipt anchoring

> **Русский:** [mandates.ru.md](./mandates.ru.md) · **Español:** [mandates.es.md](./mandates.es.md) · **Français:** [mandates.fr.md](./mandates.fr.md) · **中文:** [mandates.zh.md](./mandates.zh.md)
>
> Code: [`mandates.py`](../aimarket_hub/mandates.py) · [`subcontract.py`](../aimarket_hub/subcontract.py) · [`invoke_funding.py`](../aimarket_hub/invoke_funding.py) · [`anchoring.py`](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/aimarket_provenance/anchoring.py)

The normative text is [`aimarket-protocol/mandates.md`](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)
(AMD/1 for mandates, SUB/1 for subcontracting). This page is how to run and use it on this hub.

## What each piece is for

| Piece | Question it answers | Code |
|---|---|---|
| **Mandate** | "Who authorised this spend, up to how much, on what?" An owner signs limits for an agent key; the hub enforces them. The agent never holds the owner's API key. | `aimarket_hub/mandates.py` |
| **Subcontracting** | "This provider bought from another provider while serving me — on whose money, and where is it on my bill?" | `aimarket_hub/subcontract.py` |
| **Funding layer** | Decides who pays and under whose limits before the payment path runs; settles what it opened afterwards. | `aimarket_hub/invoke_funding.py` |
| **Anchoring** | "Can the hub later deny or backdate a receipt?" Each work receipt's digest goes into HISTOR's public receipts log. | `plugins/aimarket-provenance/aimarket_provenance/anchoring.py` |

All three money-facing pieces sit on the **credits rail** — the only rail on which the hub
meters money itself. A mandate or an allowance never rides along with a channel, an x402
payment or a sandbox visitor id: the hub refuses that combination (`400 mandate_rail_unsupported`,
or `403 job_invalid` for a grant) rather than enforcing a limit it cannot see.

## Money limits and the expiry boundary

- `perCall` limits the amount reserved for one call, including a routing fee when applicable. `perDay` uses a **UTC calendar day**, not a rolling 24-hour window; `total` is the optional lifetime budget. These are monetary limits, not request counts, and there is no built-in per-hour monetary limit.
- A mandate is usable only while `validFrom <= now < validUntil`, throughout its ancestor chain. At **exactly `validUntil` it is already expired**. This ends authorization for new work; it is not a deadline promising cancellation or an on-chain refund of work already started.
- Set `require_mandate=True` when linking the funding account's owner. Registering a mandate alone does not stop someone holding the raw API key from spending outside it. IP/session request-rate limiting is not a per-key spending budget.
- The underlying prepaid balance and API key have no automatic TTL. Reservation recovery and internal credit returns follow the [credit lifecycle](credits-topup.md#credit-lifecycle); they are not cash payouts or escrow-contract guarantees.

## Owner: fund an agent without handing it your key

```python
from aimarket_agent import AgentKey, issue_mandate, owner_link_payload
import httpx

HUB = "https://modelmarket.dev"                      # this hub's AIMARKET_HUB_URL, exactly
owner = AgentKey.from_seed_hex(OWNER_SEED_HEX)       # keep this offline
agent = AgentKey.generate()                          # this one goes to the agent

# 0. The account id your API key names.
ACCOUNT_ID = httpx.get(f"{HUB}/ai-market/v2/mandates/owners",
                       headers={"X-API-Key": API_KEY}).json()["account_id"]

# 1. Link your DID to your credit account (once). The API key proves the account, the
#    signature proves the key. require_mandate=True makes the raw API key stop paying.
httpx.post(f"{HUB}/ai-market/v2/mandates/owners", headers={"X-API-Key": API_KEY},
           json=owner_link_payload(owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=True))

# 2. Issue and register a mandate for the agent key.
doc = issue_mandate(owner, agent.did, audience=[HUB], scope=["gaia.*", "atlas.nearest.read@v1"],
                    per_call_usd=0.02, per_day_usd=1.00, total_usd=10.00, valid_days=30)
reg = httpx.post(f"{HUB}/ai-market/v2/mandates", json=doc).json()
# {"digest": "sha256-…", "status": "active", "root": "sha256-…", "root_issuer": "did:key:…", "depth": 0, …}
```

To let the agent open subcontracting allowances, add `subcontract_allowance_usd=` and
`subcontract_max_depth=` (1–3) to `issue_mandate`; without them the mandate cannot pay for one.

### What registration refuses

`POST /ai-market/v2/mandates` needs no key: the document authenticates itself. The hub checks
the field rules of the spec (§3.2) and the proof, and then refuses:

| Answer | When |
|---|---|
| `403 mandate_invalid` "this mandate is not addressed to …" | `audience` does not contain this hub's `AIMARKET_HUB_URL` exactly — scheme, host, port and path (a hub mounted under `/hub` is `https://example.net/hub`), no trailing slash. The hub would never serve such a mandate, so it does not store it. `mandates.audience` in `/.well-known/ai-market.json` is the string to use. |
| `402 mandate_unfunded` | The chain's root issuer is not linked to an account on this hub (step 1). |
| `403 mandate_invalid` "register the parent mandate first" | A re-delegation whose parent is not registered here. |
| `403 mandate_invalid` "… already registered a different mandate with id …" | The issuer already registered another document with the same `id`. One credential id names one mandate per issuer; issue the new one with a fresh `id` (`issue_mandate` makes a `urn:uuid:` unless you pass `mandate_id=`). |
| `403 mandate_invalid` "the mandate has already expired" | `now >= validUntil` (the end is exclusive). A mandate whose `validFrom` is still ahead registers, and reads as `pending`. |
| `403 mandate_invalid` "numbers in a mandate must be integers" | A float anywhere, or an integer outside ±(2^53 − 1). Amounts are integer µUSD. |
| `400 mandate_malformed` | The body is not a JSON object, has no canonical form, or its canonical form exceeds 16 KiB. |
| `413 mandate_malformed` | The raw body exceeds 20 KiB. |

Re-posting a document that is already registered returns the same answer — registration is
idempotent by digest (`status` reads `revoked` if it has been revoked since).

**The proof key rule.** The `proof` object must carry exactly `@context`, `type`, `cryptosuite`,
`created`, `verificationMethod`, `proofPurpose` and `proofValue`, and `proof.@context` must equal
the document's `@context`. The reason: the digest that names a mandate is taken over the whole
secured document, proof included, but `eddsa-jcs-2022` hashes the proof configuration with the
*document's* `@context` in place of the proof's own, so `proof.@context` is not covered by the
signature. Left free, it would let the agent a mandate constrains re-spell the document and
register copy after copy — each a new digest with fresh limit counters, none touched by revoking
the original. `issue_mandate` and ARGUS's signer produce exactly this shape. A mandate registered
before the rule whose proof breaks it is re-checked whenever the hub reads it, and now reports
`invalid`.

### Owners and `require_mandate`

Only the **first** owner of an account is linked with the API key alone. After that, adding a
second DID, unlinking one or changing `require_mandate` also needs an existing owner's signature —
the API key is what leaks, so it must not be enough to undo the protection:

```python
from aimarket_agent import owner_unlink_payload

# another owner (key rotation), authorised by an existing one
owner_link_payload(new_owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=True,
                   authorized_by=owner)
# switch require_mandate off for a DID that is already linked: a policy change
owner_link_payload(owner, hub_origin=HUB, account_id=ACCOUNT_ID, require_mandate=False,
                   authorized_by=owner, action="policy")
# unlink — body of POST /ai-market/v2/mandates/owners/unlink
owner_unlink_payload(old_owner.did, hub_origin=HUB, account_id=ACCOUNT_ID, authorized_by=owner)
```

Each goes with the account's `X-API-Key`. A change without a valid owner signature answers
`403 owner_authorization_required`; a DID already linked to another account answers
`409 owner_linked_elsewhere`. `require_mandate` is kept per linked DID, and the account is locked
while **any** of its DIDs has it on — switching it off takes a policy change for each such DID.
`GET /ai-market/v2/mandates/owners` (with the API key) lists the linked DIDs and their
`require_mandate`. An owner who has lost every key is recovered by the operator: the same call
with `Authorization: Bearer $AIMARKET_ADMIN_TOKEN` (and the API key) stands in for the owner's
signature.

With `require_mandate` on, the API key alone no longer moves the balance:

- a plain invoke answers `402 mandate_required`, and so does one that asks for a subcontracting
  allowance without a mandate;
- a credit-funded stake (`POST /ai-market/v2/supply/stake` with the API key and a positive
  `amount_usd`) answers `403`: a stake would not pay a thief, but it would freeze the balance as
  collateral and expose it to slashing.

A child call paid from a job's grant is not affected: its money was authorised on the root call.

### Revocation

Revoke with `POST /ai-market/v2/mandates/revoke` — signed by any issuer in the chain
(`revoke_payload(owner, hub_origin=HUB, digest=digest)`), or with just `{"digest"}` and the funding
account's `X-API-Key` as a kill switch. Revoking a mandate revokes everything re-delegated from it.
Holds already taken settle normally.

### Owner approval above a threshold

Add `approvalAbove` (µUSD) to a mandate's `limits` and any single call that would cost more
waits for you instead of spending ([spec §5.6](https://github.com/alexar76/aimarket-protocol/blob/main/mandates.md)). Small
calls keep running unattended; a big one needs your signature on **that** call.

```python
from aimarket_agent import approval_payload, issue_mandate

doc = issue_mandate(owner, agent.did, audience=[HUB], scope=["*"],
                    per_call_usd=50, per_day_usd=100, approval_above_usd=10)   # aimarket-agent ≥ 2.6.0
```

1. The agent's call over the threshold answers `402 approval_required` with an `approval`
   block: `approval_id`, `capability_id`, `amount_usd`, `max_usd` (the ceiling you approve; a
   routed call includes the routing fee), `body_sha256` (the exact request), `expires_at`
   (24 h) and `url`. Nothing is reserved. Asking again before you answer returns the same request.
   A call that another of the mandate's limits (`perCall`, `perDay`, `total`, a product's daily
   limit) would refuse anyway is refused at once with `402 mandate_limit` — you are never asked
   to sign what could not run.
2. You see what waits: `GET /ai-market/v2/mandates/approvals?status=pending` with the funding
   account's `X-API-Key`.
3. You answer: `POST /ai-market/v2/mandates/approvals/{approval_id}` with
   `{"decision": "approve", "by": <your DID>, "t", "n", "s"}`, where `s` is your Ed25519
   signature over

   ```
   aimarket-mandate-approval/1
   <hub base URL>
   <approval_id>
   approve
   <mandate digest>
   <body_sha256>
   <max_micro>
   <t>
   <n>
   ```

   With the SDK: `httpx.post(approval["url"], json=approval_payload(owner, hub_origin=HUB,
   approval=approval))`. Any owner DID linked to the account may sign (a second owner — say a
   finance key — works).
   The API key alone can only **deny** (`{"decision": "deny"}`): approving spends money, and a
   key is what leaks.
4. The agent sends the same request again with a fresh proof. It runs once; the approval is
   spent with it, or given back if the call fails before it is charged. A denial stands until
   the request expires (`402 approval_denied`), so a looping agent cannot nag you.

An agent may have at most 16 requests waiting (`429 approval_queue_full`). Re-delegated
mandates keep the parent's threshold and may only lower it. Over A2A the task waits in
`AUTH_REQUIRED` and moves when you answer, with a push to the agent's webhook
([a2a.md](a2a.md#paid-with-a-mandate)).

### Being told when a call waits for you

Without a channel an owner learns about a request only by asking (step 2 above). Register
channels on the funding account and the hub sends each new request — and the answer to it —
there. A notification only tells: approving still needs an owner key's signature, which no
chat, channel or ticket holds, and every message says how to approve and how to deny.

```bash
# Telegram through the hub's bot (when the operator runs one): press Start with it, then give your chat id
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "telegram", "chat_id": "123456789"}'
# … or through your own bot: add "bot_token": "123456789:AA…"
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "slack", "webhook_url": "https://hooks.slack.com/services/T…/B…/…"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "jira", "base_url": "https://acme.atlassian.net", "email": "ops@acme.example",
       "api_token": "…", "project_key": "OPS", "issue_type": "Task"}'
curl -X POST "$HUB/ai-market/v2/mandates/notify" -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"kind": "webhook", "url": "https://ops.acme.example/hooks/aimarket", "secret": "…"}'
# send a test message now and see what the channel answered
curl -X POST "$HUB/ai-market/v2/mandates/notify/<channel_id>/test" -H "X-API-Key: $KEY"
```

| `kind` | What you give | What arrives |
|---|---|---|
| `telegram` | `chat_id` (a number, or `@channel` where the bot is an admin). `bot_token` for your own bot; without it the hub's bot is used, if the operator runs one (`GET …/notify` names it in `telegram_bot`). | A message: which capability, how much, the ceiling, until when, how to approve and how to deny. HTML, or the same words as plain text if Telegram refuses the markup. |
| `slack` | `webhook_url` of an incoming webhook (`https://hooks.slack.com/services/…` or `/triggers/…`). | The same text. |
| `jira` | Jira Cloud `base_url` (https), `email`, `api_token` (id.atlassian.com → Security → API tokens), `project_key`, `issue_type` (default `Task`). | One issue per request; the answer is added to it as a comment. |
| `webhook` | `url` (https), optional `secret`. | `POST` of `{"event": "mandate.approval.requested" \| "….approved" \| "….denied", "approval": {…}, "title", "text"}` with `X-AIMarket-Event`; with a secret also `X-AIMarket-Signature: t=<unix>,v1=<hex HMAC-SHA256 of "<t>.<body>">`. |

- `GET /ai-market/v2/mandates/notify` lists the account's channels with the outcome of each
  one's last delivery. Secrets — a bot token, the Slack URL, a Jira token, a webhook secret —
  are stored to be used and never returned (the Slack URL shows its last four characters).
- `POST …/notify/{channel_id}/test` sends a test message at once and answers `delivered` and
  what the channel said; `DELETE …/notify/{channel_id}` removes a channel. Up to 8 per account.
- A channel belongs to the funding account, so it hears about every mandate that account
  funds. The account's API key manages channels: the same key already lists its pending requests.
- Every address is checked like any address a caller gives this hub: https only, no private
  or metadata networks, resolved once and pinned, no redirects. Delivery runs off the request
  path, retries twice (after 2 s and 10 s) on no answer, a 5xx or a 429, and never changes the
  request it reports on.

### Reading a mandate's status

`GET /ai-market/v2/mandates/{digest}` answers anyone who holds the digest (an unknown one:
`404 mandate_unknown`). `status` is the state of the mandate **as a chain** — a re-delegation
whose parent was revoked cannot be used, however clean its own row looks:

| `status` | Meaning |
|---|---|
| `active` | Usable now. |
| `revoked` | It or an ancestor was revoked. `revoked_at` is set only on the mandate that was itself revoked; a descendant shows `revoked_at: null`, with the reason in `status_reason`. |
| `expired` | It or an ancestor is past its `validUntil`. |
| `pending` | It or an ancestor is not valid yet (`validFrom` is ahead). |
| `invalid` | The chain does not hold: an ancestor is missing, a link breaks the narrowing rules, or the stored document no longer passes the field rules. |

The other fields are `issuer`, `subject`, `parent`, `root`, `chain` (the digests, root → leaf),
`depth` (0 for a root), `valid_from`, `valid_until`, `revoked_at`, and `status_reason` whenever
the status is not `active`.

Usage — `usage`: `day`, `spent_today_usd`, `per_day_usd`, `remaining_today_usd`,
`spent_total_usd`, plus `total_usd` and `remaining_total_usd` when the mandate has a `total` limit
— is added for two kinds of caller:

- the root's funding account, with its `X-API-Key`;
- any key in the chain — every issuer and every subject, so an owner can watch an agent it
  re-delegated to — with a request proof over `GET`, an empty body and the request path:

```python
from aimarket_agent import request_proof

digest = reg["digest"]
path = f"/ai-market/v2/mandates/{digest}"
proof = request_proof(owner, hub_origin=HUB, leaf_digest=digest, body=b"", method="GET", path=path)
httpx.get(f"{HUB}{path}", headers={"X-AIMarket-Mandate-Proof": proof}).json()["usage"]
```

A proof that does not verify answers `401 mandate_proof_invalid` instead of the status. Spend is
recorded against every mandate in the chain, so a parent's figures include what its
re-delegations spent. `day` is the UTC calendar day the daily counter covers.

## Agent: pay with the mandate

```python
from aimarket_agent import AIMarketAgent, Mandate

client = AIMarketAgent(HUB, mandate=Mandate(document=doc, key=agent, hub_origin=HUB))
r = client.invoke_single("gaia.gateway", "gaia.weather.read@v1", {"latitude": 60.17, "longitude": 24.94})
r["mandate"]    # {"digest", "agent", "principal", "depth"} on a delivered call
```

Every call is signed over its exact body, the hub, the method and path, and a one-time nonce,
within 300 seconds of the hub's clock. The path is **relative to the hub's base URL**: for a hub
published at `https://example.net/hub`, a POST to `https://example.net/hub/ai-market/v2/invoke`
signs `POST /ai-market/v2/invoke`, and `hub_origin` is `https://example.net/hub`. `Mandate`
signs that path by default.

What comes back when the hub says no:

- over a limit: `402 mandate_limit`, with `limit` naming which (`perCall`, `perDay`, `total`,
  `perProductPerDay`, or `subcontract.perCallAllowance` for an allowance) and `mandate` naming the
  mandate in the chain that refused. `perCall` covers everything one call reserves — on a
  federated call, its price and its routing fee together. The product a per-product limit counts
  is the one the hub executes, whatever `product_id` the caller typed;
- outside the scope: `403 mandate_scope`; unknown, expired, revoked or not addressed to this hub:
  `403 mandate_invalid`; a bad signature, a stale `t` or a reused nonce:
  `401 mandate_proof_invalid`; an account that pays only under a mandate, reached without one:
  `402 mandate_required`.

The SDK returns a 403 mandate or job refusal as `{"refused": True, "error": …, "detail": …}` —
not as `safety_blocked`, which is kept for the content-safety gate. A 402, 401 or 400 comes back
as the hub's body (`error`, `detail`, and `limit` / `mandate` where set).

The provider the hub runs receives `X-AIMarket-Agent` (the leaf subject) and
`X-AIMarket-Principal` (the root issuer) — who is calling, vouched for by the hub — and nothing
about the account or the limits. Neither header is sent on a call routed to a peer hub: the peer
did not verify the mandate.

The same mandate pays over A2A (`POST /a2a`, [a2a.md](a2a.md)): the headers ride on the A2A
request and the invoke goes in one raw `application/json` part holding the exact bytes the
proof signs — still for `POST /ai-market/v2/invoke`. A limit reached is a `REJECTED` task.
Reading your tasks back (`GetTask`, `ListTasks`) takes a fresh proof over `POST /a2a` and the
JSON-RPC body. `aimarket_agent.A2AClient(HUB, mandate=…)` and ARGUS's `argus a2a invoke` do both.

**ARGUS** pays the same way. `argus mandate keygen` prints a new agent `did:key` and its secret;
the owner issues a mandate to that DID and registers it; `ARGUS_AGENT_KEY` (the secret) and
`ARGUS_MANDATE_FILE` (the mandate JSON) switch ARGUS to it. `argus mandate status` shows the
chain's status and spend, and `argus mandate delegate --to <did:key> --per-call <usd> --per-day <usd>`
registers a narrower re-delegation for a sub-agent.

## Provider: hire another provider inside a job

> The full guide — the flow and money diagrams, where the money is at every step, who carries
> which risk, children on other hubs, A2A, errors and operator notes — is
> [subcontracting.md](subcontracting.md). This section is the short version.

Every provider this hub executes through its invoke URL receives `X-AIMarket-Job` (a token signed
with the key the hub publishes as `signer_public_key` in its well-known, valid for 60 seconds) and
`X-AIMarket-Hub` (where to present it), plus `X-AIMarket-Job-Grant` when the buyer set aside an
allowance. Send them back on anything you buy while serving the call:

```python
from aimarket_agent import AIMarketAgent, JobContext

job = JobContext.from_headers(request.headers)       # None when the hub sent no token
buyer = AIMarketAgent(job.hub or HUB, api_key=MY_OWN_KEY)
r = buyer.invoke_single("wx", "wx.read@v1", {"q": 1}, job=job)
r["job"]    # {"job_id", "node", "parent", "depth", "funded_by"}
```

- With a grant (**cost-plus**) the purchase is paid from the buyer's allowance and nothing else
  may be sent with it — no `X-API-Key`, mandate, channel or x402 payment (`403 job_invalid`); the
  SDK leaves its own payment off when the job carries a grant. Every balance figure in the answer
  is what is left of the allowance, never the buyer's balance.
- Without one (**fixed price**) you pay with your own rail; the purchase still appears in the
  buyer's job tree.

### What the hub refuses inside a job

| Answer | When |
|---|---|
| `403 job_invalid` | The token is not this hub's or has expired, or the call it was issued to has already returned: a provider holding a token past its call cannot graft purchases onto a job whose bill and receipt are already out. |
| `402 allowance_exhausted` | The grant is closed — it closes the moment the root call returns — or what is left cannot cover the price. |
| `403 job_limit` | `limit` says which: `depth` (deeper than the job allows), `cycle` (the capability is already on the path), `nodes` (the job already holds 64 calls, the root included), `children` (the calling node already has 16). |
| `403 mandate_scope` | A grant-funded purchase outside the root mandate's scope. |
| `400 subcontract_unsupported` | A call inside a job asks for an allowance of its own; only the root sets one. |

The depth a job allows: without an allowance (linkage only) it is the hub's maximum, 3 — every
hop pays for itself, so the depth bounds only the size of the tree. With an allowance it is the
buyer's `max_depth`. A child refused after it joined the tree — outside the root mandate's scope,
say, or with the root mandate revoked in the meantime — gives its slots back and shows in the tree
as `refused`.

### The buyer's side: an allowance and the bill

The buyer asks for an allowance on the root call:

```python
r = client.invoke_single("brief", "brief.make@v1", {...},
                         subcontract={"allowance_usd": 0.005, "max_depth": 2})
```

`allowance_usd` must be above 0 and at most `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`;
`max_depth` is 1–3 (default 1). The hub reserves the price and the allowance together from the
buyer's credit account and, on a mandated call, against the mandate chain, whose leaf must carry a
`subcontract` block that bounds both. An allowance on a call that pays on chain or through a
channel, carries neither an `X-API-Key` nor a mandate, or is routed to a peer answers
`400 subcontract_unsupported`: the hub can only pass through money it meters.

The root answer carries the bill of materials:

```json
"subcontracting": {
  "job_id": "job_…",
  "nodes": [
    { "node": "node_…", "parent": "node_…", "depth": 1,
      "product_id": "wx", "capability_id": "wx.read@v1",
      "price_usd": 0.001, "funded_by": "allowance", "status": "captured",
      "receipt_digest": "sha256-…", "receipt_id": "urn:uuid:…" }
  ],
  "spent_from_allowance_usd": 0.001,
  "allowance_usd": 0.005,
  "spent_usd": 0.001,
  "released_usd": 0.004
}
```

- `nodes` are the subcontracted calls; the root itself is not listed. `status` is `running`,
  `captured`, `failed` or `refused`; `funded_by` is `allowance` or `own`. `receipt_id` and
  `receipt_digest` name the child's AWR/2 work receipt.
- An allowance-funded node's `price_usd` is what that call actually took from the allowance
  (see [the rules below](#rules-that-are-easy-to-miss)); `spent_from_allowance_usd` is their sum.
- `allowance_usd`, `spent_usd` and `released_usd` appear only when an allowance was set.
  `spent_usd` and `released_usd` are what the ledger settled; they are `null` while the settlement
  is still pending (a release that failed, which the sweep retries — see
  [Stranded allowances](#stranded-allowances)). `null` does not mean nothing was spent.
- The block is on the root's answer **whether the root delivered or not**. A subcontractor that
  delivered is paid even if the provider that hired it then fails (cost-plus: materials consumed
  are paid for), so a failing root still returns the bill and the `job_id` that explain the
  charge.
- Every call the hub executes through a provider endpoint gets a job id, so its answer carries a
  `subcontracting` block even when nothing was subcontracted (`"nodes": []`).

`GET /ai-market/v2/jobs/{job_id}` returns the tree later: the same nodes plus the root's own
(`depth` 0), `spent_from_allowance_usd`, and — with an allowance — `allowance_usd`, `max_depth`,
`allowance_status`, and `spent_usd` / `released_usd` once the settlement is recorded. The job id
is an unguessable capability: anyone holding it can read the tree, and the hub gives it only to
the root buyer and the providers of the job.

The root's AWR/2 work receipt lists each delivered child's work receipt in
`credentialSubject.parents`: `id` is the child's `receipt_id`, `digestSRI` its `receipt_digest`.
Each child's receipt does the same for its own children, so the tree is committed to hop by hop,
not only reported.

Limits the hub enforces whatever the buyer asks: depth ≤ 3, 64 calls per job including the root,
16 children per call, no cycles (a capability already on the path), a token that lives 60 seconds
(the 30-second provider timeout plus 30), a grant that dies with its root call.

### Rules that are easy to miss

- **A child on another hub needs `source_hub`.** Only the root must execute on this hub; a
  child can be any capability this hub routes, and its price (and, for a resold peer, the
  routing fee) is carved out of the allowance like a local one. But without
  `source_hub: <the peer URL /search returns>` the hub looks for a local capability, finds only
  the peer's listing and answers `400` — and the attempt still takes one of the call's 16
  child slots and shows in the bill as a failed node.
- **The job token and the grant never leave this hub.** A routed child reaches the peer
  without either; linkage and money stay where the hub can meter them.
- **Verify the token before you spend.** Your invoke URL is public. Check the signature
  against the hub's `signer_public_key` (from `/.well-known/ai-market.json`), that `iss` is
  the hub you serve, `exp`, that the last entry of `path` is *your* capability (the hub hands
  a token to every provider it runs — this stops another provider replaying its own at you),
  and serve each `node` once. Refuse anything else before buying anything.
- **`max_price_usd` on a routed child is compared in whole cents.** The hub quotes a routed
  capability as its price plus routing fee rounded up to the cent, so a ceiling below $0.01
  refuses a $0.001 child with `409 price_limit_exceeded`.
- **The bill adds up.** An allowance-funded node's `price_usd` is what that call took from the
  allowance, routing fee included, so those nodes sum to `spent_usd`, and
  `spent_usd + released_usd == allowance_usd`. A failed node whose hold was released shows 0; one
  that still cost money (the peer delivered, then the fee capture failed) shows what was taken.

### Worked example: `weather.witness@v1`

[`examples/subcontract-capability`](../examples/subcontract-capability/) is a real provider
built on these rules, run by the hub operator. For a place it buys `gaia.weather.read@v1` and
`gaia.air.read@v1` (product `gaia.gateway`, `source_hub: https://iot.modelmarket.dev`) through
the hub that called it, inside the caller's job, and answers with both device-attested
readings, whether they agree on place and time, and each child's job node and receipt digest,
signed over the hub's request-bound canonical. Cost-plus when the buyer sends an allowance
(token + grant, nothing else); fixed price otherwise (token + its own `X-API-Key`, under a
daily cap, and it refuses without one).

[`scripts/subcontract_canary.py`](https://github.com/alexar76/aicom/blob/main/scripts/subcontract_canary.py) is the root buyer:

```bash
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py            # cost-plus, allowance $0.01
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --fixed-price
SUBCONTRACT_CANARY_API_KEY=aimk_… scripts/subcontract_canary.py --a2a      # the root call over A2A 1.0
```

It asserts two captured children funded as expected, `spent + released == allowance`, node
prices that add up to what was spent, the same tree from `GET /ai-market/v2/jobs/{job_id}`, and
the children's receipt digests in the root receipt's `credentialSubject.parents`.

Be clear about what that demonstrates: it is **self-driven** — our buyer, our composite, our
GAIA, internal credits. Every hop is the production code path and every claim is checked from
outside, which is what it is for; it is not evidence that anyone else wants the product. The
example's README has the operator runbook (systemd, nginx, the collateral exemption, publish,
a canary account). `tests/test_subcontract_example.py` runs the provider and the canary against
the real hub app.

## Operator

### Configuration

| Variable | Default | Effect |
|---|---|---|
| `AIMARKET_CREDITS_ENABLED` | `0` | Mandates and allowances need the credits rail on; off, a mandated call or an allowance answers `503 mandates_unavailable`. Job tokens (linkage) work either way. |
| `AIMARKET_HUB_URL` | `http://localhost:9083` | The hub's public base URL, path included for a hub mounted under one. It is the audience a mandate must name and the origin every proof signs, so a hub left on the default refuses every mandate addressed to its public name. |
| `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD` | `1.0` | Largest pass-through allowance one root call may reserve. |
| `AIMARKET_SUBCONTRACT_SWEEP_S` | `120` | How often stranded allowances are swept (below). `0` turns the sweep off; a value under 10 is raised to 10. |
| `AIMARKET_ADMIN_TOKEN` | unset | `Authorization: Bearer …` with it stands in for an owner's signature on owner changes — the recovery path. |
| `AIMARKET_HISTOR_URL` | unset | Where the provenance plugin anchors receipt digests; unset = anchoring off. |
| `AIMARKET_HISTOR_FLUSH_S` | `30` | How often the outbox sends pending anchors (backs off to 10 min while HISTOR fails or defers). |
| `AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS` | `30` | Days an anchored row stays in the outbox; after that the status route asks HISTOR. `0` keeps every row. |
| `AIMARKET_MANDATE_APPROVAL_TTL_S` | `86400` | How long an owner-approval request stays open (300 s – 7 days). An approved one must be used within the same window. |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_TOKEN` (or `…_FILE`) | unset | The hub's own Telegram bot for approval notifications: owners then give only a chat id. Unset, a Telegram channel needs the owner's own `bot_token`. Never logged. |
| `AIMARKET_NOTIFY_TELEGRAM_BOT_NAME` | unset | That bot's @name, returned by `GET /mandates/notify` so owners know whom to press Start with. |

The image already installs `awr` (the provenance plugin needs it). A hub installed without it
starts normally and answers `503 mandates_unavailable` to mandated calls.

Clients sign request paths relative to `AIMARKET_HUB_URL`; before it checks a proof, the hub
removes a mount prefix that the ASGI server reports as `root_path`.

### The well-known blocks

`/.well-known/ai-market.json` tells a client, before it sends anything, whether this hub enforces
AMD/1 and SUB/1 and with which limits:

```json
"mandates": {
  "spec": "aimarket-protocol/mandates.md", "version": "AMD/1", "enabled": true,
  "audience": "https://modelmarket.dev",
  "register": "/ai-market/v2/mandates", "owners": "/ai-market/v2/mandates/owners",
  "revoke": "/ai-market/v2/mandates/revoke", "status": "/ai-market/v2/mandates/{digest}",
  "max_chain": 4
},
"subcontracting": {
  "spec": "aimarket-protocol/mandates.md#6-subcontracting-sub1", "version": "SUB/1",
  "job_tokens": true, "allowance": true, "max_allowance_usd": 1.0,
  "max_depth": 3, "max_nodes_per_job": 64, "max_children_per_node": 16,
  "jobs": "/ai-market/v2/jobs/{job_id}"
}
```

`mandates.enabled` and `subcontracting.allowance` follow `AIMARKET_CREDITS_ENABLED`;
`mandates.audience` is `AIMARKET_HUB_URL` without a trailing slash — the exact string a mandate's
`audience` must contain; `max_allowance_usd` follows `AIMARKET_SUBCONTRACT_MAX_ALLOWANCE_USD`.

### Stranded allowances

An allowance is a credit hold on the buyer's account that should live exactly as long as its root
call. If the root never settled it — a crash mid-call, a release that kept failing — the money
would stay frozen. The hub sweeps once at start and then every `AIMARKET_SUBCONTRACT_SWEEP_S`
seconds: an allowance whose grant expired more than five minutes ago and whose hold is still held
is closed, what is left is released, a mandated allowance's reservation is settled to what the
children drew, and the settlement is recorded, so the job's `spent_usd` / `released_usd` fill in.
Up to 50 allowances per cycle; `subcontract: settled N stale allowance(s)` is logged at WARNING
when any were settled. The sweep runs only with the credits rail on, and never on the request
path.

### Migration 038

`038_job_receipts_and_settlement` adds:

| Column | For |
|---|---|
| `job_nodes.work_receipt_id` | The child's work-receipt id, carried by the parent receipt's `parents` edge and by the bill's `receipt_id`. |
| `job_grants.spent_micro`, `released_micro`, `settled_at` | How the allowance was settled, so `GET /jobs/{job_id}` matches the bill the root answer carried. |
| `mandates.credential_id`, unique index on `(issuer, credential_id)` | One credential id per issuer. |
| `mandate_holds.pending_back_micro` | A child refund that arrives while the allowance's reservation is still open, subtracted by the settle that closes it. |

It is applied at start, like every hub migration. 036 and 037 belong to other branches; versions
are a set, not a sequence, so a hub can show 038 applied before them. Rows written before 038 keep
an empty `credential_id` (the unique index skips them) and an empty `work_receipt_id` (their
`parents` edge names the node as `urn:aimarket:job-node:…`; the digest still commits to the right
bytes).

The µUSD columns of 034 and 035 are `BIGINT`. On SQLite that is the same 64-bit integer as
before. A PostgreSQL hub that applied 034/035 while they said `INTEGER` has int4 columns, which
top out at $2,147.48, and an applied migration is not re-run: change `mandate_usage.spent_micro`,
`mandate_holds.amount_micro`, `job_nodes.amount_micro` and `job_grants.allowance_micro` with
`ALTER TABLE … ALTER COLUMN … TYPE BIGINT`.

Every call the hub executes through a provider endpoint writes one `job_nodes` row when it
finishes, whether or not it subcontracted.

### Anchoring receipts in HISTOR

With `AIMARKET_HISTOR_URL` set, the provenance plugin queues every work receipt's digest and a
background thread sends the queue to HISTOR's receipts log (what is sent and how it is retried:
[the plugin's README](https://github.com/alexar76/aimarket-plugins/blob/main/plugins/aimarket-provenance/README.md)). HISTOR accepts anchors only from
the issuers its operator lists in `HISTOR_RECEIPT_ISSUERS`, so give that operator this hub's
receipt issuer `did:key`. Read it off any live receipt — `provenance_receipt.issuer` in an invoke
answer, or `issuer.id` in the receipt document:

```bash
curl -s "$HUB/ai-market/v2/p/provenance/receipt/$RECEIPT_ID" | jq -r '.issuer.id'
```

The plugin also logs it at startup (`Provenance issuing AWR/2 receipts as did:key:…`). Until
HISTOR lists it, anchors are refused as "issuer is not accepted" and stay `pending`: the hub
retries them with backoff for up to 30 days, so nothing is lost while the two operators catch up.

`GET /ai-market/v2/p/provenance/anchor/{receipt_id}` shows where a receipt stands: `pending` (with
`attempts` and `last_error`), `anchored` (with `leaf_index` and a `proof_url` into HISTOR),
`refused` (with `last_error`), `not_queued`, or `not_configured` when anchoring is off.

**After retention, the log answers.** Anchored rows leave the outbox once they are older than
`AIMARKET_HISTOR_OUTBOX_RETAIN_DAYS` (default 30; 0 keeps them); `pending` and `refused` rows are
never removed. For a receipt with no row the route asks HISTOR itself: a proof that names this
digest under this hub's key reads `anchored` with `"source": "log"`; not in the log reads
`not_queued`; a log that cannot be reached reads `unknown`, never `anchored`. Answers are
remembered (an hour, five minutes, thirty seconds) so the public route cannot make the hub
hammer the log.

**Receipts issued before anchoring was switched on.** Queue them with their own issue time;
the running hub's outbox sends them like any other row:

```bash
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db --dry-run
docker exec -it modelmarket-hub python -m aimarket_provenance.backfill --db /app/data/provenance.db
```

It queues only receipts that verify, were issued by this hub's provenance key, and are younger
than HISTOR's 30-day window (with an hour's margin); it refuses to run where
`AIMARKET_HISTOR_URL` is unset, so a hub that does not anchor publishes nothing. HISTOR's window
exists to stop backdating, so a receipt older than that cannot be anchored with its true time and
is left alone. A backfilled anchor proves the receipt existed by the moment HISTOR logged it, not
at the issue time the receipt claims.

Traffic on `/a2a` and `/.well-known/agent-card.json` is counted in
`aimarket_hub_a2a_requests_total{method,result}` on `/metrics`; an invoke task is counted by
the state it reached (see [a2a.md](a2a.md)).
