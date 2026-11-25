# Observed-seller probe times in milliseconds — LIVE on modelmarket.dev 2026-11-25 06:15:46Z

Why: YuTao matched one of our 21 November probes in his Cloudflare logs at 14:32:02.126 and read it as outside a window
we wrote as ending 14:32:02, because the hub stored `probed_at` in whole seconds (rounded down, after the response).
Owner: «Yes, do it».

Change (main a13a17cf0): `probed_at` = `2026-11-25T06:15:46.123Z`; `_parse_iso` reads both forms. Seller-level
`observed_at` keeps whole seconds. Test `test_a_probe_time_has_milliseconds_and_parses_back`; observed-seller + x402
bridge suites 153 passed.

Rollout (factory-vps, kit `/root/hub-probems-20261125`): one-file overlay
`modelmarket-hub:tutu-federated-probems-20261125` FROM the running `modelmarket-hub:tutu-federated-20261125` (another
session's 04:40Z rollout, kept intact; the live observed_sellers.py was byte-identical to main's previous version).
`roll.sh` = the capsfix roll with the names changed, run right after a publisher-payout run.

- DB backup: `/root/hub-backups/modelmarket-hub-pre-probems-20261125T061546Z.db` (6.4M)
- Previous container kept: `modelmarket-hub-security-prev-*` (rollout_container.py); rollback:
  `cd /root/hub-probems-20261125 && python3 rollout_container.py modelmarket-hub --rollback`
- After: hub and THEMIS healthy, 0 restarts, no tracebacks or 5xx in 3 min.
- Not yet seen live: the next observation cycle (every 6 h; last 04:14Z, next about 10:15Z) is the first to write
  millisecond `probed_at`. Other hubs not changed (only the apex observes YuTao's sellers).

## Found while checking: Insight answers 503 on every route (2026-11-25)

Hub cycle 04:14:53–04:15:40Z: all 20 paid Insight routes 503 (`/api/mcp` 401), so Insight has 0 of 21 listed;
PriorSeal 4/4 at 402. Rechecked 06:17Z from factory-vps: discovery 200, HEAD base-perp-guard 503, one unpaid GET:
`{"error":"RATE_LIMIT_STORE_UNAVAILABLE","message":"The payment rate limit service is temporarily unavailable. Please retry shortly."}`.

Short note for YuTao (owner sends in the same thread, private; no numbers for publication):

> Hi YuTao, a heads-up in case it is not on your dashboard yet: since our 04:14 UTC observation today every paid
> Insight route answers 503. A request at 06:17 UTC to GET /api/v1/safety/base-perp-guard returned
> RATE_LIMIT_STORE_UNAVAILABLE ("The payment rate limit service is temporarily unavailable"). The discovery document
> answers 200. PriorSeal is fine. Insight routes will show as unlisted on the Hub until they quote again. Best, Alex
