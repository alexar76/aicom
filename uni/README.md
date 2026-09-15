# The bubble's own ecosystem

> **UNI only.** These six labs federate into `https://uni.modelmarket.dev`. They are not LIVE
> catalogue peers. LIVE is `https://modelmarket.dev`. Split:
> [docs/uni-and-live.md](../docs/uni-and-live.md).

UNI is a sealed parallel realm — its own Anvil chain, its own contracts, a USD-pegged token
funded from nowhere — and its premise, stated by the owner, is that *from the inside it is
indistinguishable from the live economy and there is no way out of it*.

It failed the first half of that on the most visible possible axis. The live hub is a pure
federation index: **99 capabilities, 0 local, 99 federated from 7 sources**. The bubble had
**one** locally published capability and no peers at all. Anything inside could tell where it
was by reading the catalogue.

This is the fix: one program, `satellite.py`, instantiated six times with different
catalogues, giving **91 federated capabilities across 6 sources**.

| satellite | product | caps | what it sells |
|---|---|---|---|
| KHRONOS Time Series | `khronos` | 20 | descriptive statistics, smoothing, decomposition, forecasting |
| STOICHEION Data Hygiene | `stoicheion` | 17 | schema inference, structural diffs, profiling, text metrics, units |
| HORIZON Geo & Telemetry | `horizon` | 17 | geodesy, spatial queries, sensor transforms |
| PSEPHOS Draws & Ballots | `psephos` | 13 | reproducible draws with commitments, exact discrete probability, ballots |
| KYMA Signal Lab | `kyma` | 12 | spectra, filtering, waveform measurement |
| DIKTYON Graph Metrics | `diktyon` | 12 | centrality, connectivity, ordering, spanning structure |

## The rule everything here follows

**Every capability is a pure function of its input, computed with the standard library.** No
network, no model, no lookup table, no canned string. That is not a limitation the simulation
imposes — it is what makes the results real inside it. Only the money is simulated.

Where a formula has more than one convention (sample vs population variance, quantile
interpolation, tie handling in a rank correlation, what "noise" means in a signal-to-noise
ratio) the choice is named in the output, because a consumer comparing two providers needs to
know which one it asked for. Where a model has a validity range, going outside it is a
refusal rather than an extrapolation.

## Running one

```bash
UNI_SAT_CATALOGUE=khronos \
UNI_SAT_PUBLIC_URL=https://uni.modelmarket.dev/sat/khronos \
UNI_SAT_PORT=9301 \
UNI_SAT_KEY=/var/lib/uni-satellites/khronos.pem \
python3 -m uni.satellite
```

`deploy/uni-satellites.sh` does all six as systemd units with their nginx locations. It is
idempotent, and the keys in `/var/lib/uni-satellites` must survive: the hub **pins** a peer's
key on first contact and refuses it forever after if it changes.

## Why they are behind the hub's own public name

The crawler's SSRF guard rejects `127.0.0.0/8` and `172.16.0.0/12` outright — no env override,
no realm exemption — and the routed invoke takes the same check. The two documented
private-address escapes are honoured only for locally *published* capabilities, never for
federation. So a bubble peer on a private address can be neither crawled nor invoked. A path
under `https://uni.modelmarket.dev` resolves to a public address, which the guard accepts,
while the packets never leave the machine.

## What a satellite has to get exactly right

Four things, each of which fails silently — the hub indexes zero capabilities and says
nothing useful about why:

1. **The manifest canonical.** The hub hashes `tools` with plain `json.dumps(sort_keys=True,
   ensure_ascii=False)` and **default separators**. A compact dump produces a different digest
   and a signature that fails with "Invalid manifest signature" and nothing else.
2. **`source_hub: "local"` on every row.** The crawler indexes only what a peer originates; a
   row naming anyone else is a re-export and is dropped.
3. **Freshness.** `generated_at` is checked against a maximum age as replay protection, so the
   manifest is rebuilt per request rather than cached.
4. **Types.** `p50_latency_ms` is an integer in the schema — a float rejects the *whole*
   manifest — and `protocol_versions` is enum-restricted to `v1`/`v2`/`mcp`.

`tests/test_satellite.py` checks all four against the hub's **own** `Signer`,
`validate_well_known` and `validate_manifest`, rather than against a second reading of them.

## Tests

```bash
python3 -m pytest uni/tests/test_capabilities.py    # 400 — contract + known values
python3 -m pytest uni/tests/test_satellite.py       # 24 — protocol interop (needs the hub package)
```

The first half of `test_capabilities.py` proves each capability is well-formed: it runs, it is
deterministic, it refuses rubbish with a `ValueError` rather than a traceback, and its answer
survives a JSON round trip. That catches a broken capability but not a **wrong** one — so the
second half checks named results against values computed elsewhere: a distance between two
cities, a binomial probability, a PageRank vector with a closed form, a Condorcet cycle, a dew
point. A bubble whose arithmetic was merely plausible would be the exact thing the realm is
supposed not to be.

Adding a capability: write the function, declare its schemas and price, append it to its
catalogue. The generic tests then exercise it automatically — including its `example`, which
must actually run.
