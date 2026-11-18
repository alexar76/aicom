# Live ARGUS on 0.5.1 — attested, 2026-11-18 05:20Z and 05:30Z

The live ARGUS (container `argus` on attested, @Argis3Bot) ran `aicom-security:argus-0.5.0-20261117`, the 0.5.0 release
image. It now runs `aicom-security:argus-0.5.1-20261118` (`sha256:6833789c…`), built on the host with `argus/Dockerfile`
from the 0.5.1 release sources (main `d4d159425`); its `/app/dist` (517 files) and `/app/web` are byte for byte the npm
tarball's (sha256 `708eba37…`). What 0.5.1 changes: after a refused eSIM order ARGUS weighs the other sellers' offers
and never switches seller by itself (`argus/CHANGELOG.md`, 0.5.1). The owner asked for it on 2026-11-18 («Implement
first», «давай сделаем в лучшем виде», then «агрус 5 уже в нпм — не надо поднять версию?»).

Two switches, both with `switch*.sh` here (purchase-in-progress guard, rollback on any error):

1. **05:19:57–05:20:14Z, `switch-1-compare.sh`:** `aicom-security:argus-0.5.0-cmp-20261118` (`sha256:ca68f1d8…`), the
   0.5.0 release context with `src` from main `a932b6106`; it still said 0.5.0. Main's own `package.json` could not
   build then: `16baae29c` added a `file:third_party/picomatch-4.0.8.tgz` override that the Dockerfile did not copy,
   and `npm ci` failed with ENOENT on attested. Fixed in 0.5.1.
2. **05:30:10–05:30:28Z, `switch-2-release.sh`:** the 0.5.1 release image, after the owner asked for a new version
   number (npm 0.5.0 was already published).

## Before the switches

| Check | Result |
|---|---|
| Image 1: build context `src` against `git archive a932b6106 argus/src` | 130 files, identical |
| Image 1 against the live 0.5.0 container: `dist`, `web`, `package.json`, `package-lock.json` | 520 files; only `dist/economy/esim.*` and `dist/tools/esim.*` differ |
| Image 2 `/app/dist` and `/app/web` against the 0.5.1 npm tarball (sha256 `708eba37…`) | identical, file by file (517 + 1) |
| Image 2 `dist` against image 1 | only `dist/cli/util.{js,d.ts}` (the version) |
| `node_modules/**/package.json` (depth 3), both images against the live container | 278 files, identical |
| Offline smoke (`--network none --read-only --cap-drop ALL`) | ARGUS 0.5.1, WARDEN 0.29.0, `playwright-core` 1.64.1; eSIM tools load; `esim_buy` describes `cheaper_elsewhere` |
| Dockerfile fix | main with `COPY third_party` in both stages built on attested; the check image was removed |
| Purchases in progress | none (the switch scripts check the Hudson Link and itch.io journals) |

## After (05:30–05:33Z)

| Check | Result |
|---|---|
| Container | `aicom-security:argus-0.5.1-20261118`, healthy; `package.json` 0.5.1, WARDEN 0.29.0, Playwright 1.64.1 (checked by the switch) |
| Logs | threat feed loaded (signature valid); chain LIVE Base mainnet; WARDEN `ALLOW aimarket-web`, 13 tools pinned; `argus serve — http :8787 + telegram`; @Argis3Bot online; 0 error lines (also after switch 1) |
| `/health` | 200 |
| Wallet (`argus economy status`) | economy ON, wallet loaded |
| Checkout browsers from inside the live container | Hudson and itch.io both connect (Chromium 156.0.8078.80), after each switch |
| `esim_offers` JP through https://modelmarket.dev (image 1, no wallet, throwaway container) | one seller, the demo reference node, labelled `[DEMO: sells nothing]`; `esim_buy` refuses without a wallet |

The comparison itself is not exercised on prod: the hub lists one eSIM seller, in demo mode, and a purchase is real
money. It is covered by `argus/test/esim.test.ts` (two sellers behind a test hub) and the kit's
`rails/test/agent-buy.test.js` (two kit nodes behind a test hub).

Rollback to the 0.5.0 release image (kept, as is image 1):
`cp -p /root/argus/docker-compose.roster.yml.before-argus-0.5.0-cmp-20261118 /root/argus/docker-compose.roster.yml && docker compose --project-directory /root/argus -f /root/argus/docker-compose.yml -f /root/argus/docker-compose.roster.yml up -d --no-deps --no-build argus`
(`.before-argus-0.5.1-20261118` goes back to image 1 instead.)

Later on 2026-11-18 the owner asked for WARDEN 0.30.0 everywhere («давай сделаем все под 30»), so the release became
ARGUS 0.6.0 (WARDEN 0.30.0, `docs/evidence/argus-0.6.0-npm-2026-11-18/`); 0.5.1 was never published. This build stays
live until WARDEN 0.30.0 is on npm, then prod moves to 0.6.0 (colleague-tasks §130 and §131).
