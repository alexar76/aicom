# Live ARGUS on 0.6.0 (WARDEN 0.30.0) — attested, 2026-11-18 08:37Z

The live ARGUS (container `argus` on attested, @Argis3Bot) ran `aicom-security:argus-0.5.1-20261118`, the 0.5.1 build
with WARDEN 0.29.0 (`artifacts/argus-0.5.1-prod-2026-11-18/`). It now runs `aicom-security:argus-0.6.0-20261118`
(`sha256:9501a47b…`), built on the host with `argus/Dockerfile` from the 0.6.0 release sources (main `46060eaaa`). The
owner asked for WARDEN 0.30.0 everywhere («давай сделаем все под 30»), published WARDEN 0.30.0 to npm at
08:25:32Z (shasum `2c43b950…`), and the Docker build installs it from the registry.

## Before the switch

| Check | Result |
|---|---|
| `https://registry.npmjs.org/@aimarket/warden/-/warden-0.30.0.tgz` | HTTP 200; the build's `npm ci` resolved it by the lock's integrity |
| Image `/app/dist` (517 files) and `/app/web` against the ARGUS 0.6.0 npm tarball (sha256 `dea86bff…`) | identical, file by file |
| `/app/node_modules/@aimarket/warden` against the npm 0.30.0 tarball (downloaded on the host, sha1 `2c43b950…`) | every file identical |
| `node_modules/**/package.json` (depth 3) against the live 0.5.1 container | 278 files; only `@aimarket/warden/package.json` differs |
| Versions in the image | ARGUS 0.6.0, WARDEN 0.30.0, `playwright-core` 1.64.1 |
| Pins | WARDEN 0.30.0 verifies pins stored by 0.29.0 (`docs/evidence/argus-0.6.0-npm-2026-11-18/warden-pin-compat-0.29-to-0.30.log`) |
| Purchases in progress | none (`switch.sh` checks the Hudson Link and itch.io journals) |

## Switch and after

`switch.sh` (here and in `/root/argus-0.6.0-20261118/` on the host), 08:37:20–08:37:36Z: roster image line changed,
`compose up --no-deps --no-build argus`, healthy, image ID, ARGUS 0.6.0, WARDEN 0.30.0 and Playwright 1.64.1 checked
in the container.

| After (08:37–08:39Z) | Result |
|---|---|
| Logs | threat feed loaded (signature valid); chain LIVE Base mainnet; WARDEN 0.30.0 `ALLOW aimarket-web`, 13 tools pinned (the stored pins verified); `argus serve — http :8787 + telegram`; @Argis3Bot online; 0 error lines |
| `/health` | 200 |
| Wallet (`argus economy status`) | economy ON, wallet loaded |
| Checkout browsers from inside the live container | Hudson and itch.io both connect (Chromium 156.0.8078.80) |

Rollback to the 0.5.1 build (kept, as are the 0.5.0 release and comparison images):
`cp -p /root/argus/docker-compose.roster.yml.before-argus-0.6.0-20261118 /root/argus/docker-compose.roster.yml && docker compose --project-directory /root/argus -f /root/argus/docker-compose.yml -f /root/argus/docker-compose.roster.yml up -d --no-deps --no-build argus`

npm `@alexar76/argus3` 0.6.0, the mirror, the tag and the registry entry: `docs/distribution/colleague-tasks.md` §130.
