# Wholesale eSIM price history

Started 2026-11-18 to answer a question we could not answer with data: how often and how far do wholesale eSIM prices
move between a quote and an order? The kit's quote window (`QUOTE_TTL_SECONDS`, default 600) was chosen, not measured
(asked on DEV by APIbase, comment 3lh4e).

The reference node `esim-node` on factory-vps runs in demo mode but reads the live eSIM Access catalogue: it rewrites
`/opt/esim-node-data/catalog-snapshot.json` after each successful read, and reads again when its copy is older than
15 minutes and someone asks for a quote. `esim-price-history.timer` (every 5 minutes, UTC) asks the node for one quote
on `127.0.0.1:9493`, then `esim_price_history.py record` compares the snapshot with the previous read and appends to
`/var/lib/aicom/esim-price-history/`:

| File | What |
|---|---|
| `reads.jsonl` | one line per new catalogue read, also when nothing changed: time, previous time, plans, counts |
| `changes.jsonl` | one line per plan whose wholesale cost (`price`), data or days (`terms`) changed, or that was `added` or `removed` |
| `daily/YYYY-MM-DD.json.gz` | the first snapshot of each UTC day |
| `last.json` | the previous read, per plan id: cost, data, days, name |

It changes nothing in the kit or the node, reads no secrets, and talks only to localhost. Resolution is the node's
catalogue age, about 15 minutes: two changes of one plan between reads count as one.

```bash
ssh factory-vps 'python3 /usr/local/lib/aicom/esim-price-history/esim_price_history.py report'
```

`report` gives the period, the number of reads, price changes per 1,000 plans per day, rises and falls, the median and
90th percentile of the change in percent, the shortest gap between two changes of one plan, and a Poisson estimate of
the chance that a plan's price changes within a quote window (`--window-seconds`, default 600).

Install or remove: see `install.sh`. Tests: `tests/test_esim_price_history.py`.

## Before 2026-11-18: the nightly backups

The node's latest snapshot is in every nightly backup of factory-vps (`/opt` is a backup root). `backfill_from_borg.sh`
extracts it from each archive, oldest first, into `/var/lib/aicom/esim-price-history/backfill-borg` with the same
recorder (read-only on the repository). Run 2026-11-18 14:39Z: 21 archives, the first three without the file, 18
snapshots from 2026-10-19 to 2026-11-18 (2026-10-19, 10-26, 11-01, 11-02 and 11-05, then daily), 1,725–1,823 plans:

- 402 wholesale price changes on 377 plans: 356 cuts (median −14.3 %, largest −69.4 %), 46 rises (median +25.2 %,
  largest +88.2 %), all 46 rises in one update between the copies of 2026-11-15 03:17Z and 2026-11-16 02:54Z (16
  countries and territories, and two regional plans: North America, South America (6 areas));
- no price changed between the copies of 2026-10-19 and 2026-11-05; of the 13 daily intervals since, 7 had an update
  of 59, 16, 84, 17, 111, 91 and 24 plans: prices move in batches, not as a drift;
- 102 plans added, 7 removed, no change of data or days on an existing plan id.

Daily copies cannot show at what hour an update lands or how a batch spreads over the day; the 15-minute recorder can.
