# modelmarket.dev home page without CoinMarketCap strings — 2026-11-22

Owner 22.11: «убери строки CMC с главной». After CoinMarketCap left the directory at 15:22Z
(`../hub-cmc-removal-2026-11-22/`), the page source still carried two unused strings: `coinmarketcap` in the
documentation-host allowlist of `terminal-home.html`, and `external_desc_coinmarketcap` in `hub-ui-i18n.json` (five
languages). Neither was shown.

**Change** (aicom main, see the commit after this record): both strings removed. `terminal_search_evidence.test.cjs`
now feeds the page a CMC row from the server and checks it does not render (directory and search), and checks escaping
with a Tavily row instead. node 22/22 (caps search 3, live 9, search evidence 10); hub page and catalogue tests 292 passed.

**Rollout (factory-vps, server UTC).** Overlay `modelmarket-hub:3.22.0-nocmcpage-20261122` (`sha256:7eb779251c52…`)
FROM the running `modelmarket-hub:3.22.0-nocmc2-20261122` (`35c1a74f…`): the two files in both places the image keeps
them (`/app` and `/app/aimarket_hub/static/ui`), mode 644, owner `hub`; `build.sh` checked the running copies were
main's before the change (`f85effe3…`, `90d47378…`) and refuses an existing tag. Open alerts read before (none open).

- 18:36:39Z first `roll.sh`: DB backup `/root/hub-backups/modelmarket-hub-pre-nocmcpage-20261122T183639Z.db`, then
  `rollout_container.py` stopped with `Docker POST /containers/7acf3bd6…/stop failed: HTTP 404` before changing
  anything (the hub kept running on `nocmc2`, healthy). See the trap below.
- 18:39:50Z second `roll.sh`, started right after a payout run finished and after checking that only `themis` shared the
  hub's network: DB backup `…-pre-nocmcpage-20261122T183950Z.db`, healthy (hub 9083, THEMIS 9460); previous container
  `modelmarket-hub-security-prev-1795372791307186055`. Payout runs before and after the switch (18:39:47Z, 18:40:50Z)
  finished normally.

**Trap: the publisher payout job looks like a borrower.** `modelmarket-publisher-payout.timer` runs every ~60 s
(`/root/publisher-custody-20261112/payout-worker.sh run-once`, about one second): a `docker run --rm --network
container:modelmarket-hub <hub image> python -m aimarket_hub.publisher_withdrawal_cli run-once`. `rollout_container.py`
recreates every container in the hub's network namespace inside the new one. At 18:36:39Z the payout container
(`elastic_saha`) was listed as a borrower and had removed itself before the stop, hence the 404. Had it still been
running, the script would have re-created it, that is, run a payout pass a second time. Before rolling
`modelmarket-hub`: wait until a payout run has just finished and check that no container other than `themis` has
`NetworkMode container:<hub id>` (the wait loop used here is in this record's commit message).

**After (18:40–18:41Z).** Public `https://modelmarket.dev/`: 200, 0 occurrences of "coinmarketcap" in the page; the
allowlist and the translations for Tavily and Laso present; `/ai-market/v2/external-services` = `tavily`, `laso`. In the
container all four files have 0 occurrences. Health ok, `RestartCount` 0, no traceback; THEMIS 200.

**Rollback** (only on the owner's word), after a payout run as above:
`cd /root/hub-cmc-strings-20261122/kit && python3 rollout_container.py modelmarket-hub --image
modelmarket-hub:3.22.0-nocmc2-20261122 --health http://127.0.0.1:9083/ai-market/v2/health --health
http://127.0.0.1:9460/health`.
