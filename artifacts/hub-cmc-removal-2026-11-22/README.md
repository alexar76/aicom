# CoinMarketCap removed from modelmarket.dev — 2026-11-22

On 22.11 CoinMarketCap support (Grace, ticket 1474981) asked that the directory entry stay a documentation reference
only, and that ModelMarket not present CMC data or API access as part of its offerings. They cited their Commercial
Terms of Use (no copying or aggregating content to make it available to a third party; distribution only inside one's
own product, not standalone). Before this change the entry carried their x402 endpoint, method, price and network, and
a search for crypto prices returned it beside the hub's own results. The owner chose to remove it entirely (22.11,
«Да, убрать»). This is the second removal: on 21.11 it was removed at 19:11Z and restored at 19:18Z
(`../hub-cmc-removal-2026-11-21/`).

**Change.** `aimarket_hub/external_services.py` lists only Tavily and Laso. `tests/test_catalog_hygiene.py` checks the
directory holds exactly those two and that "CMC crypto prices", "CoinMarketCap" and "котировки криптовалют" return no
external reference. `test_catalog_hygiene.py` and `test_x402_bridge.py`: 82 passed. The bridge's CMC-specific receipt
check stays in code; it is reachable only for a seller the bridge admits, and CMC is admitted nowhere.

**Rollout (factory-vps, server UTC).** One-file overlay `modelmarket-hub:3.22.0-nocmc2-20261122`
(`sha256:35c1a74f…`), built FROM the running image `modelmarket-hub:3.22.0-cataloguelink-20261122` (`sha256:ef2ece24…`).
`build.sh` checked the running file is main's copy before this change (`f786c49a…`); the image's own check lists
`['tavily', 'laso']`. Before the switch: open alerts read (none open on factory-vps), no in-container edits
(`docker diff` shows only `__pycache__`), no other rollout running. `roll.sh` at 15:22:04Z:

- database backup `/root/hub-backups/modelmarket-hub-pre-nocmc2-20261122T152204Z.db` (6.3 MB);
- `rollout_container.py` with health 9083 (hub) and 9460 (THEMIS): healthy;
- previous container `modelmarket-hub-security-prev-1795360925835390587`, THEMIS's
  `themis-security-prev-1795360925835390587`.

**After (15:22–15:24Z).**
- `/ai-market/v2/external-services` lists `tavily` and `laso`.
- Search "CMC crypto prices", "CoinMarketCap", "котировки криптовалют": `external: []`. The crypto query's hub matches
  are `crypto.price.onchain@v1` (HESTIA, Uniswap v3 on Base) and `meter.prices@v1`; nothing from CMC.
- Health 3.22.0 ok, `RestartCount` 0, no traceback.
- The home page no longer shows a CMC card (it renders only what the directory returns). Its source still carries the
  unused translation key `external_desc_coinmarketcap` and the documentation-host allowlist entry; neither is shown.

**Rollback** (only on the owner's word): `python3 rollout_container.py modelmarket-hub --image
modelmarket-hub:3.22.0-cataloguelink-20261122 --health http://127.0.0.1:9083/ai-market/v2/health --health
http://127.0.0.1:9460/health` in `/root/hub-cmc-removal-20261122/kit`.

**Reply to CMC:** `coinmarketcap-reply-2026-11-22.md` (owner sends).
