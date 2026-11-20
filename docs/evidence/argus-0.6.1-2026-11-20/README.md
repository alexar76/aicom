# ARGUS 0.6.1 on WARDEN 0.33.0 — prepared and live on attested, 2026-11-20

Owner 2026-11-20: move ARGUS to WARDEN 0.33. Times are UTC from the host clock.

## What changed against 0.6.0

- `@aimarket/warden` 0.30.0 → 0.33.0 (npm; the registry tarball equals the recorded release archive, sha256
  `31de2475…`).
- The built-in list of ecosystem components (`src/ecosystem/knowledge.ts`, already in main since `9d1bfd55c`).
- The version. The lock file changes only in these lines; the other dependencies are 0.6.0's.

## Checks

| Check | Result |
|---|---|
| Pins stored by WARDEN 0.30.0 under 0.33.0 (`argus/scripts/warden-pin-compat-check.mjs`, both packages from npm) | plain and rich tool sets allowed, no pinning finding; a changed description is caught (`TOOL_DEF_DRIFT`) — `warden-pin-compat.log` |
| Clean copy of the committed sources: `npm ci` from the registry, build, tests | 604 passed, 13 skipped (66 files) — `tests-summary.log` |
| `npm audit --omit=dev` | 2 moderate; WARDEN has no runtime dependencies, so they are 0.6.0's |

## Production (attested, container `argus`)

- Image `aicom-security:argus-0.6.1-20261120` = `sha256:257cb577be4243aed83edd208749a17648fb7c1d30ddf10dd85df5852cafbe01`:
  the running `argus-0.6.0-20261118` image with WARDEN replaced by the npm 0.33.0 package, `/app/dist` built from
  aicom `7ee40693a` and that commit's `package.json` and `package-lock.json` (`Dockerfile.overlay`). In the image
  `/app/dist` equals the clean build file for file (`dist.sha256`); against the 0.6.0 image six files differ
  (`cli/util.*`, `ecosystem/knowledge.*`). playwright-core stays 1.64.1.
- 09:56:53–09:57:10 `switch.sh` (the 0.6.0 switch with the names changed): refuses during a purchase, changes the
  image line of `/root/argus/docker-compose.roster.yml`, rolls back on any error. Result: healthy.
- After: `/health` version 0.6.1, mode live, `mcp` connected 1, blocked 0, failed 0 (before: the same on 0.6.0). The
  log shows WARDEN allowing `aimarket-web` (13 tools); no error line in the first minutes.
- Rollback: `cp -p /root/argus/docker-compose.roster.yml.before-argus-0.6.1-20261120 /root/argus/docker-compose.roster.yml`
  and `docker compose --project-directory /root/argus -f /root/argus/docker-compose.yml -f /root/argus/docker-compose.roster.yml up -d --no-deps --no-build argus`.
  Kit on the host: `/root/argus-0.6.1-20261120`.

## The npm tarball (built and checked 2026-11-20, not yet published)

Built from a clean export (`git archive`) of `7ee40693a` (`argus/`), Node 22.22.1, npm 10.9.4: `npm ci` (WARDEN 0.33.0
from the registry), `npm run build`, `npm run typecheck`, `npx vitest run`, `npm pack`.

The tarball is not in git (12.8 MB). It is kept at
`aicom/artifacts/npm-release-argus3-0.6.1-2026-11-20/alexar76-argus3-0.6.1.tgz` in the main checkout (with `pack.json`);
that folder ignores itself. `SHA256SUMS` here pins it:

```
ac47d5ab638b7de773327955bfdf3fd6609c946de7bd3da632a3fb72847446c4  alexar76-argus3-0.6.1.tgz
```

npm `shasum` ee28d634198d7da1e59d5adf21ff850c03bc8217, integrity
`sha512-qXQcwU2VWJ7v4mFKol8AsfrfSVZlOYgy8JAsElIBqhkFRrCb44azgvQdJ393mQsx73g915nZSzDjT+IP4Wg+7A==`, 15,662 files,
71,034,786 bytes unpacked.

| Check | Result |
|---|---|
| `npm ci`, build, typecheck in the clean export | exit 0 |
| `npx vitest run` | 66 files passed, 2 skipped; 604 tests passed, 13 skipped, 0 failed |
| `npm install <tarball>` in an empty folder, everything else from the registry | `@alexar76/argus3@0.6.1`, `@aimarket/warden@0.33.0`, `pdfjs-dist@6.5.438`, `playwright-core@1.64.1` |
| MCP handshake over pipes (`argus` with no arguments, `initialize`, `tools/list`) | serverInfo `argus 0.6.1`; tools `argus_ask`, `argus_status`, `argus_capabilities` |
| `npm publish <tarball> --access public --dry-run` | `+ @alexar76/argus3@0.6.1`, tag `latest` |
| Unpacked tarball vs npm `@alexar76/argus3@0.6.0` (registry tarball, sha256 `dea86bff…`), `diff -rq` | 8 files: `README.md` (install pins), `package.json` (version, `@aimarket/warden` 0.30.0 → 0.33.0), `dist/cli/util.{js,d.ts}` (version), `dist/ecosystem/knowledge.{js,js.map,d.ts,d.ts.map}`. Bundled `node_modules` identical |
| Package scan (524 files outside bundled `node_modules`) | no private-host entry from `scripts/.mirror-forbidden-hosts`; no private-key or token pattern; no `.env`, `.pem`, `.key` or `argus.config.json` |
| GitHub mirror export (`audit_satellite_exports.py --satellite argus`, from the main checkout on `9db13e23b`) | passed |

State on 2026-11-20 ~10:40Z: npm `@alexar76/argus3` latest is 0.6.0; MCP registry `io.github.alexar76/argus3` 0.6.0;
`@aimarket/warden` 0.33.0 is on npm with the integrity the lock pins. Publishing, the mirror, the tag and the registry
entry are the owner's and colleague's steps: `docs/distribution/colleague-tasks.md` §140.

## Not done

- `@alexar76/argus3` 0.6.1 is not on npm yet (the tarball is ready, see above). The mirror, the tag and the MCP
  registry entry of ARGUS stay at 0.6.0 until colleague-tasks §140.
- `argus` and `argus-uni` on factory-vps are separate older instances (ARGUS 0.3.4 with WARDEN 0.8.2, running since
  2026-11-14). They were not touched.
- No purchase was made after the switch.
