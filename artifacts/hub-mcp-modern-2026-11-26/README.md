# MCP 2026-07-28 beside the handshake: six hubs and the tools service — 2026-11-26

**Why.** Our measurement article of the same day says that of our eleven readable MCP registry entries one answers
MCP 2026-07-28 and "we have not moved them yet". Owner, 26.11: «делай». Revision 2026-07-28 has no `initialize`:
a request names its protocol version and the client's capabilities in `params._meta`, mirrors version, method and
tool name into HTTP headers, and `server/discover` says what a server speaks.

## Change (main 9886575bc)

- Hub (`aimarket-hub` 3.22.4): `mcp_modern.py` (era detection, the header/body checks with `-32020` and `-32022`,
  the fields every result carries), `mcp_gateway.py` (a modern request gets a stateless JSON answer; `initialize`,
  `ping`, sessions are HTTP 404 `-32601` there), `hub_routes/ai_catalog.py` and the packaged server card (versions
  listed, MCP server version 1.3.0 → 1.4.0). No migration, nothing stored changes.
- Tools service (`okx-a2mcp`): `src/mcp/modern.js`, `server.js`, `pages.js`; server version 1.0.0 → 1.1.0.
- Handshake clients get the same answers as before: `initialize` still opens a session on the hubs and still
  negotiates 2025-06-18; the tool lists are equal in both eras (checked in every smoke and from outside).

## Kits

`kit/` (on each hub host `/root/hub-mcp0728-20261126`). The hubs ran three different `mcp_gateway.py`, so
`kit/gateway/` holds each running variant with the same 140-line patch applied (all applied cleanly):

| running file | what it is | hubs |
|---|---|---|
| `a81bde47a61d` | 3.22.0 | hunt, uni, Attested Memory, Independent |
| `c78c8d068d88` | another session's Tutu build | hub.modelmarket.dev |
| `b5600ddedee0` | main before this change (HALOWERK pilot build) | modelmarket.dev |

Before any host: the 3.22.0 and Tutu variants were tested in hub trees checked out at their own commits
(63291e197, f537e5654) with main's `test_mcp_modern.py`, `test_mcp_gateway.py`, `test_ai_catalog.py` — 162 passed
each. `build.sh` refuses unless the running files are the expected versions and the container holds no file its
image lacks (a change copied in by another session). `smoke.sh` runs `smoke_mcp.py` inside the new image with no
network on a throw-away database: handshake (session, 2025-06-18, tools, ping), `server/discover`, equal tool
lists, a `market_search` call, the three refusals, the documents that state the versions. No database backup was
taken: the change has no migration and writes nothing new.

`tools-kit/` (factory-vps `/root/tools-mcp0728-20261126`): the same for `okx-a2mcp`; `smoke.mjs` starts the app in
the new image with stub upstreams and checks the four profiles in both eras.

## Per service (server UTC)

| service | switched | previous container (rollback) |
|---|---|---|
| hub.modelmarket.dev (canary), competing-lab `modelmarket-hub` | 19:46:00Z | `modelmarket-hub-security-prev-1795722361077497271` |
| hunt.modelmarket.dev, competing-lab `signal-hunt-hub-1` | 19:46:42Z | `signal-hunt-hub-1-security-prev-1795722402446055656` |
| uni.modelmarket.dev, factory-vps `modelmarket-hub-uni` | 19:47:25Z | `modelmarket-hub-uni-security-prev-1795722445659300112` |
| modelmarket.dev, factory-vps `modelmarket-hub` (+ THEMIS), right after the 19:48:49Z payout run, borrowers = themis | 19:48:50Z | `modelmarket-hub-security-prev-1795722530476542902`, `themis-security-prev-1795722530476542902` |
| hub.attestedmemory.net, attested `attested-memory-hub-hub-1` | 19:51:22Z | `attested-memory-hub-hub-1-security-prev-1795722682368958617` |
| independentai.network/hub, indep `independentai-hub.service` | 19:52:24Z | `./indep.sh rollback` (drop-in 99k → back to the httpvalid venv via 99j) |
| modelmarket.dev/tools/mcp/*, factory-vps `okx-a2mcp` | 19:53:53Z | `okx-a2mcp-security-prev-1795722833895975197` |

Container rollback: `cd /root/hub-mcp0728-20261126 && python3 rollout_container.py <container> --rollback`
(tools service: the same from `/root/tools-mcp0728-20261126`).

New images: `<previous tag without -httpvalid-20261126>-mcp0728-20261126` for the hubs,
`okx-a2mcp:okx-list-new-20261125-blD2MjSb-mcp0728-20261126` for the tools service.

## Checks after, from outside (`kit/probe.sh URL`, 19:46–19:55Z)

Before, every endpoint answered `server/discover` with `-32601 Method not found`.

- Six hubs (`/mcp`): `server/discover` HTTP 200 `application/json`, `supportedVersions`
  `2026-07-28, 2025-06-18, 2025-03-26, 2024-11-05`, serverInfo `aimarket-hub-mcp 1.4.0`, `resultType complete`,
  `ttlMs 300000`, `cacheScope public`; `tools/list` 13 tools (uni 8), `ttlMs 60000`; `initialize` still 2025-06-18
  with a session. Health 200 on all six.
- modelmarket.dev: one real call in the new era, `tools/call market_search` → HTTP 200, `resultType complete`; the
  same call with a wrong `Mcp-Name` header → HTTP 400. `/mcp/server-card` lists the four versions. The publisher
  payout ran again at 19:49:55Z (exit 0); THEMIS healthy.
- Tools service, four profiles and the `emporion` alias: `server/discover` lists
  `2026-07-28, 2025-11-25, 2025-06-18, 2025-03-26, 2024-11-05`, version 1.1.0, the tool counts as before
  (weather 3, security 4, domains 1, symmartys 8); `/tools/`, `/tools/mcp`, `/a2mcp` 200.

## Not done here

- `__version__` on the hubs still says 3.22.0: the overlays replace files, not the package metadata.
- PyPI `aimarket-hub` 3.22.4 was uploaded at 19:49Z by someone else (built in the main checkout); its wheel and
  sdist equal a clean build of 9886575bc file for file (245 and 519 files). The MCP registry still lists 3.22.0.
- The three PyPI packages and WARDEN: ../mcp-2026-07-28-packages-2026-11-26/README.md.
