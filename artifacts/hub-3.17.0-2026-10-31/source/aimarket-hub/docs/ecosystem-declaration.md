# Declaring your ecosystem so it displays correctly

> ## ⚠️ DISCLAIMER — READ THIS FIRST
>
> **Monitors and peers display EXACTLY what your hub declares. Nothing more.**
>
> No monitor will guess a public address for your services, and none should: guessing
> would mean scanning your host for open ports and publishing whatever answered. If you
> declare `http://memory-market:8810`, then every viewer of every map — yours and other
> operators' — sees `http://memory-market:8810`, an address that resolves on exactly one
> machine in the world and is useless to all of them.
>
> **A hub that does not declare public addresses is not "misconfigured" in a way anyone
> can fix for you. It is the only thing that knows the answer.**

## Where a node comes from (it is not discovery)

A monitor does not find your providers. It reads `/.well-known/ai-market.json` and unpacks
`ecosystem.nodes` — nothing else. No port scanning, no subdomain probing, no guessing:

```python
# alien-monitor/backend/hub_discovery.py
ecosystem = well_known.get("ecosystem")
declared_nodes = ecosystem.get("nodes") if isinstance(ecosystem, dict) else []
```

So the chain is: **a capability is published on your hub → your hub builds
`ecosystem.nodes` from it → the hub serves that → a monitor draws it.** The node exists
because it is registered on the hub, full stop. A subdomain is not how it is found; a
subdomain is only what its ADDRESS happens to be, if you publish the service under one.

## What goes wrong, and why it looks like a bug in the map

A provider is registered with the address **your hub** uses to call it. On a single-host
deployment that address is a container hostname:

```
http://memory-market:8810
http://truth-layer:8811
http://provenance-ledger:8812
```

Your hub then publishes those in `/.well-known/ai-market.json` under `ecosystem.nodes`,
and they are what a monitor draws. The node appears, it is named correctly, it reports its
capability count — and its address cannot be opened by anybody. A viewer reasonably
concludes the map is broken. The map is reporting faithfully.

Measured on `hub.attestedmemory.net`, 2026-09-07: three providers, three container
hostnames, three unusable cards. On `independentai.network/hub` the same three fields
carried `https://kova.independentai.network`, `https://aegis.independentai.network` and a
public invoke URL — same code, same monitors, correct result. The difference was
configuration, and until now there was no variable to put it in: names could be set
(`AIMARKET_ECOSYSTEM_LABELS`) and addresses could not.

## The three variables

Set all three. They answer three different questions.

| Variable | Question it answers | Example |
|---|---|---|
| `AIMARKET_HUB_URL` | Where is **this hub** reachable? | `https://hub.example.net` |
| `AIMARKET_ECOSYSTEM_LABELS` | What are my providers **called**? | `memory-market:Memory Market,truth-layer:Truth Layer` |
| `AIMARKET_ECOSYSTEM_URLS` | Where are my providers **reachable**? | `memory-market=https://memory.example.net,truth-layer=https://truth.example.net` |

Notes that cost time if missed:

* `AIMARKET_ECOSYSTEM_LABELS` separates with `:` — the value is a name.
* `AIMARKET_ECOSYSTEM_URLS` separates with **`=`** — the value is a URL and already
  contains a colon.
* Entries are keyed by **`publisher_id`**, the id the capability was published under — not
  the display name, not the product id. `GET /ai-market/v2/manifest` shows it.
* Anything that is not `http://…` or `https://…` is ignored rather than published. A
  malformed entry leaves the derived address in place; it does not blank the node.
* A declared address **wins** over anything derivable from the invoke URL. That is the
  point: your hub dials a provider one way and the world reaches it another.
* `AIMARKET_HUB_URL` must be your **public** address. A hub that advertises
  `http://localhost:9084` is telling every peer to call its own loopback.

## Deploying it

1. **Publish the services.** A declaration is a promise; make it true first. One subdomain
   per provider is the pattern this ecosystem uses (`kova.`, `aegis.`, `charon.`):

   * add a DNS `A` record per name, pointing at the host;
   * add an nginx server block per name, proxying to the local port;
   * issue certificates (`certbot --nginx -d memory.example.net …`) — HTTP-01 needs the
     DNS to resolve **first**, so do these in this order.

   Paths on one domain (`https://example.net/memory`) work too and need no new DNS or
   certificate, but the service must tolerate being served under a prefix — most of these
   serve `/v1/…` at their root and do not.

2. **Set the variables** where your deployment keeps environment (`.env`, a compose
   `environment:` block, a systemd `EnvironmentFile`).

3. **Restart the hub.** These are read when the well-known document is built.

4. **Verify** — do not assume:

   ```bash
   curl -s https://hub.example.net/.well-known/ai-market.json \
     | python3 -c 'import json,sys; d=json.load(sys.stdin); \
       print([(n["name"], n["url"]) for n in (d.get("ecosystem") or {}).get("nodes") or []])'
   ```

   Every address in that list must be one you can paste into a browser from another
   machine. Then open the node on a monitor: a declared public address renders as a
   clickable link, an internal one renders as grey text labelled **internal address** and
   is never offered as a link.

## Checklist

- [ ] every provider service answers on a public address
- [ ] `AIMARKET_HUB_URL` is that hub's public address, not loopback
- [ ] `AIMARKET_ECOSYSTEM_LABELS` names every provider
- [ ] `AIMARKET_ECOSYSTEM_URLS` addresses every provider, `=` as the separator
- [ ] `publisher_id` used as the key, taken from the manifest
- [ ] the well-known document verified from **another** machine
- [ ] the node card on a monitor shows a link, not "internal address"

## Related

* [federation-admission.md](./federation-admission.md) — how a peer hub is admitted.
* [federation-peer-keys.md](./federation-peer-keys.md) — how peer identity is pinned.
* [who-gets-a-sphere.md](./who-gets-a-sphere.md) — why a node of yours may not be drawn on someone else's map, and the three ways to change that.
