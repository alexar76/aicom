# Tutu quote reference (mmq): LIVE on modelmarket.dev and hub.modelmarket.dev, 2026-11-27

Why: Tutu (Mykyta Dzhus, 27 Nov) agreed to store a quote reference from the checkout link with the order, under the
parameter `mmq` (`ref` is their invite-code parameter). Owner: «Да, добавь mmq». With it an order in Tutu's CSV can
be matched to the quote that led to it and to that quote's age.

Change (main, see git log): each successful Tutu quote gets `quote_id` = 16 hex characters (`secrets.token_hex(8)`),
returned in the quote and appended to `checkout_url` as `mmq=<quote_id>`; the `external_quotes` row stores it
(migration 076, column `quote_id`, '' for older and failed rows, indexed). A link from Tutu that already carries
`mmq` is refused (503, counted unavailable). `HubDatabase.external_quote(quote_id)` looks one up. The free quote
capability's output schema lists `quote_id`. Until Tutu confirms that mmq is saved with orders, a link with mmq
works as before (Tutu's words; the page answers 200).

Tests: test_catalog_hygiene + test_tutu_esim 41 passed. Full hub suite 4428 passed, 2 failed, 68 skipped; the two are
the pre-existing failures of artifacts/hub-quote-counter-2026-11-27 (fail on clean main too).

## Rollout (server UTC)

| hub | host, container | switched | DB backup | previous container (rollback) |
|---|---|---|---|---|
| modelmarket.dev | factory-vps `modelmarket-hub` (+ THEMIS), after the 05:17:52Z payout run, borrowers = themis | 05:18:00Z (migration 076) | `/root/hub-backups/modelmarket-hub-pre-quotemmq-20261127T051753Z.db` | `modelmarket-hub-security-prev-1795756674191229797` |
| hub.modelmarket.dev | competing-lab `modelmarket-hub` | 05:18:22Z | `/root/hub-backups/modelmarket-hub-pre-quotemmq-20261127T051818Z.db` | `modelmarket-hub-security-prev-1795756698903884491` |

Images: `…-quotecount-20261127-quotemmq-20261127` FROM each hub's running quote-counter image; `build.sh` checks the
three running files are the counter versions. hub.modelmarket.dev's files are its own Tutu build with the same change
applied by hand (no schema there: that build has no quote capability). Smoke in each image, throw-away DB, no
network: migration 076, a 16-hex id in the link and the row, a link already carrying mmq refused. (On the apex the
smoke must not import hub_routes.catalog: it opens a read-only database there.)
Rollback: `cd /root/hub-quotemmq-20261127 && python3 rollout_container.py modelmarket-hub --rollback`.

## Checks after

- Both: health 200, healthy, 0 restarts, no tracebacks; apex THEMIS healthy, next payout run `success`.
- Live quotes: apex `…&mmq=c17a63a948d9e780` (05:18:43), hub.modelmarket.dev `…&mmq=7162b50486ea1999` (05:18:45); the
  rows carry the same ids. Tutu's page with mmq: HTTP 200.
- DEV 5127285 got a dated "Update, 27 November" paragraph (05:19:11Z); its curl snippet, rerun, printed a link with mmq.
- **Our check quotes, to exclude from the reconciliation** (apex rows at this point): [('2026-11-27 04:43:14', ''), ('2026-11-27 05:18:43', 'c17a63a948d9e780'), ('2026-11-27 05:19:25', '716ffad7826f7a9d')]
  plus hub.modelmarket.dev 04:45:37 and 05:18:45.
