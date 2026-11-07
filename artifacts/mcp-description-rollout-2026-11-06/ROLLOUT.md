# Hub tool definitions without prices, and ARGUS that reports a blocked server: 2026-11-06

Owner's words: «проверь своё решение независимым агентом и вкатывай». Code: aicom `624e03e43`, plus `8185007bd`
with the fixes from the independent review. All times are server clocks (UTC).

## Why

The hub wrote the live price and the trial size into each direct tool's description. Any price edit
therefore changed the tool definitions. WARDEN pins tool definitions, so our own ARGUS treated each edit
as a possible rug pull and stopped using the hub until someone re-approved it. This happened on all three ARGUS,
for days, and each container reported healthy (`artifacts/security-audit-2026-11-06/ROLLOUT.md` §5).

## Review before the rollout

An independent agent reviewed `624e03e43` without access to my conclusions. Fixed in `8185007bd`:

- a block while running was neither logged nor reported to the owner;
- a server whose tool list stopped answering stayed "connected";
- an owner note was lost when the bot had no owner yet, or when Telegram refused it;
- the note offered `pins approve` where it does not apply, and named catalog servers whose ids are the catalog's text;
- the trial half of the hub test checked nothing;
- the packaged server card still said 1.2.0.

Not changed, and left to the owner: direct tools still leave `tools/list` while their route is not sellable, so a
peer that is stale for more than 6 h changes the tool set.

## Hubs (only `aimarket_hub/mcp_gateway.py` changes)

The live gateway files had two variants:

- modelmarket.dev had `5c5ae3aa2693`, which equals main's base, so it got the committed file `bcb3d88c3f76`.
- The other five had `44e5645e8544`, which is main's base plus a `receipt_binding` block from branch
  `claude/federation-hub-deployers-search-8b9411`. That block is not on main. These hubs got the same change
  patched on (`kit/mcp_gateway.patch`): `a81bde47a61d`. Apart from the 12-line offset, it differs from the
  committed file only in that block.

`kit/build.sh` stops unless the live gateway still has the expected hash. It then builds FROM the running image
(`kit/Dockerfile`, one COPY), runs `kit/smoke.py` in the image with no network and without the `AIMARKET_*` env, and
compares the file in the image with the context. The smoke has 22 checks: version 1.3.0; each direct tool's definition
is the same at $0.001 and $0.05 and with another trial size; no amount appears; a free tool says "Free."; the app
imports. All five builds passed (`logs/build-*.log`).

Each hub was rolled with `/root/hub-3160-main-20261021/roll.sh`: a DB backup, then `rollout_container.py` with
automatic rollback.

| Hub | Host | Before | After | Previous container | DB backup |
|---|---|---|---|---|---|
| uni.modelmarket.dev | factory-vps | `modelmarket-hub-uni:cf-20261104` | `modelmarket-hub-uni:md-20261106` | `modelmarket-hub-uni-security-prev-1793995749121476110` | `/app/data/hub-backup-pre-3160-20261106T200907Z.db` |
| hub.modelmarket.dev | competing-lab | `modelmarket-hub:cf-20261104` | `modelmarket-hub:md-20261106` | `modelmarket-hub-security-prev-1793995797041743888` | `/app/data/hub-backup-pre-3160-20261106T200956Z.db` |
| hunt.modelmarket.dev | competing-lab | `signal-hunt-hub:cf-20261104` | `signal-hunt-hub:md-20261106` | `signal-hunt-hub-1-security-prev-1793995833787543645` | `/root/hub-backups/signal-hunt-hub-1-pre-3160-20261106T201032Z.dump` |
| hub.attestedmemory.net | attested | `attested-memory-hub:mgw-20261105` | `attested-memory-hub:md-20261106` | `attested-memory-hub-hub-1-security-prev-1793995904107397568` | `/root/hub-backups/attested-memory-hub-hub-1-pre-3160-20261106T201143Z.dump` |
| modelmarket.dev | factory-vps | `modelmarket-hub:mgw-20261105` | `modelmarket-hub:md-20261106` | `modelmarket-hub-security-prev-1793995932326069965` (THEMIS recreated, healthy) | `/app/data/hub-backup-pre-3160-20261106T201211Z.db` |
| independentai.network/hub | indep (venv) | `mcp_gateway.py` `44e5645e8544`, copy in `/root/mcpdesc-20261106/backup/` | `a81bde47a61d` | — | `/root/indep-hub-pre-md-20261106.dump` |

The rolls ran from 20:09Z to 20:12Z, all with `ROLL-EXIT=0` and healthy. On Independent, the smoke first ran on a
copy of the venv package with the venv's Python (22 checks). The file was copied in and the service restarted
separately at 20:13:02Z. It was healthy after 5 s; the 502s before that came from the start.

Rollback, per hub: `cd /root/hub-3160-main-20261021 && python3 rollout_container.py <container> --image <before image>
--health http://127.0.0.1:<port>/ai-market/v2/health`. The ports are uni 9183, apex and lab 9083, hunt and
attested 9084. Independent: copy `/root/mcpdesc-20261106/backup/mcp_gateway.py` back into
`/opt/independentai/venvs/hub-3.16.0-rpc-security-20261031/lib/python3.12/site-packages/aimarket_hub/`, then
`systemctl restart independentai-hub`.

## Verified from outside (`kit/live_tools.py`: initialize and tools/list, twice per hub)

Before (`live-before.log`):

- all six reported server version 1.2.0;
- all five hubs with direct tools carried amounts in all five direct-tool descriptions;
- modelmarket.dev's tool list (`772b3b6e0fc5`) differed from the others' (`adbe6e414555`) only because their prices
  differed.

After (`live-after.log`):

- all six report 1.3.0, with no amounts;
- two reads in a row are identical;
- the five hubs with direct tools serve one identical list, `2da312ba9027` (13 tools);
- uni has no direct tools, so its 8 tools are unchanged (`d77cb482eb33`);
- health returns 200 on all six;
- `market_search` on modelmarket.dev still shows `price_per_call_usd` and `max_price_usd`
  (`logs/market-search-price.log`).

## ARGUS ×3 (`8185007bd`)

The images are built over the same hc-live bases as this morning (`kit/argus/`, context `git archive 8185007bd
argus`). They are 0.3.4 on node 22.23.4, and the build checks that the new code is in `dist`.

| Where | Before | After | Compose backup |
|---|---|---|---|
| factory-vps `argus` | `aicom-security:argus-vx-20261106` | `aicom-security:argus-md-20261106` | `/root/claudecode/aicom/argus/docker-compose.yml.pre-md-20261106` |
| factory-vps `argus-uni` | `aicom-security:argus-uni-vx-20261106` | `aicom-security:argus-uni-md-20261106` | same file |
| attested `argus` | `aicom-security:argus-vx-20261106` | `aicom-security:argus-md-20261106` | `/root/argus/docker-compose.roster.yml.pre-md-20261106` |

factory, 20:18:57Z: both healthy. `/health` shows `"mcp":{"connected":0,"blocked":1,"failed":0}` with `status` `"ok"`, and
the log has `ERROR [argus] WARDEN blocked 1 MCP server(s); running without their tools: aimarket-web (TOOL_DEF_DRIFT)`.
The block is expected: the hub's definitions changed once more with this rollout, and the pin has to be re-approved
one last time. Telegram is off on factory, so the log line and `/health` are all there is.

attested, 20:19:45Z: healthy, with the same `/health` counts and the same ERROR line, then
`telegram @Argis3Bot online; owner=…`. The bot's owner note is queued at startup and sent when the bot comes up.
A refused send is retried, but not logged, so whether it arrived is confirmed in the owner's chat, not here.

Owner step (a human at a terminal; ARGUS refuses approval without a TTY): approve `aimarket-web` once on each of
the three containers and restart them. Commands are in the closing message of this session and in
`artifacts/security-audit-2026-11-06/ROLLOUT.md` §5.

Rollback: restore the compose backup, then `docker compose up -d --no-deps argus argus-uni` (factory) or
`docker compose -f docker-compose.yml -f docker-compose.roster.yml up -d --no-deps argus` (attested).
