# Tutu quote counter: LIVE on modelmarket.dev and hub.modelmarket.dev, 2026-11-27

Why: a reader of the two-supplier article asked how a Tutu order quoted one day and bought later is attributed.
The checkout link carries only `plan` and `src=aimarket`, and it goes straight to tutuesim.com, so the hub kept
no record of the quotes it handed out. Tutu's order log can count tagged purchases, but nothing on our side
counted the links issued. Owner: «Да, счётчик», then «делаем выкатываем на прод».

Change (commit on main, see git log): migration 075 `external_quotes` (service_id, route `rest`|`invoke`, outcome
`ok`|`unavailable`, plan_id, price, currency, quoted_at). `tutu_esim.fetch_and_count_tutu_quote(db, route)` wraps
the quote call; the REST quote URL and the invoke path use it. Nothing about the caller is stored. A failure to
count is logged and never changes the answer. `HubDatabase.external_quote_counts(service, since, until)` groups by
UTC day, route and outcome.

Tests: test_catalog_hygiene + test_tutu_esim 40 passed. Full hub suite: 4427 passed, 2 failed, 68 skipped. The two
failures (`test_mandates_hardening::TestJobTree::test_each_receipt_commits_to_its_own_children_by_their_receipt_ids`,
`test_pipeline_provider::test_free_graph_needs_no_wallet_and_returns_one_sub1_tree`) fail the same way on an
untouched archive of main 32cfdd226: pre-existing, not this change.

## Rollout (server UTC)

| hub | host, container | switched | DB backup | previous container (rollback) |
|---|---|---|---|---|
| modelmarket.dev | factory-vps `modelmarket-hub` (+ THEMIS), right after the 04:42:33Z payout run, borrowers = themis | 04:42:40Z (migration 075 applied) | `/root/hub-backups/modelmarket-hub-pre-quotecount-20261127T044233Z.db` 6.5M | `modelmarket-hub-security-prev-1795754554788042054`, `themis-security-prev-1795754554788042054` |
| hub.modelmarket.dev | competing-lab `modelmarket-hub` | 04:45:16Z | `/root/hub-backups/modelmarket-hub-pre-quotecount-20261127T044511Z.db` 2.0M | `modelmarket-hub-security-prev-1795754712601086429` |

- Apex: `kit/` (factory-vps `/root/hub-quotecount-20261127`). The five running files equalled main 32cfdd226;
  `build.sh` checks their hashes and refuses files copied into the container. Image
  `modelmarket-hub:halowerk-ocr-20261126-XwKcRz-mcp0728-20261126-quotecount-20261127`. The first `roll_apex.sh`
  stopped before switching (the kit lacked `service_env.py`; container untouched, an extra backup
  …T044131Z.db was taken); added and rerun.
- hub.modelmarket.dev runs another session's Tutu build of 2026-11-24 (migrations to 073; catalog.py not in git
  history). `kit-competing-lab/`: `running/` = the files taken from the container, `files/` = the same change
  applied to them by hand (REST route only: this build has no invoke path for Tutu). Image
  `modelmarket-hub:tutu-find-20261124-mcp0728-20261126-quotecount-20261127`. It now has 073 and 075; 074 (OCR
  deliveries) is applied when this hub gets main.
- Smoke in each new image on a throw-away DB, no network: migration 075, ok and unavailable rows.
- Rollback: `cd /root/hub-quotecount-20261127 && python3 rollout_container.py modelmarket-hub --rollback`. The
  older code ignores the new table.

## Checks after

- Both: health 200, container healthy, 0 restarts, no tracebacks; apex THEMIS healthy, the next payout run
  ended `success`.
- One real quote each through the public URL, 3.49 USD, counted:
  apex `('tutu-esim','rest','ok','3.49',…,'2026-11-27 04:43:14')`, hub.modelmarket.dev `… '2026-11-27 04:45:37'`.
  **These two rows are our checks: exclude them from the pilot reconciliation.**

Reading the count (read-only, on the host):

    docker exec modelmarket-hub python -c "from aimarket_hub.database import HubDatabase; import os; print(HubDatabase(os.environ['AIMARKET_DB_PATH']).external_quote_counts('tutu-esim', since='2026-11-27 05:00:00'))"
