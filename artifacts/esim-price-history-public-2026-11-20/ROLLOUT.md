# Public eSIM price history and `esim.price.history@v1` — 2026-11-20

## What went live (times UTC, from the servers)

- **factory-vps, 20:32Z.** `scripts/esim-price-history` installed again with `install.sh`. The service now runs
  `export` after `record` and writes `/var/www/esim-landing/price-history/v1/` (index.json plus 205 country files,
  about 1.5 MB, about 1 s of CPU, rewritten only after a new catalogue read).
- **nginx on factory-vps.** `deploy/nginx/esim.modelmarket.dev.conf` has a new location, `^~ /price-history/`: static
  JSON, `Access-Control-Allow-Origin: *`, `Cache-Control: public, max-age=60`. The live file now equals the repo
  file. Before this, the only difference was where the IndexNow include sat.
- **HESTIA (competing-lab), ~20:50Z.** The agent `esim-prices` (`esim.price.history@v1`) was deployed with
  `hestia_agents.cli deploy --only esim-prices`. It is free, its only egress host is `esim.modelmarket.dev`, and it
  runs in the wasm sandbox.

## Checks

- `https://esim.modelmarket.dev/price-history/v1/index.json` returned 200 with `application/json` and CORS `*`.
  An unknown country file returns 404, and the landing page `/` is unchanged.
- The index covers the 18 backup copies from 2026-10-19 to 2026-11-18, a bridge interval from 11-18 02:40Z to 14:29Z,
  and 214 reads at 15-minute intervals. It shows 468 price changes (47 rises), and the 16 November batch has 46 rises,
  the same as the DEV.to article.
- Live agent calls:

  | Request | Result | Time |
  |---|---|---|
  | `{"country":"JP","data_gb":20,"days":30,"regional":false}` | 4 plans; JP_20_30 +40.2 % and JP_20_30_nonhkip +45.5 %, both in the 11-16 batch | 2.3 s |
  | `{}` (overview) | 14 batches | 1.1 s |
  | DE 3 GB/30 d | 8 plans, none changed | 1.7 s |
  | `JPN` | 400 | — |

  Every successful answer carries a signed receipt.
- The published files carry no absolute wholesale costs, only `change_pct`. A test checks this, see below.
- Tests: `tests/test_esim_price_history.py` has 6 tests, including the export test with backup copies, the bridge,
  live reads and no costs. `hestia-agents/tests/test_esim_prices.py` has 7 tests, run against files recorded from the
  live copy at 20:35Z. The full hestia-agents suite: 969 passed. The failures were the docs tests (since written; all 125
  docs, catalogue and agent tests now pass), `test_cli` payment-redeem (it fails on main too), and the
  `test_mcp_diff` timing test, which took 3.37 s against a 3.0 s limit on a busy Mac. Its file passes when run on its
  own.

## Rollback

```bash
# nginx: the previous config (functionally the same, without /price-history/)
ssh factory-vps 'cp /root/esim.modelmarket.dev.nginx.pre-pricehistory-20261120 /etc/nginx/sites-available/esim.modelmarket.dev && nginx -t && systemctl reload nginx'
# recorder without export: install the previous scripts/esim-price-history (git show 07a85eeea:...) with install.sh;
# the public files can stay or be removed: they live only in /var/www/esim-landing/price-history (this session made it)
# the agent: stop the esim-prices tenant on the hearth (owner API), or redeploy the previous catalogue without it
```
