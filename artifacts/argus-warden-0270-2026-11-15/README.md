# Live ARGUS on WARDEN 0.27.0 — attested, 2026-11-15 16:59Z

The live ARGUS (container `argus` on attested, @Argis3Bot) ran WARDEN 0.24.0 inside image
`aicom-security:argus-hudson-auto-receipt-20261114`. It now runs `aicom-security:argus-warden-0270-20261115`
(`sha256:fecd0a09…`): the same image with only `/app/node_modules/@aimarket/warden` replaced by the published
0.27.0 package (tarball sha256 `525622b7…`, checked on the host; build digest `403842d7…`, the one MOMUS accepted).
The owner asked for it on 2026-11-15 («Собирай ARGUS»).

Why only WARDEN: the live image's five modules that import WARDEN (`runtime.js`, `mcp/host.js`, `core/agent.js`,
`verify/index.js`, `cli/commands/warden.js`) are byte for byte a build of main `5ef92aec0`, where ARGUS typechecks and
591 tests pass against 0.27.0. Every name they import exists in 0.27.0. The rest of ARGUS is unchanged.

| Step | Result |
|---|---|
| Purchases before restart | Hudson Link journal `stage=delivered`; eSIM file unchanged since 2026-10-15 |
| Offline smoke of the new image (`--network none --read-only`) | the five modules load; WARDEN 0.27.0, ruleset 20, build digest `403842d70620a8dd`; a weather tool allowed, an EVM opcode "mnemonic" tool allowed (warden#14), "Provide your mnemonic…" blocked |
| Switch (`switch.sh`, 16:59:35–16:59:53Z) | roster image line changed, `compose up --no-deps --no-build argus`, healthy, WARDEN 0.27.0 in the container |
| After | `aimarket-web` ALLOW, 13 tools vetted and pinned; `argus serve — http :8787 + telegram`; @Argis3Bot online; `/health` 200; no error lines (`after.txt`, 17:00:16Z) |

Rollback (the previous image is kept):
`cp -p /root/argus/docker-compose.roster.yml.before-argus-warden-0270-20261115 /root/argus/docker-compose.roster.yml && docker compose --project-directory /root/argus -f /root/argus/docker-compose.yml -f /root/argus/docker-compose.roster.yml up -d --no-deps --no-build argus`

On the host: `/root/argus-warden-0270-20261115/` holds the tarball, its checksum file, this Dockerfile and `switch.sh`.
Not changed: npm `@alexar76/argus3` 0.3.6 still depends on WARDEN 0.24.0 (a 0.3.7 release is the owner's decision).
