# ModelMarket on minia2a.uk — listing kit, 2026-11-27 (NOT sent)

Owner: «Да, подготовь». minia2a.uk is an x402 marketplace (1,600+ endpoints, MCP, OpenAPI). A third-party listing is one
POST signed by the payTo wallet; platform fee 0% through 2027; buyers pay the address in our own 402 directly; the
platform never holds money or forwards calls. Review: an unpaid request must answer 402 with accepts[] before any
parameter check. Rules: https://minia2a.uk/publish-standard.md, https://minia2a.uk/docs/sell.md (read 27 Nov).

## Our routes against their rules (route-check.txt, 27 Nov ~20:15Z)

All 8 paid routes answer an unpaid POST (empty and `{}`) and a GET with 402 + accepts[], payTo
0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a. The blocker is price: minia2a's price_cents is an integer, floor 1 cent,
and its own discovery 402 for a listing asks the listed price.

| Route | Our price | Fits a whole-cent listing |
|---|---|---|
| nearby-sensors | $0.03 | **yes, 3 cents** |
| fair-random | $0.006 | no |
| x402-check, mcp-diff | $0.003 | no |
| warden-scan, histor-check, weather-now, air-quality-now | $0.001 | no |

A sub-cent route listed at 1 cent would ask 10,000 units in minia2a's 402 while ours asks 1,000–6,000: a buyer who
follows their challenge signs the wrong amount and our gate does not take it (no charge, no answer), and price checks
like Agent402's priceMatchesListing would count a mismatch. So the kit lists **nearby-sensors only**.

## To send

1. `python3 publish.py` — dry run (OK on 27 Nov: description 331 bytes, 402 = 30,000 units = 3 cents, payTo matches).
2. `python3 publish.py --send` — signs `minia2a publish: 0x1218…Ad0a` with the payTo key from
   ~/.aicom-base-deployer-v4.json (a message signature, no funds move) and posts. Result in publish-response.json:
   `review_status: pending`; approval is manual on their side. The auto-mode classifier refused my reading that key
   file, so the owner runs step 2 (or allows it explicitly).
3. After approval: the listing appears in https://minia2a.uk/api/services ; their probes hit /x402/nearby-sensors.

Not decided (owner): whether to add whole-cent versions of other routes for this channel. WARDEN scan or HISTOR check
at $0.01 would change their price everywhere unless a separate route is added.

## Sent 2026-11-27 (owner «Подпиши сам»)

`publish.py --send` at ~19:50Z (server time): HTTP 200, `ok: true`, id `x402-publish-1795809023020-aimarket-nearby-sens`,
`reviewStatus: pending`, `active: 0`, price_cents 3, category data / geo-sensors. Response in publish-response.json
(it holds no signature). The status page answers `active: false` until their manual review; status-2026-11-27.json.
Next: check `GET https://minia2a.uk/api/services/x402-publish-1795809023020-aimarket-nearby-sens` in a day; when active,
it is in https://minia2a.uk/api/services and their probes hit /x402/nearby-sensors.
