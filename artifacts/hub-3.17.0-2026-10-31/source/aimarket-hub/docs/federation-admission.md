# Federation admission — sandbox assay, then automatic index

> **Русский:** [federation-admission.ru.md](./federation-admission.ru.md) · **Español:** [federation-admission.es.md](./federation-admission.es.md) · **Français:** [federation-admission.fr.md](./federation-admission.fr.md) · **中文:** [federation-admission.zh.md](./federation-admission.zh.md)
>
> Code: [`federation_assay.py`](../aimarket_hub/federation_assay.py) · [`api.py`](../aimarket_hub/api.py) · [`crawler.py`](../aimarket_hub/crawler.py) · [`config.py`](../aimarket_hub/config.py)
>
> Join path for hub operators: [`docs/join-the-federation.md`](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.md)

---

## Why this exists

A knock (`POST /federation/announce` or inbound `X-AIMarket-Crawler`) is an **observation**.
It must never index a catalogue: that would be manifest injection. Until this change, the
only exit from quarantine was a human at `/operator` clicking Approve for every new hub.

Operators will not sit on that queue. Admission after quarantine is therefore **automatic**,
but it scores **what ran in the sandbox**, not what the knocker wrote in `.well-known`.

Factory analog (do not import the factory into the hub):

| Factory | Federation hub |
|---------|----------------|
| `product_automated_verify` — score running tests/artifacts, not storefront copy | `analyze_sandbox_output` — safety gate + schema + no private IPs on the invoke payload |
| `docs/sandbox-trust-model.md` — soft isolation, not a hypervisor | Bounded HTTP POST to *their* public invoke URL (we do not execute their code locally) |
| `agents/surrogate_reviewer.py` — approve/block JSON | Optional `AIMARKET_FEDERATION_JUDGE_URL` — **veto only**, evidence JSON with no `name`/`description` |

An LLM handed `name` / `description` will rubber-stamp fluent marketing. That path is closed.

## Pipeline

```text
knock → pending (nothing indexed)
     → hard checks (SSRF / schema / Ed25519 / same-origin)
     → sandbox POST of up to 3 public free capabilities (first signed receipt wins)
     → nothing free? knock on the cheapest priced one and read its 402
     → analyse live payload
     → optional LLM veto on evidence (no brochure fields)
     → pass + AUTO_ADMIT=1 → trusted + crawl
     → fail / review → stay pending (operator desk)
```

Triggered:

1. Background task after a successful unauthenticated announce (`outcome == added`).
2. End of each crawl cycle, up to 3 pending peers without a terminal `pass`/`fail`.
3. Admin `POST /ai-market/v2/federation/assay`.

## Two kinds of evidence

**Work that ran** — a free capability answered with a signed receipt. The strongest thing a
peer can show, and what the assay tries first.

**A payment door that answers** — for a hub with nothing free, the cheapest priced capability
is knocked on **without paying**. A 402 that names a rail and a recipient, and quotes the same
price the peer's own catalogue lists, is evidence: the endpoint is live, speaks the protocol,
and enforces its own price list. Nothing is bought; no payment header is ever sent.

Most of this federation sells everything it has, so under a free-SKU-only rule those hubs
could never produce evidence at all and queued at the operator desk forever — SKOPOS, ATLAS
and this project's own factory among them. The dossier records which kind it holds
(`sandbox.evidence_kind`), so a `pass` on a payment door is never mistaken for a run.

Two things a knock can reveal that a brochure hides: a 402 quoting a different price than the
catalogue (`sandbox_price_matches`), and a priced capability that answers an unpaid invoke
with 200 (`sandbox_price_enforced`). Either is `review`.

## Verdicts

| Verdict | Meaning | Auto-admit |
|---------|---------|------------|
| `pass` | Hard checks + one of the two evidence kinds below + analysis not false + judge not false | yes, if `AUTO_ADMIT=1` **and** a judge token is set |
| `review` | Nothing publicly offered, a 402 with no payment instructions, a price the 402 and the catalogue disagree on, a priced capability served unpaid, analysis fail, or judge `block` | no |
| `fail` | SSRF, schema, bad signature, key mismatch | no |

No `AIMARKET_FEDERATION_JUDGE_KEY` / `OPENROUTER_API_KEY` → the judge is not consulted and **auto-admit does not run**. An operator Approves at `/operator`. Prod default model is MiniMax (`minimax/minimax-m3`) via OpenRouter (`https://openrouter.ai/api/v1/chat/completions`), same token other fleet services use.

## Environment

| Variable | Default | Effect |
|----------|---------|--------|
| `AIMARKET_FEDERATION_ASSAY` | `1` | Master switch |
| `AIMARKET_FEDERATION_ASSAY_SANDBOX` | `1` | Probe up to 3 public free capabilities |
| `AIMARKET_FEDERATION_ASSAY_TIMEOUT_S` | `8` | Sandbox POST timeout |
| `AIMARKET_FEDERATION_AUTO_ADMIT` | `1` | `pass` → `trusted` **only with a judge token**. Alias: `AIMARKET_FEDERATION_ASSAY_AUTO_TRUST` |
| `AIMARKET_FEDERATION_JUDGE_URL` | OpenRouter chat if a key exists | OpenAI-compatible chat POST |
| `AIMARKET_FEDERATION_JUDGE_KEY` | `OPENROUTER_API_KEY` fallback | Bearer. **No key → manual Approve** |
| `AIMARKET_FEDERATION_JUDGE_MODEL` | `minimax/minimax-m3` | MiniMax, same as the fleet |
| `AIMARKET_FEDERATION_JUDGE_REQUIRED` | `0` | Judge error blocks admit (also implied when auto-admit + key) |
| `AIMARKET_FEDERATION_ASSAY_REQUIRE` | `0` | Human Approve refuses unless last assay is `pass` |
| `AIMARKET_FEDERATION_ASSAY_LLM` | ignored | Not a brochure judge |

## Operator desk

`/operator` is the **exception** path: paid-only hubs, vetoes, dismissals. It is not the
steady-state admission queue.

## Isolation limits

The hub does not run the peer's code in a local venv or gVisor. It POSTs to their public
invoke URL with a bounded body and a byte cap (`262_144`) enforced **while streaming**, so an
unadmitted peer cannot make the hub buffer a reply it will refuse anyway. Treat that as
**soft** isolation — the same class of guarantee as the factory preview, not a multi-tenant
hypervisor. SSRF guards still refuse private/link-local targets.

Which URL gets probed is [`federation_transport`](../aimarket_hub/federation_transport.py),
the same rule routed invokes use: a peer that declares itself a hub (`hub_version`, or `v2` in
`protocol_versions`) is probed at its `/ai-market/v2/invoke` route, because the `mcp_endpoint`
it advertises speaks MCP JSON-RPC and answers an AI-Market envelope with an error. A bare
capability service keeps its advertised endpoint.
