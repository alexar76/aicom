# The hosted MCP endpoint — `https://modelmarket.dev/mcp`

> ### 🟢 One URL. No wallet, no Docker, no clone.
>
> ## &nbsp;&nbsp;&nbsp;`https://modelmarket.dev/mcp`
>
> Paste it into any MCP client and the marketplace becomes two tools: **`market_search`**
> to find a capability, **`market_invoke`** to run one and get back the hub's **signed
> receipt**. **A few trial invokes per caller are free.** When the allowance is spent the
> hub answers **402** and the on-chain escrow path begins.

This is the shortest path from "never heard of this" to "I just invoked something on a
live agent marketplace and hold a signed receipt for it". Everything else in the
ecosystem — the factory, the oracles, the escrow, the verifier — is reachable from behind
that one paste.

---

## Add it to your client

**Claude Desktop / Claude Code** — `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aimarket": {
      "type": "streamable-http",
      "url": "https://modelmarket.dev/mcp"
    }
  }
}
```

**Cursor** — `.cursor/mcp.json`, same shape. **Any other client**: it speaks
Streamable-HTTP MCP (JSON-RPC 2.0 over `POST`, SSE `data:` framing, `Mcp-Session-Id`),
protocol version `2025-03-26`.

A GET with `Accept: text/event-stream` answers **405** — this endpoint offers no
server-initiated stream, and 405 is what the spec says to reply so a client stops looking
for one. A plain GET returns an info document instead, for humans and monitoring.

**By hand**, to see it work before trusting it with a config file:

```bash
curl -s https://modelmarket.dev/mcp
```

```bash
curl -s -X POST https://modelmarket.dev/mcp -H 'content-type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

---

## The trial, precisely

> ### ⚠️ The allowance is per caller, and it is small on purpose
> **Three invokes** per caller as of this writing — the hub publishes the live number as
> `free_trial.max_invokes_per_visitor` in
> [`/.well-known/ai-market.json`](https://modelmarket.dev/.well-known/ai-market.json), which
> is the value to trust. It is keyed on an opaque digest of the caller's address; the
> address itself never reaches the hub's ledger. Spend them on something you actually want
> to see. After that every invoke answers **402** with the price, and paying means opening
> an escrow channel on Base.
>
> **Free capabilities do not touch the allowance** — the trial identity is attached only to
> priced ones. The hub consumes a trial before it ever looks at the price, so sending it
> unconditionally would both cap free capabilities at three calls and replace the eventual
> 402 with a `429 trial_quota_exhausted` that carries no price at all.

Why so little? Because the wallet friction downstream is deliberate — this is a
crypto-native circuit and the trial is a taste, not a free tier. What the trial has to
prove is only that the thing is real: a capability executed, and a receipt you can verify
against the hub's published key at
[verify.modelmarket.dev](https://verify.modelmarket.dev).

Two things follow from one process serving everybody, and both are load-bearing:

| | why it matters |
|---|---|
| **identity per caller** | one shared identity would spend the entire allowance on whoever arrived first, and 402 every stranger after — a reachable endpoint that demos nothing |
| **address only from a trusted hop** | a forwarding header from an unlisted peer is ignored, so the allowance cannot be farmed by rewriting one request header |

Both are pinned by tests in `aimarket-hub/tests/test_mcp_gateway.py`; the same properties
for the self-hosted gateway are pinned in `aimarket-mcp/tests/test_hosted.py`.

---

## Using it

`market_search` first — it returns the `source_hub` each capability lives on, and
`market_invoke` needs that value verbatim for anything the hub does not execute itself.
Most of the catalogue is federated, so an invoke without it looks locally and answers 404.

```
market_search  { "intent": "verifiable random number", "budget": 0.05 }
market_invoke  { "product_id": "prod-platon",
                 "capability_id": "platon.oracle@v1",
                 "source_hub": "https://oracles.modelmarket.dev/family",
                 "input": {} }
```

The invoke returns the capability's output plus a receipt nonce. Paid callers pass
`payment_channel` (+ `payment_channel_secret`, and `payment_authorization` for escrow
channels) and are never placed on the trial tier.

---

## Two paths, one protocol

| | `https://modelmarket.dev/mcp` | `pip install aimarket-mcp` |
|---|---|---|
| install | none | a package, or a container |
| tools | `market_search`, `market_invoke` | those two plus `web_fetch`, `web_search`, `metis_verify` |
| hub | this one | any, via `AIMARKET_HUB_URL` |
| trial identity | derived per caller | one per installation |
| for | trying it, and agents that just want the market | self-hosting, and pointing at your own hub |

`https://modelmarket.dev/ai-market/mcp` is the same gateway under its older path. It stays
because peers read it out of `mcp_endpoint` in the well-known manifest; humans should be
given the short one.

---

## Operating it

The endpoint is the hub itself — no separate service, port, container or certificate.
`aimarket_hub/mcp_gateway.py` is mounted twice by `create_app`: once under `/ai-market`
for peers, once at the apex for people.

**Deploy** is therefore just a hub deploy. Use
[`scripts/deploy_hub_rebuild.sh`](../scripts/deploy_hub_rebuild.sh) on the hub host: it
copies the live container's environment into the new one, refuses to start if the payment
interlock did not survive the copy, verifies `/mcp` and `payment_configured` before
declaring success, and rolls back automatically if either fails. That refusal exists
because a hub redeploy has twice silently switched payments off
([`payment-enable-runbook.md`](payment-enable-runbook.md)).

**Watch it** with [`scripts/payment_canary.py`](../scripts/payment_canary.py), which
asserts from outside that a priced capability still answers 402, that the manifest still
says `payment_configured`, and that `/mcp` still answers with a per-caller trial:

```bash
scripts/payment_canary.py --publish /var/www/verify.modelmarket.dev/status.json
```

Exit **1** means a critical check failed; exit **2** means the report could not be
published (a missing directory must not read like a payment regression, since cron sees
only the code). Stdlib only — no venv needed on the host.

It probes the cheapest priced capability **of each provider**, because enforcement is not
one switch: `AIMARKET_SELLS_FOR` decides it per federated peer and the local branch has a
gate of its own. Probing one capability is how a $0.03 atlas capability came to be served
free while the oracle family was correctly answering 402.

It also probes **each peer's liveness**, separately, because the payment checks are
structurally blind to it — the hub answers 402 before it ever contacts the provider, so a
priced capability reads as perfectly gated while the satellite behind it is down.

> ### 🔴 A served manifest is not a live satellite
> On 2026-08-16 GAIA answered `/.well-known/ai-market.json` with a clean 200 while its
> invoke endpoint hung. Every gaia capability returned 502 through the hub for the whole
> outage, and a manifest-only check would have called it healthy. The liveness probe
> therefore asks the peer's own `/ai-market/v2/invoke` for a capability that cannot exist:
> any HTTP answer means the service is serving, and only silence counts as dead. It is
> retried once, so a single blink does not page anyone.
>
> It deliberately does **not** use the `mcp_endpoint` the peer advertises. Trusting that
> value reported three healthy peers as dead, because magic-ai-factory.com publishes
> `http://localhost:9080/…` to the whole internet — the probe dialled its own machine. That
> advertisement is itself reported, as a warning: no peer can route an invoke to it.

Peers that carry priced capabilities fail the run; the rest only warn. The published JSON
carries a `peers` array alongside the prose checks, so a dead satellite names exactly one
host — the shape a node agent's allowlisted restart command already takes.

To install it on the hub host — copy the script beside the build tree first, then schedule
it (`MAILTO` matters: on a box with no mail transport the output goes nowhere):

```bash
scp scripts/payment_canary.py my-vps:/root/aicom-hub-build/payment_canary.py
```

```bash
ssh my-vps "( crontab -l 2>/dev/null; echo 'MAILTO=you@example.com'; echo '17 6 * * * /usr/bin/python3 /root/aicom-hub-build/payment_canary.py --publish /var/www/verify.modelmarket.dev/status.json' ) | crontab -"
```

Once a day is the right cadence: the failure it watches for is introduced by a redeploy,
not by traffic, and a check that runs constantly is a check whose mail gets filtered.

> ### 🔴 `payment_configured: true` is not evidence that anyone is being charged
> Those two facts came apart once already — the flag was true while forty-two federated
> capabilities were free to call. The canary probes behaviour, not the manifest's opinion
> of itself, and its tests in `tests/test_payment_canary.py` assert that a hub serving paid
> work for free **fails** the check.

### Configuration

| variable | where | effect |
|---|---|---|
| `AIMARKET_TRUSTED_PROXIES` | hub | which peers may name a caller, matched by **exact string**. Unset means every limit keys on the peer the hub sees — the whole internet in one bucket, and one shared trial identity. In a container the peer is the **docker bridge gateway**, not `127.0.0.1`: `scripts/deploy_hub_rebuild.sh` reads it from `docker network inspect` and sets both. |
| `AIMARKET_INTERNAL_BASE` | hub | where the MCP gateway posts its own invoke. Loopback (`http://127.0.0.1:9083`) on purpose: routed through the public URL, nginx appends its own hop and the caller the gateway named is discarded. |
| `AIMARKET_MCP_PUBLIC` | self-hosted `aimarket-mcp` only | explicit opt-in that lets a production deployment answer anonymous callers. Production without it stays fail-closed. |
| `AIMARKET_MCP_TRUSTED_PROXIES` | self-hosted `aimarket-mcp` only | same idea, and **loopback only by default**. A containerised deployment behind nginx must name the bridge gateway (`172.17.0.1`, or its CIDR); trusting the private ranges by default would let any host on the same network name any caller. |
| `AIMARKET_MCP_VISITOR_SALT` | self-hosted `aimarket-mcp` only | pin it to keep trial allowances across restarts; unset re-rolls them on every boot. |
