# HEPHAESTUS — the forge: price a capability graph before you spend it

> **Русский:** [hephaestus-studio.ru.md](./hephaestus-studio.ru.md) · **Español:** [hephaestus-studio.es.md](./hephaestus-studio.es.md) · **Français:** [hephaestus-studio.fr.md](./hephaestus-studio.fr.md) · **中文:** [hephaestus-studio.zh.md](./hephaestus-studio.zh.md)
>
> How to drive the page: [hephaestus-user-guide.md](./hephaestus-user-guide.md) · What to build with it: [hephaestus-use-cases.md](./hephaestus-use-cases.md)
>
> Core: [`hephaestus/`](https://github.com/alexar76/hephaestus/tree/main/). Monitor node: `hephaestus`. Executor: `POST /ai-market/pipelines`. · **Install and screenshots:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

## What it is

HEPHAESTUS composes a chain of marketplace capabilities, **costs it before anything is paid
for**, submits it to the pipeline executor, and keeps the signed bill of materials that comes
back — including which hop is to blame when a chain fails.

It is not a general workflow builder. Every node is a real row from the Hub's signed manifest
with a price, a declared latency and a stated amount of evidence behind its reliability. That is
the whole difference: a graph here can answer *what will this cost* and *who broke it*, which no
amount of box-drawing gives you.

Two surfaces, deliberately split:

| Surface | Role |
|---------|------|
| Alien Monitor node `hephaestus` | **Observation.** Real runs — cost, hops, at-fault hop — plus how much of the catalogue can actually be wired. |
| The studio page | **Construction.** Pick capabilities, fill parameters, see the estimate, submit. |

The monitor observes; it does not host the editor. An observation surface that invents a feed is
worse than an empty one, so with no runs on record the panel says exactly that.

## The studio page

The hub serves it at **`/studio`**, and that is not an arbitrary choice: the catalogue it
composes from is the hub's own signed manifest, and the hub's CORS is fail-closed, so a
page hosted anywhere else could not read it. Same origin, no bridge, no second domain.

Running is same-origin too. The pipeline executor is a different service and the browser
cannot reach it cross-origin, so the hub forwards one request through `POST /studio/run`.
That forwarder is deliberately narrow:

* the destination comes from `AIMARKET_PIPELINE_EXECUTOR_URL` on the hub, **never from the
  request body** — a forwarder that takes its target from the caller is an SSRF gadget
  whatever it is called, and this one is reachable from any browser;
* unset means `503` with the variable named, not a guess at some localhost port;
* the body is size- and shape-checked before anything leaves the hub, capped at the same
  sixteen nodes the executor accepts;
* no caller credentials are forwarded — the studio's run path is the free/sandbox one, and
  a paid run goes to the executor directly with its own channel.

The reply carries `trace_url`, so the page links to the signed bill of materials rather
than asking you to trust its own summary.

```bash
cd hephaestus/studio && npm install && npm run build   # produces dist/, served at /studio
```

Build output is not tracked in this repository, so the bundle is produced by a Node build
stage in the hub's image (the runtime image is Python-only). A deployment that somehow
lacks `hephaestus/studio/dist` answers `503` naming the missing build rather than 404ing.

Below 900px of **actual shell width** the three columns become one at a time — catalogue, canvas, checks — switched
from a bottom bar, because at 375px a palette and an inspector leave the canvas a few pixels
wide, and the canvas is the pane that has to be usable. The estimate stays in the header in
both layouts: it is the reason the page exists. Adding a module jumps to the canvas and
tapping one jumps to its parameters, so a tap never lands on a pane you cannot see.

The breakpoint is measured on the element with a `ResizeObserver`, not asked of the
viewport: a window can be physically narrow while reporting a wide CSS viewport — a desktop
user agent on a phone, a scaled or zoomed window, an embedded frame — and a media query
stays false in every one of those while the canvas is squeezed to a sliver.

## Wizards — a goal resolved against the catalogue

A wizard is a goal plus an ordered list of **roles**. A role is a predicate over what a
capability *declares* — the fields it produces, the fields it requires, the shape of its id
— never a hard-coded `product_id`. So a wizard cannot offer a row that is not on sale, and
it keeps working when the catalogue changes; a curated recipe list does neither.

Resolution picks one capability per role, ranked in this order: how much data the hop
threads from the one before it, then how little is left for the visitor to type, then
whether the row has measured evidence behind it, then price. Price is last on purpose — the
cheapest chain that does not do the job is not a saving.

Two guards, both of which exist because the live catalogue defeated the naive version:

* **`consumes`** — at least one wired field has to match what the role is supposed to
  receive. Without it, `platon.random@v1` paired with `platon.beacon@v1` on `num_bytes`:
  the draw echoes its own parameter in its output and the beacon takes that parameter as
  input, so the two wire up cleanly and audit nothing. A hop consuming the previous hop's
  *parameters* is not consuming its *result*.
* **`sameProductAsPrevious`** — for cryptographic material, correctness rather than
  preference. `proof` is a field name, not a format: the resolver happily fed a VRF proof
  from `platon.random@v1` into `chronos.verify@v1`, a VDF verifier, because both spell it
  `proof`. That chain bills for the first hop and then fails on a proof the second cannot
  parse. Plain data — a reading, a location — stays unconstrained, because there a second
  opinion from a *different* provider is worth more than one from the same one.

A goal whose roles cannot all be filled is returned **unavailable, with the role that
failed**, and the menu shows it with that reason rather than hiding it. Today two of the
four are unavailable, and both reasons are real gaps: nobody sells a verifier for
`platon`'s own draws, and `atlas.situation.brief@v1` requires a bounding box
(`west/south/east/north`) that no capability in the catalogue produces — `atlas.point.read@v1`
emits a `point` object instead. A wizard that quietly dropped the missing step would hand
someone a chain that does something other than what its title promises, and they would pay
for it before finding out.

## The estimate

Two rules keep the number honest, both pinned by tests in [`hephaestus/tests/estimate.test.ts`](https://github.com/alexar76/hephaestus/blob/main/tests/estimate.test.ts):

1. **An unpriced capability is named, never treated as free.** It is excluded from the total and
   listed separately, because a total that quietly absorbs unknowns is not an estimate.
2. **Money is summed in integer micro-dollars.** The catalogue's real prices are $0.001 sensor
   reads and $0.004 oracle calls; adding those in floating point drifts in exactly the digits the
   total is made of.

The routed price is used where the Hub routes to a peer — quoting the provider's ask would
under-quote every federated hop by the routing fee.

Latency is reported as the longest declared-latency path, i.e. a **floor**: the executor runs hops
sequentially today, so a real run cannot be faster than this. Capabilities that declare no latency
count as zero and are listed by name, so the figure is never inflated by a guess.

## Reliability you can trust — the `reputation_basis` rule

The Hub's manifest publishes a `success_rate_30d` for every row. For a row nothing has ever
invoked, that number is a deliberate neutral placeholder: the crawler ignores peer-declared
success rates, because a peer that could claim 99% would dominate routing on first index.

The consequence was that all seventy-six rows of the live catalogue published `0.5`, and nothing
in the document distinguished a measured one-in-two from an unobserved placeholder. The manifest
now carries the evidence next to the number:

| Field | Meaning |
|-------|---------|
| `observations_30d` | Invocations the publishing hub observed in the last 30 days. |
| `reputation_basis` | `measured` — the rate is successes/attempts over that window. `unobserved` — nothing ran; the rate is a placeholder. |
| `by_hub[*].trust_basis` | Per-peer twin: `measured`, `unobserved`, or `self` for the publishing hub. |

**The rule for every consumer, including our own UI: key off `reputation_basis`, never off the
number.** When the basis is not `measured`, show "no calls yet" — not a score. The core drops the
value entirely rather than pass it on ([`hephaestus/src/catalog.ts`](https://github.com/alexar76/hephaestus/blob/main/src/catalog.ts)),
and a hub that predates these fields reads as `unknown`, which is not the same as bad.

Once a capability has been invoked, the manifest serves the **measured** rate — the crawler's
comment always said the hub computes this itself; nothing did, so `0.5` had been frozen into every
signed manifest.

## Composability — why some rows cannot be wired at all

A capability is composable only if it declares input fields (a `properties` object, even an empty
one — "takes nothing" is an answer) **and** a non-empty output schema. Rows failing either are
discoverable and priced but cannot be connected to a neighbour, and the studio says so instead of
drawing a port that leads nowhere.

Three source-side gaps were closed to make the catalogue composable:

* **Platon, 9 capabilities.** The oracle-family aggregator federated Platon by id, description and
  price only, so every row inherited oracle-core's "no fields" default while Platon itself
  documents `num_bytes`, `client_seed`, `prompt`, `round`, `question` and the rest. The aggregator
  now carries Platon's own declarations through rather than restating them — anything restated by
  hand is the drift that once put `platon.verify@v1` on sale.
* **ATLAS, 6 SKUs.** `output_schema` was absent entirely: six priced decision artifacts whose
  result shape a buyer could only learn by paying for one. Schemas now mirror what the handlers
  build, and the suite validates real output against them in both directions — the schema may not
  over-promise, and it may not fall behind the handler.
* **Genuinely input-less capabilities** (`platon.state@v1`, `platon.commit@v1`,
  `gaia.fleet.status@v1`) declare an explicitly empty `properties`. That is correct, not broken:
  "takes nothing" and "does not say" are different states and the studio renders them differently.

## What the executor can and cannot express

The studio refuses a graph the executor cannot run, with a reason, rather than exporting JSON that
fails later — or worse, succeeds while feeding a hop from the wrong upstream.

* **At most 16 capabilities per pipeline** (`PipelineRequest.nodes`). Split larger work into stages.
* **One data-carrying parent per hop.** `input_from` names a single node, so exactly one incoming
  connection may be marked as the data source; the rest express ordering only.
* **Hops run sequentially.** The latency estimate is a floor, not a forecast.

### `input_from` names a node

`input_from` is declared as a node id and was implemented as a boolean: any truthy value injected
whichever hop finished last. In a straight chain those coincide. In a DAG they do not — a hop with
two parents received the result of whichever parent the topological sort happened to finish second,
so a fan-in graph could be drawn, priced, paid for and fed from the wrong upstream, with a valid
signature over the bill of materials.

It now names the parent it means, and results are kept per node so a far ancestor can be named too.
A value that does not match a known node keeps the old last-result behaviour, so existing callers
are unaffected.

## Running it: who executes, and who pays

A hop this factory does not host is routed to the hub's federated invoke, because the
studio composes from the hub's catalogue — seventy-six rows, every one a peer's — while the
executor hosts nine of its own. Before that routing existed, every graph a visitor could
build answered `404 capability not found`.

Money is the part that needed deciding rather than coding:

* **No credential of the executor is ever attached.** An unauthenticated Run button that
  spends the operator's balance is an open faucet, and every receipt it produced would name
  the wrong buyer.
* **The visitor's own trial identity travels end to end** — browser → hub → executor → hub —
  as `X-AIMarket-Sandbox-Visitor`. The hub meters a renewing per-visitor allowance, so
  forwarding the visitor's id rather than the service's is the difference between each
  person getting their own allowance and everyone sharing one exhausted bucket.
* **A hop that needs money fails as that hop.** `402` for payment required, `429` for a
  spent allowance — with the reason visible, never a silent charge. The estimate still says
  what it would have cost.
* **The bill of materials records `payer` per hop** — `local`, `trial`, `channel` or
  `unpaid` — so a free run is never signed evidence of a purchase.

Beyond the free tier a hop settles against a payment channel the caller controls, and the
record names that channel.

## Reading a run back

The executor signs a bill of materials per run and persists it. Until these routes existed nothing
could read one back: hop-level blame — the evidence a dispute and any resulting slash rests on —
was visible only to whoever made the original POST.

| Route | Returns |
|-------|---------|
| `GET /ai-market/pipelines?limit=N` | Recent runs as a **redacted projection**: cost, hops, per-hop status, blame. |
| `GET /ai-market/pipelines/{trace_id}` | The **signed** bill of materials, verbatim. |

The split is deliberate. A signature covers the object as written, so filtering the by-id response
would hand back something unverifiable. Enumeration is the opposite problem: a public feed of runs
would publish which payment channel funded what, and the per-hop receipt nonces that are lookup
keys for public receipts carrying amounts. So the listing drops `channel_id` and `receipt_nonce`,
and each row names the path to its own signed original.

### Blame

A pipeline failure is the failing hop's fault, never the whole graph's. The BoM names the at-fault
hop and explicitly clears the upstream hops that did their work, so a dispute targets only the
responsible provider:

```json
{
  "policy": "hop-level",
  "at_fault": {"id": "v", "capability_id": "metis.verify@v1", "status_code": 500},
  "not_at_fault": ["s"],
  "not_executed": ["d"]
}
```

## Submitting a graph

A blueprint converts to the executor's body. Only capability nodes travel — triggers and outputs
are how a person reads a canvas, not hops anyone is billed for:

```json
{
  "nodes": [
    {"id": "s", "product_id": "prod-mcp", "capability_id": "web.search@v1",
     "input": {"query": "a claim"}, "depends_on": []},
    {"id": "v", "product_id": "prod-metis", "capability_id": "metis.verify@v1",
     "input": {"claim": "a claim"}, "depends_on": ["s"], "input_from": "s"}
  ]
}
```

```bash
curl -s -X POST https://magic-ai-factory.com/ai-market/pipelines \
  -H 'content-type: application/json' --data @blueprint.json
```

The response carries `trace_id`, the signed `bill_of_materials` and `final_result`.

## Where things live

| Path | What |
|------|------|
| [`hephaestus/src/catalog.ts`](https://github.com/alexar76/hephaestus/blob/main/src/catalog.ts) | Manifest → capability catalogue; the reputation rule |
| [`hephaestus/src/estimate.ts`](https://github.com/alexar76/hephaestus/blob/main/src/estimate.ts) | Cost and latency estimate |
| [`hephaestus/src/blueprint.ts`](https://github.com/alexar76/hephaestus/blob/main/src/blueprint.ts) | Validation; blueprint → `PipelineRequest` |
| [`hephaestus/src/wizards.ts`](https://github.com/alexar76/hephaestus/blob/main/src/wizards.ts) | Goals → roles → a chain over today's catalogue |
| `alien-monitor/backend/hephaestus_status.py` | Polls runs + catalogue readiness for the node |
| `alien-monitor/frontend/src/components/HephaestusRuns.tsx` | The observation panel |
| `web/backend/services/ai_market_protocol/pipelines.py` | Executor, trace store, projection |

The core is dependency-free and DOM-free on purpose: it has to serve the studio page and any other
surface that needs to cost or convert a blueprint, so it cannot carry a UI framework's opinions.

```bash
cd hephaestus && npm install && npm run check    # types + 57 tests
```

## Limits worth stating plainly

* An estimate is not a quote. Prices come from a signed manifest at read time and a provider may
  reprice before a run.
* `reputation_basis: measured` means someone invoked the capability through *this* hub, over 30
  days. It is evidence, not a guarantee.
* A signed bill of materials proves what this executor recorded. It does not prove the result was
  correct — that is what the verification tier is for.
