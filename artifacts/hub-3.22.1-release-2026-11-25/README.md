# aimarket-hub 3.22.1 — built 2026-11-25 from main 00480ee98 (clean `git archive`), not yet on PyPI

Owner 25.11: «ну значит надо обновить образ? обнови, да и пакет тоже можно?», after «вроде уже ничего не дорабатывается»
(main checkout clean for aimarket-hub; the Tutu work committed as 284cbb06e).

## What is in it (main since 3.22.0, ca04e6ab1)

- Observed sellers: `probed_at` in milliseconds (a13a17cf0).
- Tutu Japan eSIM: live quotes, merchant checkout and the external-services reference (f537e5654); the terminal's
  Japan eSIM example and direct offers as their own group (1425bbf21); on the apex a free signed quote capability
  `esim.tutu.quote@v1` (284cbb06e).
- Hub page capability search no longer freezes the tab (06809e022); CoinMarketCap removed from the apex (dbb381ab1,
  ace0404ed); HESTIA strip on the apex home (3921e7413, 5f2c92588).

## Checks

- Full hub suite on 00480ee98's tree: 4370 passed, 68 skipped; failures: `test_mandates_hardening` TestJobTree receipt
  children and `test_pipeline_provider` free graph (both already failing at 3.22.0), `test_pipeline_client` (fails
  intermittently, a different test each run; code and tests unchanged since 3.22.0). The stale Tutu assertion found by
  the run is fixed in this commit (catalog + pipeline_client files rerun: Tutu passes).
- Node page tests 3/3.
- Wheel files match the commit (observed_sellers.py, tutu_esim.py, __init__.py compared by sha256); 202 .py files.

## Files

`wheels/SHA256SUMS`:

    757aab3fdaaaaeb0cc5bfe5ed0cc8911316db26146b49a0256c3b03efcc1cfa0  aimarket_hub-3.22.1-py3-none-any.whl
    a54c4bd58415f40bd73c79138dd70321b92cb685285fd4dc270d8d067a2cef46  aimarket_hub-3.22.1.tar.gz

## Hubs

Not rolled out as a release. modelmarket.dev runs `modelmarket-hub:tutu-federated-probems-20261125` (the millisecond
change is live there; 284cbb06e's apex quote capability is not). Other hubs unchanged.

Publication: colleague-tasks §170 (PyPI upload of these exact files by the owner, then the MCP registry entry).
