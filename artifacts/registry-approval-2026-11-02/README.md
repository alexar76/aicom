# registry.modelmarket.dev approved as a peer (2026-11-02, about 04:08Z)

Owner: «Да, одобряй».

**Why the assay could not pass it.** registry.modelmarket.dev is a minimal hub (profile `minimal-hub/1`): four static
files, no tools of its own, a signed list of 21 verified peers. The federation assay admits a stranger only on evidence
of work: a signed receipt from a free call, or a 402 that quotes the catalogue's price. An index-only hub has neither,
so it stays in `review` ("no publicly offered capability to probe, free or priced").

**Why the assay was not changed.** Checking the index's `by_hub` keys against the keys this hub pinned would be easy,
but those keys are public. Any static "index" could copy them, be admitted, and then add tools that get indexed without
a sandbox probe. Admitting index-only hubs is therefore the operator's decision. The hubs allow it:
`AIMARKET_FEDERATION_ASSAY_REQUIRE` is off, so that a hub with nothing to probe can be admitted by a person.

**What admission does.** The peer becomes `trusted` and `active`. A crawl indexes its own tools, of which there are 0.
Its peers enter as `pending` through `announce_peer`, which never upgrades trust or rewrites a pin.

## Done

`approve_registry.py` runs inside each hub container with that hub's own admin token, which is never printed, and
calls `POST /ai-market/v2/federation/peers/approve`.

| Hub (container, host) | Before | After | Log |
|---|---|---|---|
| modelmarket.dev (`modelmarket-hub`, factory-vps) | pending since 2026-11-01 11:03:48Z | active, trusted | `apex.log` |
| hunt.modelmarket.dev (`signal-hunt-hub-1`, hunt host) | pending since 2026-11-01 11:08:59Z | active, trusted | `hunt.log` |
| hub.modelmarket.dev (`modelmarket-hub`, hunt host) | pending since 2026-11-01 11:02:15Z | active, trusted | `hub-modelmarket-dev-on-hunt-host.log` |

The third row was not planned. On the hunt host the container named `modelmarket-hub` serves hub.modelmarket.dev; the
container serving hunt.modelmarket.dev is `signal-hunt-hub-1`. Our registry was pending there as well. `outside-check.log`
shows all three public `/federation/peers` lists with the registry active and no longer pending (04:09Z, server time).

## Rollback, per hub

Inside the container, the same call with `"trusted": false`, or delete the row:

```bash
curl -X POST -H "Authorization: Bearer $AIMARKET_ADMIN_TOKEN" -H 'Content-Type: application/json' \
  -d '{"url":"https://registry.modelmarket.dev","trusted":false}' http://127.0.0.1:9083/ai-market/v2/federation/peers/approve
```
