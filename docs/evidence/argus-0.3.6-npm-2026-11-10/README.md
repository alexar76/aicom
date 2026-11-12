# ARGUS 0.3.6 for npm: built and checked, not published

Built on 2026-11-10 around 09:20Z (server time; this Mac's clock runs about an hour fast) from this commit's `argus/`.
The only change from 0.3.5 is the `@aimarket/warden` dependency, 0.8.2 → 0.24.0 (see `argus/CHANGELOG.md`).

The tarball is not in git (11.8 MB). It is kept at
`aicom/artifacts/npm-release-argus3-0.3.6-2026-11-10/alexar76-argus3-0.3.6.tgz` in the main checkout. That folder
ignores itself (`.gitignore` = `*`). `SHA256SUMS` here pins it:

```
bbedea55124971461c97d444095c4d290b9227fc55e282f5c7eaf78a4a275c20  alexar76-argus3-0.3.6.tgz
```

npm `shasum` bfc9d64d0650fff7c9bded7a45bd286ba835abc6, 15,380 files, 65,891,982 bytes unpacked.

## Checks run

| Check | Result |
|---|---|
| `npm ci`, `npm run build`, `npm run typecheck` (Node 22.22.1, npm 10.9.4) | exit 0 |
| `npm test` (vitest) | 45 files passed, 2 skipped; 408 tests passed, 10 skipped, 0 failed |
| Unpacked tarball vs the published `@alexar76/argus3@0.3.5` tarball, `diff -rq` | 3 files differ, listed below |
| `npm install <tarball>` in an empty folder, then `npm ls @aimarket/warden` | `@aimarket/warden@0.24.0` |
| MCP handshake over pipes (`argus` with no arguments, `initialize` then `tools/list`) | serverInfo `argus 0.3.6`; tools `argus_ask`, `argus_status`, `argus_capabilities` |
| `npm publish <tarball> --access public --dry-run` | `+ @alexar76/argus3@0.3.6`, tag `latest` |

Earlier, in commit b0f553024: pins stored by WARDEN 0.8.2 verify under 0.24.0, and a changed description still drifts
(`argus/scripts/warden-pin-compat-check.mjs`).

The three files that differ from 0.3.5:

```
dist/cli/util.d.ts   VERSION = "0.3.5"  →  "0.3.6"
dist/cli/util.js     VERSION = "0.3.5"  →  "0.3.6"
package.json         "version": "0.3.5" →  "0.3.6"
                     "@aimarket/warden": "0.8.2" → "0.24.0"
```

The bundled dependencies (`@x402/*`, viem, ox, zod and their trees under `node_modules/`) are byte-identical to
0.3.5. 0.3.4 and 0.3.5 have the same 15,380 files.

## State of the registries on 2026-11-10

- npm `@alexar76/argus3` latest is 0.3.5 (2026-11-08) with `@aimarket/warden` 0.8.2.
- npm `argus-warden` (the old name) latest is 0.3.1 (2026-08-24) with `@aimarket/warden` 0.4.0. It was downloaded 12
  times in the week from 11-02 to 11-08.
- The MCP registry's latest `io.github.alexar76/argus3` entry is 0.3.4, and it points at npm 0.3.3.
  `argus/server.json` now says 0.3.6.

Publishing is the owner's step: `docs/distribution/colleague-tasks.md` §85.
