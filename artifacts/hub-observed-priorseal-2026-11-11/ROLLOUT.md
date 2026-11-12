# modelmarket.dev: PriorSeal's discovery format, and two consented sellers recorded — 2026-11-11

YuTao (imokokok) in alexar76/aimarket-hub#23, issuecomment-6789700463 (2026-11-11 07:20:45Z): «Yes, please record
oracleinsight.xyz in the observed tier now» and «Please add priorseal.xyz once the parser accepts the current
resource field». The owner had agreed on 2026-11-10 to list them once YuTao said yes. The parser rollout and the
recording happened on the owner's «Yes, roll out» on 2026-11-11.

## Parser

PriorSeal's `/.well-known/x402.json` lists Bazaar-style items under `resources[]` with the route in `resource`; the
hub read `url` there and found 0 of 4 routes. The fix is 7d80bae43 (on main since 2026-11-10).

- The apex hub on factory-vps ran `modelmarket-hub:apex-tools-20261111` (8ecd6cd3547d). Its
  `/app/aimarket_hub/observed_sellers.py` was byte-identical to the file before the fix (`00e29ab8…`), so main's
  file (`b1104ce8…`) went in as is.
- Overlay `modelmarket-hub:os-priorseal-20261111` (1716dc9c0ab2) = the running image plus that one file (`Dockerfile`,
  `build.sh`).
- `smoke.py` passed inside the image with no network, against the two live discovery documents saved here
  (`priorseal-x402.json`, `oracleinsight-x402.json`): the file hash, PriorSeal 4 GET routes (0 before), oracleinsight
  20 routes, the app imports.
- Open alerts before the roll: disks of oracle (admin-vps) and attested only. No rollout was running on factory-vps.
- Rolled 2026-11-11 ~10:20Z (`roll-apex.log`):

  ```
  roll.sh modelmarket-hub modelmarket-hub:apex-tools-20261111 modelmarket-hub:os-priorseal-20261111 \
    http://127.0.0.1:9083/ai-market/v2/health,http://127.0.0.1:9460/health
  ```

  SQLite backup `/app/data/hub-backup-pre-3160-20261111T102020Z.db`. Healthy; THEMIS recreated and healthy. The two
  existing sellers (textokit 20 routes, aemb.pro 1) were unchanged after the roll.

Only the apex hub records observed sellers, so the other five hubs were not changed.

## Sellers recorded (`record.py`, inside the container, token from its env)

| Origin | Recorded | Listed | payTo (pinned on first sight) |
|---|---|---|---|
| `https://priorseal.xyz` | 10:21:11Z | 4 of 4, GET, $0.02 ×3 and $1.00 | `0x5FBbbCbF2Ade44F5c604E5E55f11945E1ADdD231` |
| `https://www.oracleinsight.xyz` | 10:21:37Z | 8 of 20 | the same |

`oracleinsight.xyz` answers both discovery paths with 307 to `www.oracleinsight.xyz`, and the hub does not follow
redirects, so the www origin is recorded. Of its 20 routes, the hub did not list 12:
- 3 quote on eip155:143 (Monad) or eip155:999 (HyperEVM) → `unknown_asset`;
- `/api/mcp` answered 401;
- 8 answered 429 to the unpaid request. It was the same 8 from the Mac dry run and from factory-vps:
  base-perp-guard, hyperliquid-perp-guard, bnb-perp-guard, solana-lending-guard, solana-perp-guard, solana-swap-guard,
  loopscale-vault-deposit and swap-intent.

POST routes were probed with POST and `{}` after HEAD, as the manifest advertises (`record-oracleinsight.txt`).

Verified live: `/ai-market/v2/federation/observed-sellers` shows four sellers (`sellers-after.json`).
`/ai-market/v2/search?intent=integration readiness` returns PriorSeal's routes. `intent=pre-trade safety` and
`intent=oracle watch window` return Insight's.

## Rollback

- Sellers: admin `DELETE /ai-market/v2/federation/observed-sellers?origin=<origin>`.
- Parser: the previous containers `modelmarket-hub-security-prev-1794392421430718209` and
  `themis-security-prev-1794392421430718209`. Or roll again onto the previous image:

  ```
  roll.sh modelmarket-hub modelmarket-hub:os-priorseal-20261111 modelmarket-hub:apex-tools-20261111 <same health URLs>
  ```
