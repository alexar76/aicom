# CoinMarketCap removed from modelmarket.dev, then restored — 2026-11-21

Owner 21.11: «убери их нафиг», «и передеплой на проде». On 19.11 CMC support (ticket 1474981) declined any
callable ModelMarket route for CMC quotes. They did not object to the direct reference: a link plus price,
`hub_invoke: false`, where the buyer pays CMC. The operator removed that reference too.

**Change.** `aimarket_hub/external_services.py` no longer lists `coinmarketcap`; Tavily and Laso stay.
`tests/test_catalog_hygiene.py` now checks that a "CMC crypto prices" query returns no external reference. Tests:
`test_catalog_hygiene.py` and `test_x402_bridge.py`, 82 passed. The bridge's CMC-specific receipt check stays in
code. It is reachable only for a seller the bridge admits, and CMC is admitted nowhere (all six hubs checked:
no CMC in `external`, `observed` or `matches`; only modelmarket.dev listed the reference).

**Rollout.** One-file overlay `modelmarket-hub:3.22.0-nocmc-20261121` (sha256:2a6a6b0f…), built FROM the
running 3.22.0 image (45737a5b…) on factory-vps. `build.sh` refuses unless the running file is main's copy
before this change (sha256 f786c49a…). `roll.sh` at 19:11:16Z (server UTC):

- database backup `/root/hub-backups/modelmarket-hub-pre-nocmc-20261121T191116Z.db`;
- `rollout_container.py` with health 9083 (hub) and 9460 (THEMIS): healthy;
- previous container `modelmarket-hub-security-prev-1795288277553946052`, THEMIS's
  `themis-security-prev-1795288277553946052`.

**After.**
- `/ai-market/v2/external-services` lists `tavily` and `laso`.
- Search "CMC crypto prices" returns `external: []`.
- Health 3.22.0 ok, `RestartCount` 0, no traceback.

**Rollback:** `python3 rollout_container.py modelmarket-hub --rollback` in
`/root/hub-cmc-removal-20261121/kit`, or `--image modelmarket-hub:3.22.0-20261121` with the same health URLs.

## Restored, 19:18Z

The owner was told CMC had not objected to the reference, and answered «тогда верни». `roll.sh` with the
previous image `modelmarket-hub:3.22.0-20261121` (45737a5b…) at 19:18:35Z:

- database backup `/root/hub-backups/modelmarket-hub-pre-cmcback-20261121T191835Z.db`;
- result healthy;
- the overlay container is kept as `modelmarket-hub-security-prev-1795288716846971122`.

After: `/ai-market/v2/external-services` lists coinmarketcap, tavily and laso again, and search "CMC" returns the
reference. The code change is reverted in main. The live reference is again the direct one: `hub_invoke: false`, the
buyer pays CMC. No callable CMC route exists (the 19.11 refusal stands).
