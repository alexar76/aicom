# ARGUS 0.4.0 for npm: built, checked, published 2026-11-15 17:42:34Z

Built on 2026-11-15 around 17:20Z from a clean worktree of main `d50c97d6e` (`argus/`), Node 22.22.1, npm 10.9.4.
Since npm 0.3.6: WARDEN 0.24.0 → 0.27.0, mail, opt-in purchases from Telegram, owner-approved paid lookups, new
dependencies and the `@aimarket/agent` peer range ^0.4.0 — a minor release (see `argus/CHANGELOG.md`).

The tarball is not in git (12.8 MB). It is kept at
`aicom/artifacts/npm-release-argus3-0.4.0-2026-11-15/alexar76-argus3-0.4.0.tgz` in the main checkout; that folder
ignores itself (`.gitignore` = `*`). `SHA256SUMS` here pins it:

```
d7be72d6058dcc64a87c8a7de5c32791c20e22440609dc3a624a58d9c0602678  alexar76-argus3-0.4.0.tgz
```

npm `shasum` 7846ba5b1b979aefa5dd0f30ea9836546b3327ea, integrity `sha512-an3zH608/vD3haLcGbLA2eO…` (full value in
`npm pack --json`), 15,662 files, 71,019,352 bytes unpacked.

## Checks run

| Check | Result |
|---|---|
| `npm ci`, `npm run build`, `npm run typecheck` in the clean worktree | exit 0 |
| `npx vitest run` | 64 files passed, 2 skipped; 591 tests passed, 10 skipped, 0 failed |
| `npm install <tarball>` in an empty folder, `npm ls @aimarket/warden` | `@aimarket/warden@0.27.0`; installed `@alexar76/argus3` 0.4.0 |
| MCP handshake over pipes (`argus` with no arguments, `initialize`, `tools/list`) | serverInfo `argus 0.4.0`; tools `argus_ask`, `argus_status`, `argus_capabilities` |
| `npm publish <tarball> --access public --dry-run` | `+ @alexar76/argus3@0.4.0`, tag `latest` |
| Unpacked tarball vs npm `@alexar76/argus3@0.3.6`, `diff -rq` | 2,585 files differ, 458 only on one side (new `dist/checkout`, `dist/mail`, mail CLI; bundled `@x402/*` 2.28 → 2.30) |
| Package scan | no file matches a private-host entry from `scripts/.mirror-forbidden-hosts`; no private-key or token pattern in `dist/`, `web/`, `vendor/`, the example config; no `.env`, `.pem`, `.key` or `argus.config.json` |
| Pins: WARDEN 0.24.0 → 0.27.0 (`argus/scripts/warden-pin-compat-check.mjs`) | plain and rich tool sets allow with no pinning finding; a changed description gives `TOOL_DEF_DRIFT` |
| GitHub mirror export of `d50c97d6e` (`git archive`, `purge-satellite-excludes argus`, `verify_mirror_secrets.sh`) | OK |

The ARGUS we run on attested has used WARDEN 0.27.0 since 2026-11-15 16:59Z (overlay image; record in
`artifacts/argus-warden-0270-2026-11-15/`).

## State on 2026-11-15

- npm `@alexar76/argus3` latest is 0.3.6 (2026-11-10), depending on `@aimarket/warden` 0.24.0.
- GitHub `alexar76/argus` was synced at 11:37Z from main (package.json 0.3.6, WARDEN 0.25.0); last tag v0.3.6.
- MCP registry `io.github.alexar76/argus3` latest is 0.3.6. `argus/server.json` now says 0.4.0.
- npm `argus-warden` (the old unscoped name) stays at 0.3.1; this release does not touch it.

Publishing, the mirror, the tag and the registry entry are the owner's and colleague's steps:
`docs/distribution/colleague-tasks.md` §116.

## Published (checked 2026-11-15 ~20:40Z)

- npm `@alexar76/argus3@0.4.0`, published 2026-11-15T17:42:34.083Z (registry time), `dist.shasum`
  7846ba5b1b979aefa5dd0f30ea9836546b3327ea and `dist.integrity` sha512-an3zH608… — the tarball above, byte for byte;
  `@aimarket/warden` 0.27.0; `latest` = 0.4.0.
- GitHub `alexar76/argus`: `package.json` 0.4.0, tag v0.4.0. Official MCP registry `io.github.alexar76/argus3`: 0.4.0.
- The later public-text change (Agent Capital Exchange instead of ACEX in ARGUS's ecosystem knowledge, main db2c06de7)
  and the pdfjs-dist bump (abc42d4d9) are not in 0.4.0; they go in the next release.

