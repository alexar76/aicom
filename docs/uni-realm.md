# The UNI realm — a sealed parallel economy

> **This page is UNI.** LIVE is a different hub and a different map. Split: [uni-and-live.md](./uni-and-live.md) (EN · [RU](./uni-and-live.ru.md) · [ES](./uni-and-live.es.md) · [FR](./uni-and-live.fr.md) · [ZH](./uni-and-live.zh.md)).

UNI is not "crypto off". It is a chain of our own — Anvil, chain id 31337, our contracts, a
USD-pegged token funded from nowhere — and its point is that **from inside it is
indistinguishable from the live economy, and there is no way out of it.**

Those are two different promises, and only one of them is absolute.

| | Promise | How it is kept |
|---|---|---|
| **No escape** | absolute | `aimarket_hub/realm.py` refuses, at boot and on every network resolve, any configuration that names a real chain, a real contract, a real token or a public RPC |
| **Indistinguishable** | behavioural | display names, API shapes, receipts, gates and flows are identical; nothing in any public payload says "uni" |

What is deliberately **not** claimed: hiding the chain id. Anyone who signs anything needs
it — it is inside the EIP-712 domain separator — so a participant can always read which
chain they are on. That same field is what makes the two realms non-interchangeable by
arithmetic: a signature made for 31337 is invalid on 8453 and the reverse.

## What the seal refuses

Turn it on with `AIMARKET_CHAIN_REALM=uni` (default is `live`, so nothing changes for an
existing deployment). Inside the bubble:

- the network preset's **public RPC list is dropped**, not filtered, and the chain id is
  forced to `AIMARKET_UNI_CHAIN_ID` (31337);
- the auto-loaded **mainnet address table is dropped** — `deployments/base-mainnet.json`
  otherwise supplies real Base contracts the moment crypto is enabled;
- a **public RPC** in the configuration is a startup refusal;
- a **real token address** is a startup refusal (Base/Sepolia USDC, Ethereum USDC/USDT);
- **x402 advertises nothing** until `AIMARKET_X402_ASSET` names a bubble-local token, and
  its CAIP-2 id is derived from the private chain id rather than read from the table;
- no **ERC-8004 declaration** is published: its registries live on a real chain.

Two of those were live leaks. `chain_net` really did default `base` to four public endpoints
plus real mainnet contracts, and the x402 asset table really did hard-code Base mainnet USDC
with `eip155:8453` — so a 402 issued inside a bubble was a payment offer valid on mainnet,
and an inside agent holding a funded real key could have signed it.

The seal is **symmetric**: a `live` realm refuses a private chain id and a loopback RPC,
because a live hub reading a simulated chain would report simulated money as real.

Guarded by `aimarket-hub/tests/test_realm_seal.py` — every test in it is an escape attempt.

## Why the bubble runs production mode

Two guards refuse an Anvil address as a settlement recipient — `payment_readiness` (which
reports) and the CLI's own boot check (which refuses to start). Correct on a live hub: that
key is public. Inside the bubble **every** address is an Anvil address, so the same rule
would have forced UNI into a demo shape that behaves differently from LIVE — and a
simulation that relaxes the rules it simulates is not one. Both guards now carry the realm
exemption; both, because a second copy of a guard is exactly what this codebase has been
bitten by before.

The bubble therefore runs `AIFACTORY_PROD=1`, `AIFACTORY_PAYMENT_VERIFY_STUB=0` and
`AIMARKET_ALLOW_DEMO_CREDIT=0`: deposits are verified on its own chain, for real.

## Standing it up

```bash
# 1. the bubble's own chain — NOT the alien-monitor demo chain on 8545 (see the warning below)
docker run -d --name anvil-uni --restart unless-stopped \
  -p 172.17.0.1:8546:8545 -v anvil_uni_state:/state \
  --entrypoint anvil alien-monitor:local \
  --host 0.0.0.0 --port 8545 --chain-id 31337 --accounts 20 --balance 1000 \
  --mnemonic "test test test test test test test test test test test junk" \
  --state /state/anvil-state --silent

# 2. its economy: a USD-pegged EIP-3009 token and an escrow with the hub authorised
UNI_RPC=http://172.17.0.1:8546 python3 scripts/deploy_uni_realm.py

# 3. the hub, loopback-only, pointed at both
bash deploy/uni-hub.sh <hub-image> <token-address> <escrow-address>
```

`deploy/uni-rpc-bridge.py` (a systemd unit) exposes the chain on the docker bridge address
only — containers cannot reach the host's loopback, and binding Anvil to `0.0.0.0` would
break the seal from the outside: anyone could then mint the bubble's dollars, and a
simulation anyone can join is not sealed. `deploy/uni-provider-example.py` is a provider that
signs its responses the way the production policy demands.

**Isolation is also a deployment property**, and the deployment moved. The bubble hub now
answers on `https://uni.modelmarket.dev` — still bound to `127.0.0.1:9183`, reached only
through nginx. Every amount it reports is virtual, so what protects the reader is the
*name*: a separate subdomain, never a path under the live host. Nothing in the payloads
says "uni", because the invariant is that from the inside the two are indistinguishable.

Publishing it changed three things, and each was a real exposure rather than a precaution:

- **the advertised address.** The manifest still named `http://127.0.0.1:9183`, which for
  any caller but the host means *their own* loopback. Now `AIMARKET_HUB_URL` is the public
  name — `name` stays `modelmarket.dev`, identical to live, on purpose.
- **the admin token.** It was `uni-admin-token-not-a-secret-in-a-bubble` — fine while
  nothing could reach the port, an open operator surface the moment something could.
  Rotated to a random secret held only on the host.
- **what an anonymous caller can do.** Verified after exposure: crawl, peer approve, peer
  delete and account credit all answer `401`; signup succeeds but grants `$0`, and funding
  needs a deposit on the bubble chain, which is bound to the docker bridge and unreachable
  from outside. So the world can read the bubble and cannot spend in it.

The observation deck is the exception that proves the rule. The universe map links *out* to
this hub, and the two maps link to each other, because an operator standing outside is
entitled to see both worlds. That link deliberately does not exist inside the bubble hub:
a "back to live" link served by the bubble itself would be a door in the wall.

## The bubble's own ecosystem

The live hub hosts nothing: 99 capabilities, **0 local**, 99 federated from 7 sources. The
bubble had one locally published capability and no peers at all — which is the most obvious
way to tell the two apart from the inside, and the invariant is that you cannot.

`uni/` is the bubble's answer: one program (`uni/satellite.py`) instantiated six times with
different catalogues, giving **91 federated capabilities across 6 sources**. Everything they
sell is a pure function of its input computed from the standard library — real statistics,
real signal processing, real graph metrics, real geodesy, real discrete probability. That is
not a limitation the simulation imposes; it is what makes the results real inside it. Only
the money is simulated.

| satellite | capabilities | what it sells |
|---|---|---|
| KHRONOS | 20 | descriptive statistics, smoothing, decomposition, forecasting |
| STOICHEION | 17 | schema inference, structural diffs, profiling, text metrics, units |
| HORIZON | 17 | geodesy, spatial queries, sensor telemetry transforms |
| PSEPHOS | 13 | reproducible draws with commitments, exact discrete probability, ballots |
| KYMA | 12 | spectra, filtering, waveform measurement |
| DIKTYON | 12 | centrality, connectivity, ordering, spanning structure |

**Why they live on paths under the hub's own name.** The crawler's SSRF guard
(`crawler._is_private_url`) rejects `127.0.0.0/8` and `172.16.0.0/12` outright — no env
override, no realm exemption — and the routed invoke takes the same check, because `api.py`
calls `safe_post` without `invoke=True`. The two documented private-address escapes
(`AIMARKET_ALLOW_LOCAL_PUBLISH`, `AIMARKET_INVOKE_HOST_GATEWAY`) are honoured only for
locally *published* capabilities, never for federation. So a bubble peer on a private address
can be neither crawled nor invoked. Giving each satellite a path under
`https://uni.modelmarket.dev` makes the host resolve to a public address, which the guard
accepts, while the packets never leave the machine — the same compromise the bubble hub
already makes, and it weakens no security control. Stood up by `deploy/uni-satellites.sh`.

## The two doors the chain seal never covered

Populating the bubble found both. Neither was a chain leak, which is all `realm.py` had ever
been asked to watch.

**The seed list named the real world.** `deploy/uni-hub.sh` set `AIMARKET_SEED_LIST=` — an
empty value — and `config._parse_seed_list` treats an empty variable as *unset*, falling back
to the committed `federation_seeds.json`: the six real satellites, **with pinned public keys
that grant trusted-and-indexed on first contact, with no approval step**. Two consequences,
both live at the time:

- the bubble published those hostnames in its own `/.well-known/ai-market.json` under
  `federation.seed_list`. An agent inside could read the exact addresses of the world outside
  it. Verified on the running deployment before the fix.
- one operator crawl would have indexed real, priced, outside-reachable endpoints into the
  bubble's catalogue, and a bubble invoke would then have routed real money to a real
  provider.

Now `realm.check_seed` refuses at startup, in both directions: inside UNI a seed must name a
host the bubble itself answers on (`AIMARKET_HUB_URL`, plus anything explicit in
`AIMARKET_UNI_FEDERATION_HOSTS`), and the committed seed file is **dropped, not filtered** —
it is the live ecosystem's address book and nothing in it can ever be inside a bubble.
Symmetrically, a `live` realm refuses a private seed. Guarded by the new escape attempts in
`aimarket-hub/tests/test_realm_seal.py`.

**The economics were broker-shaped, so nothing was charged.** For a federated capability the
hub charges what the *peer* reports in its response, unless the hub is declared the seller of
record. The satellites do not bill — there is no 402 anywhere in `uni/satellite.py` — so 51
successful "paid" invokes cost the buyer **$0.00** while every one advertised a price. This is
the same defect `config.sells_on_behalf_of` documents for the live oracle family, and the same
fix: `AIMARKET_SELLS_FOR` names them, and the hub holds and captures the full list price. It
must be declared and never inferred — "the peer answered 200" does not mean the peer did not
charge, and billing then would charge the buyer twice.

One pointer still leaves the bubble by design: provenance receipts carry
`verifier_url: https://verify.modelmarket.dev` (`AIMARKET_VERIFY_DOMAIN`). It is an offline,
stateless verifier — it needs nothing from the hub, tells the hub nothing, and checks a
signature that is self-contained — so it is a route to a page, not a route to spend. Pointing
it at a bubble-local path would only produce a dead link. Named here rather than left to be
discovered.

## What real trade proved

The catalogue's numbers are only worth anything if they were earned. The crawler **discards**
a peer's self-declared success rate and trust score and hard-sets 0.5; the hub reports
`reputation_basis: "unobserved"` until it has recorded invocations of its own. After 208
invocations across the whole catalogue: **89 of 92 capabilities "measured"**, peer trust
0.265–0.44 with `trust_basis: "measured"`, 100% success, $0.73 of credits earned against
$0.688 operator net and $0.042 in publisher payouts.

A response-safety false positive surfaced on the way and it was not a bubble problem. The PII
pattern makes its separators optional, so a six-decimal float reads as a social security
number: `343.556535` is `\d{3}` `343`, `[-.]` `.`, `\d{2}` `55`, `\d{4}` `6535`. A
great-circle distance in kilometres was refused as "Response may contain PII", refunded, and
recorded as a provider failure — every capability returning coordinates, distances, rates or
probabilities was affected, on both realms. Fixed in `safety_gate` by excluding non-integral
numbers from the PII projection only; a nine-digit integer is still scanned, because that one
really can be an SSN.

## Two warnings paid for in advance

**Do not share the alien-monitor demo chain.** Its policy is to wipe the chain and redeploy
when its Anvil state passes 64MB (`ALIEN_ANVIL_STATE_MAX_MB`) — reasonable for a disposable
demo, fatal for an economy with deployed contracts. That state was at 61MB when the bubble
was built, three megabytes from deleting it. Hence a dedicated chain, and hence
`scripts/deploy_uni_realm.py` being a single command.

**Run the bubble chain without `--block-time`.** The shared chain mines an empty block every
two seconds, which is what grew its state file to 61MB while nothing was happening; an
earlier instance reached 1.73GB and starved the host. Mining on demand keeps the file
proportional to actual activity.

## What running it found

Exercising the bubble surfaced two defects in code the live deployment never reaches:

- **the escrow bridge's env-key signer could not sign at all.** `eth-account` refuses a `to`
  address that is not EIP-55 checksummed, and every address on that path arrives lowercase.
  It surfaced as `signing failed (TypeError)` — a message that hides the payload on purpose
  and hid the cause with it. Live collection goes through an external policy signer, so the
  env path had never run. Fixed, with `tests/test_escrow_bridge_signer.py`.
- **the publish gate and the invoke gate disagreed.** The invoke path honours
  `AIMARKET_INVOKE_HOST_GATEWAY`; publishing knew only about loopback, so a hub could be
  configured to *call* an address it was forbidden to *list*, and the error never said why.

And it confirmed one guard works exactly as designed: an authorization whose invoke failed
is refused at collection time — *"the channel ledger has no debit for this receipt — refusing
to collect a charge the hub cannot show it made."*
