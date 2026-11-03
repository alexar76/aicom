# HISTOR Watch for teams — Stripe sandbox run, 2026-11-01

`sandbox_e2e.py` runs a local HISTOR (dev profile, Postgres 16 in Docker, the test suite's fake
MCP server) with the AIMarket sandbox's restricted test key, `stripe listen` forwarding to
`/api/v1/watch/stripe`, and a public HTTPS endpoint (httpbin.org) as the team's webhook.

| Run | Log | Result |
|---|---|---|
| 1 | `sandbox_e2e.run1.log` | payment, webhook, delivery and test event passed; the harness then read the `/watch` HTML as JSON and stopped (harness bug) |
| 2 | `sandbox_e2e.run2.log` + the `sandbox_refund.py` lines | paid through the checkout link on `/watch`; the refund through the API was refused (HTTP 403: the restricted key has no Refunds permission), so it went through the Stripe CLI. The refund ended the period, but the harness had corrected `time.time()` and not `datetime.now()`, so its last delivery check compared two clocks an hour apart (FAIL). Fixed in the code: `watch_paid` reads one clock |
| 3 | `sandbox_e2e.log` | **PASS**: paid on `/watch` with test card 4242 → `checkout.session.completed` 200 → active 30 days → a change delivered over HTTPS → test event 200 → `/watch` shows it active → refund via CLI → `charge.refunded` 200 → lapsed, nothing more sent |

`stripe-listen.log` is the forwarder's log with the webhook secret removed. Both refunds of the
earlier runs' payments succeeded; nothing is left charged in the sandbox. The Mac's clock runs
~58 min ahead of Stripe (servers are NTP-synced); the harness corrects `histor.watch_paid`'s
clock by the measured offset and nothing else.

## Prod (admin-vps), demo mode

| Image | What | Rollback |
|---|---|---|
| `histor-histor-1-wp-20261101` (d834b00de443) | Watch + migration 018 + `HISTOR_WATCH_DEMO: "1"`, FROM hs-20261101 (503fc8da820c) | top of `histor_watch_paid_overlay.sh` |
| `histor-histor-1-wpp-20261101` (07b33b835aef) | page fixes (endpoint field style, disabled button), FROM wp | top of `histor_watch_page_overlay.sh` |

`rollout.log`, `rollout-page.log`. Public checks after each: plan in demo, opening a subscription 503,
`/api/v1/watch/stripe` reaches the app (404 without a webhook secret), no CORS on `/api/v1/watch/`,
`/watch` 200, a cursor past 2^63 → 422, no errors in the log, crawl restarted, MOMUS binding moved.

To open sales: a live Stripe key (restricted, *Checkout Sessions: write*) and a Stripe webhook on
`https://histor.modelmarket.dev/api/v1/watch/stripe` (`checkout.session.completed`,
`checkout.session.expired`, `charge.refunded`, `charge.dispute.created`), the two values as
`HISTOR_STRIPE_SECRET_KEY` / `HISTOR_STRIPE_WEBHOOK_SECRET` in `/opt/histor/.env`, remove the
`HISTOR_WATCH_DEMO` line from the compose file, recreate the container.
