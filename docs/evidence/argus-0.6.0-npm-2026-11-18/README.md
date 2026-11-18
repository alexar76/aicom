# ARGUS 0.6.0 for npm: built and checked 2026-11-18, not yet published

Built on 2026-11-18 from a clean export (`git archive`) of `73ee0c359` (`argus/`; in main as `95a9f4231` after a rebase
onto `065486353`, `argus/` identical), Node 22.22.1, npm 10.9.4:
`npm ci`, `npm run build`, `npm run typecheck`, `npx vitest run`, `npm pack`. Since npm 0.5.0 (2026-11-17): WARDEN
0.30.0; after a refused eSIM order ARGUS weighs the other sellers' offers and never switches seller by itself (asked on
DEV 2026-11-18); it signs no more than the offer's price; the Docker image builds again — a minor release
(`argus/CHANGELOG.md`, 0.6.0). Prepared first as 0.5.1 on WARDEN 0.29.0 (`d4d159425`); that version was never published,
and its tarball was replaced by this one.

**`@aimarket/warden` 0.30.0 is not on npm yet.** The lock pins it to the WARDEN release tarball
(`warden/docs/evidence/warden-release-0.30.0-2026-11-17/aimarket-warden-0.30.0.tgz`, npm shasum `2c43b950…`, integrity
`sha512-8jQOkrJr…`) at its registry URL. Here it was installed from the npm cache by that integrity (`npm cache add` of the
tarball, then `npm ci --prefer-offline`). Publish ARGUS 0.6.0 only after WARDEN 0.30.0 (colleague-tasks §131 step 1, the
same tarball, not a rebuild); until then `npm install @alexar76/argus3@0.6.0` cannot resolve WARDEN.

The tarball is not in git (12.8 MB). It is kept at
`aicom/artifacts/npm-release-argus3-0.6.0-2026-11-18/alexar76-argus3-0.6.0.tgz` in the main checkout (with `pack.json`,
the `npm pack --json` output); that folder ignores itself (`.gitignore` = `*`). `SHA256SUMS` here pins it:

```
dea86bff155e65c2bfe01dfa78fd146b07d8a868fed51aaed037c456747f2ae0  alexar76-argus3-0.6.0.tgz
```

npm `shasum` e6494d9f9b561624240231613c8852faeeb2744c, integrity `sha512-WuDCiW8eEIkxPfVBIC70bprM…` (full value in
`pack.json`), 15,662 files, 71,033,331 bytes unpacked.

## Checks run

| Check | Result |
|---|---|
| `npm ci`, `npm run build`, `npm run typecheck` in the clean export | exit 0; WARDEN 0.30.0 installed |
| `npx vitest run` | 66 files passed, 2 skipped; 604 tests passed, 13 skipped, 0 failed (in the worktree with the rest of the monorepo: 607 passed, 10 skipped). The six new eSIM tests and the Dockerfile guard fail on the 0.5.0 code |
| Pins: WARDEN 0.29.0 → 0.30.0 (`argus/scripts/warden-pin-compat-check.mjs`, output in `warden-pin-compat-0.29-to-0.30.log`) | plain and rich tool sets stored by 0.29.0 allow under 0.30.0 with no pinning finding; a changed description gives `TOOL_DEF_DRIFT`. The live ARGUS stored its pins with 0.29.0 |
| `npm install <tarball>` in an empty folder, WARDEN overridden to its release tarball | `@alexar76/argus3@0.6.0`, `@aimarket/warden@0.30.0` (integrity `sha512-8jQOkrJr…`), `pdfjs-dist@6.5.438`, `playwright-core@1.64.1`; the installed `esim_buy` describes `cheaper_elsewhere` |
| MCP handshake over pipes (`argus` with no arguments, `initialize`, `tools/list`) | serverInfo `argus 0.6.0`; tools `argus_ask`, `argus_status`, `argus_capabilities` |
| `npm publish <tarball> --access public --dry-run` | `+ @alexar76/argus3@0.6.0`, tag `latest` |
| Unpacked tarball vs npm `@alexar76/argus3@0.5.0` (sha256 `70b66ec9…`), `diff -rq` | own files: `README.md` (install pins), `package.json` (version, `@aimarket/warden` 0.29.0 → 0.30.0), `dist/cli/util.{js,d.ts}` (version), `dist/economy/esim.{js,js.map,d.ts,d.ts.map}`, `dist/tools/esim.{js,js.map,d.ts.map}`. Bundled `node_modules`: no difference |
| Package scan (524 files outside bundled `node_modules`) | no private-host entry from `scripts/.mirror-forbidden-hosts`; no private-key or token pattern; no `.env`, `.pem`, `.key` or `argus.config.json` |
| GitHub mirror export (`audit_satellite_exports.py --satellite argus`, Python 3.12) | passed, on `a932b6106` (later commits change versions, CHANGELOG, the Dockerfile and its test, the WARDEN pin) |

## State on 2026-11-18

- npm `@alexar76/argus3` latest is 0.5.0 (2026-11-17). `@aimarket/warden` 0.30.0 published 08:25:32Z, shasum `2c43b950…`
  and integrity `sha512-8jQOkrJr…` — exactly the pin in the lock.
- GitHub `alexar76/argus`: tag v0.5.0 on the 0.5.0 code; the mirror head (`8f5ed5133`) already carries the eSIM change
  under version 0.5.0. MCP registry `io.github.alexar76/argus3`: 0.4.0. `argus/server.json` says 0.6.0.
- The ARGUS we run on attested: 0.6.0 (WARDEN 0.30.0) since 08:37Z, built from the release sources; its `dist` and `web`
  are this tarball's file by file (`artifacts/argus-0.6.0-prod-2026-11-18/`).

Publishing, the mirror, the tag and the registry entry are the owner's and colleague's steps:
`docs/distribution/colleague-tasks.md` §130, after §131 step 1.
