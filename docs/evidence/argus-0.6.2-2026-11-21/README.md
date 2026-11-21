# ARGUS 0.6.2 on WARDEN 0.35.0 — prepared and live on attested, 2026-11-21

Owner 2026-11-21: ARGUS follows WARDEN to 0.35. Times are UTC from the host clock.

## What changed against 0.6.1

- `@aimarket/warden` 0.33.0 → 0.35.0 (npm shasum `d3ba314d0f805a26b655702e3d23860c599e257b`; the pin went into main
  in `a9897a69a`).
- The version. ARGUS's own code is unchanged.

Nothing ARGUS shows or decides changes. WARDEN 0.34.0 (the direction of a moved behaviour hint) and 0.35.0
(`TOOL_HINT_CONTRADICTS_DESCRIPTION`) add to `warden wrap` and `warden scan`; ARGUS calls the gate (`vet`,
`approve`). `warden-pin-compat.log`, lines 4–6: a `readOnlyHint` that moves true → false after a 0.33.0 approval is
refused under 0.35.0 as `TOOL_DEF_DRIFT` with the text 0.33.0 gives, and a tool whose description contradicts its
`readOnlyHint` gets the same findings from the 0.33.0 and the 0.35.0 gate.

## Checks

| Check | Result |
|---|---|
| Pins stored by WARDEN 0.33.0 under 0.35.0 (`argus/scripts/warden-pin-compat-check.mjs`, both packages from npm) | plain and rich tool sets allowed, no pinning finding; a changed description is caught (`TOOL_DEF_DRIFT`) — `warden-pin-compat.log` |
| Clean export (`git archive`) of `39416d961` (`argus/`), Node 22.22.1, npm 10.9.4: `npm ci` from the registry, build, typecheck | exit 0 |
| `npx vitest run` | 66 files passed, 2 skipped; 604 tests passed, 13 skipped, 0 failed — `tests-summary.log` |
| `npm audit --omit=dev` | 2 moderate, as 0.6.1 |

## Production (attested, container `argus`)

- Image `aicom-security:argus-0.6.2-20261121` = `sha256:40c01896b3a4c722e67dafcd4bd16e5a2b86cbf6f8d60b8f5f7d2016d396e3e4`:
  the running `argus-0.6.1-20261120` image with WARDEN replaced by the npm 0.35.0 package, `/app/dist` from the clean
  build of `39416d961` and that commit's `package.json` and `package-lock.json` (`Dockerfile.overlay`). In the image
  `/app/dist` equals the clean build file for file (517 files, `dist.sha256`).
- The first build was discarded: the archive made on the Mac carried 1,056 AppleDouble `._*` files into the build
  context. They were removed from the kit folder and the image rebuilt without cache; the image has none in
  `/app/dist` and the WARDEN package. The 0.6.1 image was checked too: none.
- 04:47:40–04:47:57 `switch.sh` (the 0.6.1 switch with the names changed): refuses during a purchase, changes the
  image line of `/root/argus/docker-compose.roster.yml`, rolls back on any error. Result: healthy.
- After: `/health` version 0.6.2, mode live, `mcp` connected 1, blocked 0, failed 0 (before: the same on 0.6.1). The
  log shows WARDEN allowing `aimarket-web` (13 tools); no error line in the first minute.
- Rollback: `cp -p /root/argus/docker-compose.roster.yml.before-argus-0.6.2-20261121 /root/argus/docker-compose.roster.yml`
  and `docker compose --project-directory /root/argus -f /root/argus/docker-compose.yml -f /root/argus/docker-compose.roster.yml up -d --no-deps --no-build argus`.
  Kit on the host: `/root/argus-0.6.2-20261121`.

## The npm tarball (built and checked 2026-11-21, not published)

From the same clean export: `npm pack`. Not in git (12.8 MB); kept at
`aicom/artifacts/npm-release-argus3-0.6.2-2026-11-21/alexar76-argus3-0.6.2.tgz` in the main checkout (with
`pack.json`). `SHA256SUMS` here pins it:

```
3fbc59c5c30fb29a26a454468c1f2ff1d9ae2fd3678d3b79e44cf658c7dde806  alexar76-argus3-0.6.2.tgz
```

npm `shasum` a1b2f7c484f022872120fa89badf12d271a9e60a, integrity
`sha512-XXlzcWTfUA0GkuW43oCA9+tvSAmz+LkKSH3tyzNK6af2zR2tTzhZevDieKMU9xf+P/R+0LGgYV5TtL9+HN8tHQ==`, 15,662 files,
71,034,786 bytes unpacked.

| Check | Result |
|---|---|
| `npm install <tarball>` in an empty folder, everything else from the registry | `@alexar76/argus3@0.6.2`, `@aimarket/warden@0.35.0`, `pdfjs-dist@6.5.438`, `playwright-core@1.64.1` |
| MCP handshake over pipes (`argus` with no arguments, `initialize`, `tools/list`) | serverInfo `argus 0.6.2`; tools `argus_ask`, `argus_status`, `argus_capabilities` |
| `npm publish <tarball> --access public --dry-run` | `+ @alexar76/argus3@0.6.2`, tag `latest` |
| Unpacked tarball vs npm `@alexar76/argus3@0.6.1` (registry tarball, shasum `ee28d634…`), `diff -rq` | 4 files: `README.md` (install pins), `package.json` (version, `@aimarket/warden` 0.33.0 → 0.35.0), `dist/cli/util.{js,d.ts}` (version). Bundled `node_modules` identical |
| Package scan (524 files outside bundled `node_modules`) | no private-host entry from `scripts/.mirror-forbidden-hosts`; no private-key or token pattern; no `.env`, `.pem`, `.key` or `argus.config.json` |

State on 2026-11-21 ~04:50Z: npm `@alexar76/argus3` latest is 0.6.1 (published 2026-11-20 10:49Z, shasum equal to the
0.6.1 record); MCP registry `io.github.alexar76/argus3` 0.6.1 (2026-11-20 11:08Z). Publishing 0.6.2, the mirror, the
tag and the registry entry are the owner's and colleague's steps: `docs/distribution/colleague-tasks.md` §141.

## Not done

- `@alexar76/argus3` 0.6.2 is not on npm.
- `argus` and `argus-uni` on factory-vps (ARGUS 0.3.4 with WARDEN 0.8.2) were not touched.
- No purchase was made after the switch.
