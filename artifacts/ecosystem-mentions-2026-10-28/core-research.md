# Core ecosystem external-mentions verification, 2026-10-28

Read-only investigation of alexar76 / AIMarket / modelmarket.dev / Metis / ACEX / Alien Monitor / HEPHAESTUS. Compared with local reports of 24–27 October. No messages, publications, payments, credentials or GitHub writes.

## Directly verified change: Agent Economy Report

[Live public JSON](https://agenteconomy.report/s/modelmarket.dev.json) returned HTTP 200 at 14:32 MSK, `as_of=2026-10-28`. Rating **CC**, score **10.3**, improving outlook, **3 organic paying agents / 12 raw paying wallets**, **$0.39 settled over 14 days**, **50% probe uptime**, eight resources. The prior local 24 October snapshot was D / 0 organic / 5 raw wallets / $0.34. This confirms a change in the observer's computed signals. Its organic category describes wallets paying other services too; it does not identify human customers or establish recurring product adoption.

Current 30-day paid-call counts per resource: HISTOR 14; air quality, WARDEN and weather 8 each; MCP diff 6; fair random and x402 check 4 each; nearby sensors 3. These are the observer's figures. Do not conflate their sum with x402 List's transactions: coverage and definitions differ. Rating remains below the observer's BBB trust line; 50% liveness needs context against its probed routes, rather than being treated as entire ecosystem uptime.

## Directly verified settlement continuation

Data: x402-list.com (CC BY 4.0). Its [volume API](https://x402-list.com/api/v1/services/aimarket/volume) and [buyers API](https://x402-list.com/api/v1/services/aimarket/buyers) returned HTTP 200 at 14:32 MSK. Completed 27 October UTC has **2 settlements / 2 buyer addresses**, versus 1/1 in the morning 27 October local report. Partial 28 October UTC has **1 settlement / 1 buyer**. Both daily volumes round to $0.00; zero after rounding does not prove no payment. Counts cover a shared operator payout address and tracked facilitators, not identified customers or task-success outcomes.

The [live card](https://www.x402-list.com/services/aimarket) returned 200: assessment computed 2026-10-28 10:04:48 UTC; latest check 11:18:17 UTC; 99.6% uptime and p95 326ms in its header. These probes concern unpaid 402 handshakes. The search copy had older 27 October measurements and p95 335ms, so it is superseded.

## Additional external discovery confirmed by live GET

1. [GAIA on mcp.market](https://mcp.market/server/modelmarket-weather): HTTP 200; namespace `dev.modelmarket/weather`; endpoint `https://modelmarket.dev/tools/mcp/weather`; v1.0.0; last release/commit 26 October. Public scan dated **27 October**, scanner 0.1.10, **91/100, A**; three descriptions, no findings; **12/12 reachability checks**, **no user reviews**. Remote-only means the code-scan component was not performed. External technical listing of a specific MCP interface, not an audit of the full product. Card publication date unconfirmed. This source/door is absent from prior reports searched.
2. [INITE Atlas main card](https://inite.ai/en/atlas/modelmarket.dev), [alphabetical shelf](https://inite.ai/en/atlas/all/m) and [alternatives](https://inite.ai/en/atlas/modelmarket.dev/alternatives) all returned 200. Main card links modelmarket.dev and describes marketplace/escrow behavior. Alternatives page is dated read 2026-10-28. Its [method](https://inite.ai/en/atlas/method), also 200, describes weekly crawler readings rather than user reviews. New source relative to prior reports searched, not proof of usage. Card creation date unconfirmed.
3. [MCP Bridge AI & ML directory](https://mcpbridge.org/directory/ai-ml/): HTTP 200, exact `alexar76/aimarket-plugins`, active label, score 58, 15 plugins. Repository-derived directory listing; publication/measurement date unconfirmed. Absent from prior reports searched.

## Search exclusions and retrieval limits

Approximately 35 exact query combinations with owner, domains, package and repository names, date filters, exclusions of own sources, and Reddit/Hacker News domains. No newly verified independent narrative review of Metis, ACEX, HEPHAESTUS or Alien Monitor emerged. Bounded search visibility is not proof of absence. Generic names without exact ecosystem linkage were excluded. Hlido, Agenstry, A2A Registry, Odel, RoninForge, mcpbeat, MCPRepository, Forge and article mirrors were already known and were not counted as new. Agenstry's indexed 60/C copy was superseded by the live 78/B baseline in the prior report, so no regression is inferred.

Initial ordinary sandbox requests failed DNS resolution, and web.open returned Cache miss. These were tool-access failures. A permitted public GET pass subsequently returned 200 for all 11 selected URLs; it supersedes the initial search-only limitations. An optional follow-up request without the configured browser User-Agent received 403; the evidenced GETs used that header and succeeded.

Evidence: `core-public-verification.json` records requested/final URLs, retrieval timestamps, HTTP status, SHA-256 of response bytes and selected public fields. Full foreign HTML articles were not retained.
