# Use cases

Attested Memory is for situations where **forgetting is expensive** and
**blind trust is worse**. These scenarios show when a note, chat log or
vector store is not enough — and when identity, truth state, provenance and
exact settlement turn context into something you can act on.

Route names, headers and payment terms stay exact across languages. Only the
explanatory text is localized.

## Founder second brain that survives context rot

**Who.** A founder, researcher or operator who jumps between tools, agents and
devices every day.

**Problem.** Decisions live in chats, Notion dumps and half-finished prompts.
Six weeks later nobody can say *why* a choice was made, which sources were
trusted, or which agent invented a convenient summary.

**How it works.**

1. Write a Memory Unit with the decision, rationale, tags and `source_refs`.
2. Sign as an actor (`X-Actor-ID` / public key / signature). The private key
   stays in your client.
3. Later, search `/memory/api/search` and inspect truth + provenance before
   you reuse the memory in a new plan or agent run.

**Why attestation matters.** You are not retrieving “a similar paragraph”.
You are retrieving a portable claim with an actor and a lineage.

**Start.** [Personal Memory](/memory) · [User guide](USER_GUIDE.md) · trial on
[/billing](/billing).

## Incident war-room that keeps the decision trail

**Who.** On-call engineers, SREs, security responders.

**Problem.** The outage channel moves faster than the wiki. The postmortem is
written from memory, ownership of each call is fuzzy, and next week’s agent
repeats a rejected mitigation because nothing was signed into a shared
namespace.

**How it works.**

1. Open a Team Memory OS workspace and create a team namespace.
2. Members write incident notes, rejected options and final actions with
   actor signatures.
3. The SaaS gateway checks membership; the Hub accepts only matching
   `team:<id>` records. Queries cannot bleed into another team.

**Why attestation matters.** Handoffs become auditable. Offboarding revokes
the key; short-lived team assertions expire without a forensic scavenger hunt.

**Start.** [Team Memory OS](/teams) · [User guide § Team](USER_GUIDE.md).

## Expert knowledge that sells without leaking the corpus

**Who.** Domain experts, research shops, advisory boutiques.

**Problem.** Publishing the full corpus for free destroys the business.
Publishing only a teaser destroys trust. Buyers need to see provenance before
they pay — and sellers need time-bound access, not perpetual copies by default.

**How it works.**

1. Publish a Memory Unit with public summary fields and paid visibility for
   the body.
2. Buyers search the catalog, inspect truth/provenance, then open an exact
   Base USDC invoice.
3. KOVA verifies the transfer; the Gateway issues a scoped entitlement.
   Access expires with the plan.

**Why attestation matters.** Discovery is honest. Settlement is exact.
Entitlement is cryptographic product scope, not an honor-system PDF link.

**Start.** [Expert Memory Market](/market) · [Payments](/billing).

## Multi-agent handoff with cryptographic continuity

**Who.** Agent operators, orchestration teams, autonomous workflows.

**Problem.** Agent A dumps a chat summary for Agent B. The summary is unsigned,
partially hallucinated, and stripped of sources. Failures look like “the next
model was dumb” when the real bug was a silent loss of provenance.

**How it works.**

1. Agent A writes a signed handoff Memory Unit: constraints, tools used,
   sources, open risks.
2. Agent B retrieves it with the same actor/team policy and verifies
   provenance before continuing.
3. Truth state travels with the unit — contradictions are visible instead of
   being smoothed into confident prose.

**Why attestation matters.** Continuity is a property of the record, not of
whoever happened to keep the tab open.

**Start.** [Developers](/developers) · [User guide § Actor identity](USER_GUIDE.md).

## Due diligence and research with source-bound claims

**Who.** Analysts, counsel, investment and vendor-review teams.

**Problem.** Diligence notes cite “the deck”, “the call” and “something from
Slack”. When a claim is challenged, the chain of custody is a feeling.

**How it works.**

1. Capture each material claim as a Memory Unit with explicit `source_refs`.
2. Attach or update truth state as evidence arrives (confirmed, disputed,
   insufficient).
3. Reconstruct the file later from provenance receipts rather than from
   reconstructed folklore.

**Why attestation matters.** Reviewers argue about the claim and its evidence,
not about whose notes were “more recent”.

**Start.** Personal or Team product · [Glossary](GLOSSARY.md).

## Automated paid access when the browser is gone

**Who.** Buyers who pay from a wallet app, scripts that settle invoices, and
operators who cannot babysit a checkout tab.

**Problem.** Classic checkout dies when the tab closes. Manual “paste the tx
hash” flows create support tickets and ambiguous partial payments.

**How it works.**

1. `POST /v1/billing/orders` with a unique `Idempotency-Key`, plan and payer.
2. Send the exact canonical USDC amount on Base to the invoice recipient.
3. KOVA matches token, payer, recipient, amount and confirmation depth.
4. The Gateway activates the product key automatically. Polling
   `GET /v1/billing/orders/{id}` with the checkout token returns the key when
   confirmed — even if the original browser session is gone.

**Why attestation matters.** Money movement and entitlement issuance are
bound by exact invoice identity, not by a screenshot of a wallet.

**Start.** [Billing](/billing) · [User guide § Buy access](USER_GUIDE.md).

## Safe offboarding without orphaning the institution

**Who.** Team leads, security, IT.

**Problem.** A departing operator still has chat exports and personal notes
that contain the real runbooks. Revoking Slack does not revoke institutional
memory that never lived in a controlled system.

**How it works.**

1. Keep operating knowledge in Team Memory OS under an explicit namespace.
2. Rotate or revoke the SaaS key immediately on departure.
3. Team assertions expire in minutes; Hub policy still demands actor proofs
   for protected reads and writes.

**Why attestation matters.** Access ends as a control-plane event, not as a
hope that someone deleted a Drive folder.

**Start.** [Team Memory OS](/teams).

## What this is not for

- A general chat archive with no identity or source discipline.
- A place to store wallet private keys, seed phrases or raw credentials.
- Unscoped “share with the world” dumps that skip visibility policy.
- Rounded or approximate crypto payments — exact USDC amounts are the invoice.

If your workflow can tolerate silent loss of authorship, sources and payment
finality, a notebook is enough. If it cannot, start with the matching product
surface above and keep the Hub contracts exact.
