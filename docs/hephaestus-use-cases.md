# HEPHAESTUS — use cases

> **Русский:** [hephaestus-use-cases.ru.md](./hephaestus-use-cases.ru.md) · **Español:** [hephaestus-use-cases.es.md](./hephaestus-use-cases.es.md) · **Français:** [hephaestus-use-cases.fr.md](./hephaestus-use-cases.fr.md) · **中文:** [hephaestus-use-cases.zh.md](./hephaestus-use-cases.zh.md)
>
> How to drive the page: [hephaestus-user-guide.md](./hephaestus-user-guide.md) · How it works inside: [hephaestus-studio.md](./hephaestus-studio.md) · **Install and screenshots:** [hephaestus/README.md](https://github.com/alexar76/hephaestus/blob/main/README.md)

---

Every chain below is built from capabilities that are on sale **today** — 76 rows across
GAIA, the oracle family and ATLAS — with the prices the live list actually publishes. The
JSON is what `Copy request` gives you, so each one runs from a terminal or an agent
unchanged.

---

## 1. A sensor reading you can defend

**Who for:** anyone whose decision rests on a number from someone else's device.
**Cost:** $0.0030 · **2 hops** · covered by the free tier.

A reading on its own is a claim. This chain buys the reading and then buys a second opinion
on it — from a statistical verifier that checks bounds, rate of change, and agreement with
sibling devices — and keeps a signed record of both.

```json
{"nodes": [
  {"id": "read", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
   "input": {}, "depends_on": [], "source_hub": "https://iot.modelmarket.dev"},
  {"id": "check", "product_id": "gaia.gateway", "capability_id": "gaia.verify@v1",
   "input": {"reading": "${read.reading}", "attestation": "${read.attestation}"},
   "depends_on": ["read"], "source_hub": "https://iot.modelmarket.dev"}
]}
```

What comes back is a verdict, not a vibe:

```json
{"verified": false, "score": 0.6667, "summary": "failed: sibling:pressure_hpa",
 "checks": [{"name": "known_device", "ok": true}, {"name": "device_attestation", "ok": true}]}
```

**Why it is worth money:** the verifier disagreed with the sensor, and said which check
failed. That is the difference between "we had a reading" and "we had a reading and knew how
much to trust it". This is the chain the studio opens on.

---

## 2. A draw nobody has to be trusted for

**Who for:** anyone running a lottery, an allocation, a random audit sample.
**Cost:** ~$0.0060 · **2 hops**.

`platon.random@v1` returns random bytes with a reproducibility proof and an Ed25519
signature; `chronos.eval@v1` is a verifiable delay function — proof that real sequential
time passed. Chaining them gives a draw that cannot be re-rolled after the fact and cannot
have been computed early.

```json
{"nodes": [
  {"id": "seed", "product_id": "prod-platon", "capability_id": "platon.random@v1",
   "input": {"num_bytes": 32}, "depends_on": [],
   "source_hub": "https://oracles.modelmarket.dev/family"},
  {"id": "delay", "product_id": "prod-chronos", "capability_id": "chronos.eval@v1",
   "input": {"seed": "${seed.random_hex}", "difficulty": 200},
   "depends_on": ["seed"], "source_hub": "https://oracles.modelmarket.dev/family"}
]}
```

**Why it is worth money:** publish the trace and the participants can check the draw
themselves. You are not asking to be believed.

---

## 3. Rehearsing the cost before committing to a design

**Who for:** whoever has to answer "what will this pipeline cost at a million calls?"
**Cost:** $0 — you never press Run.

Assemble the graph you are considering. The header gives the per-run price from the signed
list, split by hop, plus a floor on latency. Multiply by your volume. Swap a hop for a
cheaper provider and watch the number move.

Two things the estimate refuses to do, which is what makes it useful:

* an unpriced capability is **named**, never counted as free;
* money is summed in integer micro-dollars, because a catalogue of $0.001 reads does not
  survive floating-point addition intact.

**Why it is worth doing:** the answer is defensible. It comes from prices that a peer
signed, not from a spreadsheet someone typed.

---

## 4. Evidence for a dispute

**Who for:** anyone who pays several providers in one workflow.
**Cost:** the run you already made.

When a chain fails, the signed bill of materials names the hop at fault and **explicitly
clears** the hops that did their work:

```json
{"policy": "hop-level",
 "at_fault": {"id": "check", "capability_id": "gaia.verify@v1", "status_code": 500},
 "not_at_fault": ["read"], "not_executed": []}
```

Every hop also records who paid for it — `trial`, `channel` or `local` — so a free run is
never mistaken for a purchase.

**Why it is worth money:** without hop-level blame, a failed chain is one bill and an
argument. With it, the upstream provider is paid, the failing one is identified, and there
is a signed document to point at. The ecosystem's slashing ladder reads exactly this.

---

## 5. Finding out whether a capability is worth buying

**Who for:** an integrator choosing between offers.
**Cost:** free, within the allowance.

The catalogue publishes, per row: price, declared latency, whether it declares its
input/output at all, and how much evidence stands behind its reliability. Today that is
**27 rows with a measured success rate and 49 with none** — and the page says "no calls yet"
for the second group rather than showing a placeholder number as a score.

Add the row, fill its fields, run it once on the free tier, read the actual result. Then
decide.

**Why it is worth doing:** you evaluate on your own input, not on a demo the seller chose,
and you find out in a minute whether the schema matches reality.

---

## 6. Handing a graph to your own agent

**Who for:** anyone building an agent that should buy work rather than fake it.
**Cost:** whatever the graph costs, on your channel.

Build and check the graph by hand, press **Copy request**, and paste the JSON into your
agent. It posts the same body to the executor and gets back the same signed record. The
studio is where a person reasons about the shape; the agent runs it a thousand times.

```bash
curl -s -X POST https://magic-ai-factory.com/ai-market/pipelines \
  -H 'content-type: application/json' --data @graph.json
```

**Why it is worth doing:** the thing you tested is byte-for-byte the thing that runs.

---

## What this is not for

* **A general workflow engine.** There are no loops, branches, retries, or HTTP nodes, and
  adding them would trade away the only advantage here — every node is a priced, verifiable
  market row.
* **A data-transformation tool.** Values are threaded between hops with `${hop.field}`, not
  reshaped. Transformation belongs in a capability someone sells.
* **A place to keep secrets.** Fields travel to the provider. Do not type anything into a
  field that you would not hand to that provider directly.
* **Proof that an answer is true.** A signed record proves what the executor did. Whether the
  result is correct is what a verification hop is for — see the first use case.
