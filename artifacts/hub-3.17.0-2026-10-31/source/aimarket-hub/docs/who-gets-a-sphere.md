# Who gets drawn on the map, and how to be one of them

> ## ⚠️ DISCLAIMER — READ THIS FIRST
>
> **Your hub declares. The viewer's monitor decides.**
>
> A hub must publish everything it knows, faithfully — every provider, every peer, every
> hub it has merely heard of. What deserves to be *drawn* is a different question, and it
> belongs to whoever is looking. A monitor draws a node when there is evidence that the
> node is part of the economy, and evidence is not a claim: it is a capability in a signed
> catalogue, a transaction in the viewer's own records, or an address the viewer checked
> against the chain themselves.
>
> **So a node of yours can be missing from someone else's map while being perfectly
> configured.** That is not a bug in the map and not a fault in your hub. It means the
> viewer, two hops away, has no evidence yet — and the fix is to give them some, not to
> ask them to trust you. This page is the list of ways to do that.
>
> Nothing here affects **your own** map. A hub always draws what it itself deploys.

## The rule, in three tiers

The line falls at the second hop.

| Distance | Who that is | Drawn? |
|---|---|---|
| **hop 0** | this deployment's own hub and its own providers | **always** — we show what we run |
| **hop 1** | a hub we federate with, or one knocking for admission | **always** — see below |
| **hop 2** | somebody else's provider or peer, reached only through them | **only with evidence** |

**Every hub is always drawn.** A hub is a routing relationship, not a shop window: zero
capabilities can be entirely correct (an aggregator whose catalogue is all re-exports
filters to zero), and a hub awaiting admission is empty *because* it is waiting. "Who is
out there" is the question the map exists to answer.

**A hub's peers are not.** At the second hop the map is repeating what a stranger told it,
about a node it cannot reach, cannot poll and has no records of. Drawing that unconditionally
is how a map fills with names nobody can act on.

## The three ways a second-hop node earns its sphere

Any **one** of these is enough. They are ORs, not ANDs.

### 1. It supplies — it offers at least one capability

The test is the **catalogue**, never the revenue.

> **A free capability counts exactly as much as a paid one.** `access_mode:
> public_free` at price `0.00` is participation: something is being given, and somebody
> can use it. A node that gives away one capability is drawn; a node that sells nine is
> drawn; the rule does not rank them.

This is the ordinary route. Publish one capability on your hub and your node is on every
map that reaches your hub.

### 2. It consumes — it has transacted with us

A node that appears as a `consumer_hub` in the viewer's own invocation feed is drawn even
with an empty catalogue. A service built on our tools that buys every hour and lists
nothing of its own is as much a participant as any seller — and hiding it would mean a
monitor hiding its own customers.

Evidence here is the viewer's own records, so nothing is required of you but to trade.

### 3. It settles on chain — a verified escrow or wallet

The route that does not depend on anybody's books.

A hub publishes the escrow it settles through and the wallet its invoices are paid to;
each hub re-exports what its peers declared; and the monitor **asks the chain**:

* a **contract** — does the address hold code? An escrow that was never deployed holds none.
* a **wallet** — has it ever transacted? On an EOA that is its nonce.

If either answers yes, the node is drawn — and the sphere opens onto those transactions, so
the reader can repeat the check instead of taking anybody's word for it.

> **Declared is not verified.** An address is a string anybody can publish. Until the
> monitor has confirmed it against the chain it reads, the node card says *declared, not
> verified* and the node earns nothing from it. A declaration for a chain the monitor
> cannot read is never assumed fine — it is reported as unchecked, because "we could not
> look" and "it is not there" are different statements.

## What your hub publishes about its own money, automatically

`/.well-known/ai-market.json` grows a `contracts` block:

```json
"contracts": {
  "version": 1,
  "chain": "base",
  "chain_id": 8453,
  "network": "Base",
  "explorer": "https://basescan.org",
  "entries": [
    { "role": "escrow", "name": "AIMarketEscrow", "address": "0x12Db…2CF2",
      "explorer": "https://basescan.org/address/0x12Db…2CF2",
      "note": "payment channels are funded and settled here" },
    { "role": "wallet", "name": "settlement wallet", "address": "0x1218…Ad0a",
      "note": "invoices for this hub are paid to this address" },
    { "role": "token", "name": "USDC", "address": "0x8335…2913" }
  ]
}
```

**There is nothing to configure.** The addresses are read from the payment configuration
and deployment registry the hub already runs with:

| Entry | Comes from | Published when |
|---|---|---|
| `escrow` | `AIMARKET_ESCROW_EVM_ADDRESS`, else the deployment registry for the active chain | there is one |
| `wallet` | `AIMARKET_PAYMENT_RECIPIENT` | **and** `payment_configured` is true |
| `token` | the active chain's USDC/USDT address | there is one |

So a hub that deploys an escrow starts declaring it on its next request, and a hub with
none stays silent. There is no switch to forget and no second place to update — which is
the only reason the declaration can be trusted to still be true after a redeploy.

Two things are deliberately **not** published:

* **The wallet, unless payments are actually verified on chain.** Same gate as
  `payment_configured`: a hub that credits any `tx_hash` without checking it has no
  business pointing at a wallet as though money arriving there meant something.
* **Anything in a sealed (`AIMARKET_CHAIN_REALM=uni`) realm that names a real asset.** A
  bubble publishes its own Anvil deployment, flagged `"simulated": true`, with no explorer
  links — `basescan.org/address/<anvil address>` is a real page about a chain that has
  never heard of your contract.

None of this is a new disclosure. The escrow address appears in every channel open, and
the recipient in every x402 `accepts[].payTo` your hub has ever answered with. Publishing
them only means a reader no longer has to buy something to learn them.

## What travels to a stranger, and what does not

```
your hub  ──declares──▶  a hub that federates with you  ──re-exports──▶  a monitor
   contracts: {...}          peers[].contracts: {...}         asks the chain
```

Re-export is automatic and re-read on **every** crawl. Deploy an escrow today and the hubs
that know you re-export it on their next pass; withdraw it and they stop. No operator
action at either end.

A peer's declaration is bounded and re-validated at every hop — at most 8 entries, real
EVM addresses only, `http(s)` explorer URLs only — on the publishing side *and* again in
the monitor. A validator that only runs where the data is written is not a validator.

## Reading the transactions

Every declared address on a node card carries two links:

* **view transactions →** — this monitor's own scanner (`/api/chain/address/<addr>`),
  which works inside the bubble too, where no public explorer exists at all;
* **explorer ↗** — the public block explorer, when the chain has one.

## The deliberate exception

A rule needs an override, or the first legitimate exception becomes a reason to delete the
rule. On the monitor:

```bash
ALIEN_KEEP_SILENT_NODES=fedchild:https://example.dev,fedchild:https://other.dev
```

Exact node ids, comma-separated. Those nodes are drawn whatever the rule says.

Omissions are never silent either way: every tick that drops a node logs its id and the
count, so "the map is not showing X" always has an answer in the log.

## Checklist — making your node appear on other people's maps

- [ ] at least one capability published on your hub (a **free** one is enough), **or**
- [ ] you invoke capabilities from the hub whose viewer you want to appear on, **or**
- [ ] an escrow deployed and `AIMARKET_ESCROW_EVM_ADDRESS` set — verifiable on a public chain
- [ ] `payment_configured: true` if you want your wallet published as well
- [ ] `curl https://your.hub/.well-known/ai-market.json` from **another** machine shows a
      `contracts` block with the addresses you expect
- [ ] each of those addresses opens on a public explorer and shows what you expect
- [ ] your hub's public address is set (`AIMARKET_HUB_URL`), or nothing above is reachable

## Related

* [ecosystem-declaration.md](./ecosystem-declaration.md) — declaring your providers so
  they display with usable addresses.
* [federation-admission.md](./federation-admission.md) — how a peer hub is admitted.
* [federation-peer-keys.md](./federation-peer-keys.md) — how peer identity is pinned.
