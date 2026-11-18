# Live ARGUS on the 0.5.0 release — attested, 2026-11-17 20:23Z

The live ARGUS (container `argus` on attested, @Argis3Bot) ran `aicom-security:argus-acex-text-20261115`: a 0.3.6 base
with `dist/` overlays and WARDEN 0.27.0. It now runs `aicom-security:argus-0.5.0-20261117`
(`sha256:c14f1625…`), built on the host with `argus/Dockerfile` from the release sources (main `5dac9253d`). The owner
asked for it on 2026-11-17 («и прод выкатывай»).

## Before the switch

| Check | Result |
|---|---|
| Image `/app/dist` (517 files) and `/app/web` against the npm tarball (sha256 `70b66ec9…`) | identical, file by file |
| Offline smoke (`--network none --read-only --cap-drop ALL`) | ARGUS 0.5.0, WARDEN 0.29.0 (`MalwareListGate`), `playwright-core` 1.64.1, `pdfjs-dist` 6.5.438; the Hudson Link, itch.io, receipt, Telegram purchase, eSIM, keystore and MCP host modules load |
| Live `/app/dist` against the new one | `.js` changes only in `cli/util.js` (version), `economy/esim.js`, `tools/esim.js`, `economy/keystore.js`; the live tree also held 20 macOS `._*.js` files from earlier overlays, gone now |
| Dependencies against the live image | WARDEN 0.27.0 → 0.29.0, `pdfjs-dist` 5.6.205 → 6.5.438 (with `@napi-rs/canvas` 1.1.1), `@x402/*` 2.28 → 2.30 (as npm 0.4.0), `@noble/*`, `viem`, `ox`, `@modelcontextprotocol/sdk` patch updates; `playwright-core` stays 1.64.1 |
| Playwright client against both live checkout browsers (a throwaway container of the new image on `argus_checkout`, no pages) | itch checkout browser and Hudson browser both connect (Chromium 156.0.8078.80) |
| Purchases in progress | none (Hudson Link and itch.io journals absent or finished; `switch.sh` checks) |

The first 0.5.0 build had `playwright-core` 1.65.0 and would have been refused by both browsers (428, "Playwright version
mismatch"); it was rebuilt before the switch (`argus/CHANGELOG.md`, 0.5.0).

## Switch and after

`switch.sh` (here and in `/root/argus-0.5.0-20261117/` on the host), 20:23:07–20:23:23Z: roster image line changed,
`compose up --no-deps --no-build argus`, healthy, image ID, ARGUS 0.5.0, WARDEN 0.29.0 and Playwright 1.64.1 checked in
the container.

| After (20:24Z) | Result |
|---|---|
| Logs | threat feed loaded (signature valid); chain LIVE Base mainnet; WARDEN `ALLOW aimarket-web`, 13 tools vetted and pinned (pins stored by 0.27.0 verified); `argus serve — http :8787 + telegram`; @Argis3Bot online; 0 error lines |
| `/health` | 200 |
| Wallet (`argus economy status`) | economy ON, wallet loaded: the keystore decrypts with the tag fixed at 16 bytes |
| Checkout browsers from inside the live container | both connect |

Rollback (the previous image is kept):
`cp -p /root/argus/docker-compose.roster.yml.before-argus-0.5.0-20261117 /root/argus/docker-compose.roster.yml && docker compose --project-directory /root/argus -f /root/argus/docker-compose.yml -f /root/argus/docker-compose.roster.yml up -d --no-deps --no-build argus`

Not done here: npm `@alexar76/argus3` 0.5.0, the GitHub mirror, the tag and the MCP registry entry
(`docs/distribution/colleague-tasks.md` §129).
