# ARGUS 0.5.0 for npm: built, checked, published 2026-11-17 20:49:50Z

Built on 2026-11-17 around 21:16Z from a clean export (`git archive`) of main `5dac9253d` (`argus/`), Node 22.22.1,
npm 10.9.4: `npm ci`, `npm run build`, `npm run typecheck`, `npx vitest run`, `npm pack`. Since npm 0.4.0
(2026-11-15): WARDEN 0.27.0 → 0.29.0, the keystore AES-GCM tag fix, `playwright-core` back to 1.64.1, eSIM quote
tokens, `pdfjs-dist` 6.5.438 and the "Agent Capital Exchange" text — a minor release (`argus/CHANGELOG.md`, 0.5.0).

A first tarball of `d5b99cb63` (sha256 `79c5fd8e…`) was replaced before anything used it: preparing the production
switch showed that its `playwright-core` 1.65.0 cannot connect to the 1.64.1 checkout browsers (below).

The tarball is not in git (12.8 MB). It is kept at
`aicom/artifacts/npm-release-argus3-0.5.0-2026-11-17/alexar76-argus3-0.5.0.tgz` in the main checkout; that folder
ignores itself (`.gitignore` = `*`). `SHA256SUMS` here pins it:

```
70b66ec9bf557f3bac6ae081d6c8fe06da01a577379c0b4df2477241d9480dc9  alexar76-argus3-0.5.0.tgz
```

npm `shasum` 6ab4a3232746b4bf4ff62aacf07605b6ebfae33b, integrity `sha512-+ySOSIHWwVlpTcoru+UXehT…` (full value in
`npm pack --json`), 15,662 files, 71,023,441 bytes unpacked.

## Checks run

| Check | Result |
|---|---|
| `npm ci`, `npm run build`, `npm run typecheck` in the clean export | exit 0 |
| `npx vitest run` | 65 files passed, 2 skipped; 595 tests passed, 13 skipped, 0 failed (load average ~16) |
| The itch.io and Hudson Link browser tests | 15 of 15, three runs in a row on `playwright-core` 1.64.1 (load ~22), and in the clean-export run above. At load ~128 (other sessions on this Mac) they time out: Chrome 157 starts in 5 s and opens a page in 7.4 s, and the tests allow 8 s |
| `npm install <tarball>` in an empty folder, `npm ls` | `@alexar76/argus3@0.5.0`, `@aimarket/warden@0.29.0` (exports `MalwareListGate`), `pdfjs-dist@6.5.438`, `playwright-core@1.64.1` |
| Playwright client vs the checkout browser | `test/checkout-browser-version.test.ts`: `package.json`, the kit's Dockerfile base and server tarball, its compose tag and `prepare.sh` all say 1.64.1 (the test fails on 1.65.0). The 1.64.1 server's `userAgentVersionMatchesErrorMessage` answers another major.minor with 428 on the WebSocket upgrade; both checkout browsers on attested run 1.64.1 |
| MCP handshake over pipes (`argus` with no arguments, `initialize`, `tools/list`) | serverInfo `argus 0.5.0`; tools `argus_ask`, `argus_status`, `argus_capabilities` |
| `npm publish <tarball> --access public --dry-run` | `+ @alexar76/argus3@0.5.0`, tag `latest` |
| Unpacked tarball vs npm `@alexar76/argus3@0.4.0`, `diff -rq` | own files: `README.md`, `package.json`, `dist/cli/util.js` (version), `dist/economy/esim.js`, `dist/tools/esim.js`, `dist/economy/keystore.js`, `dist/ecosystem/knowledge.js` and their `.d.ts`/`.map`. Bundled `node_modules`: no difference |
| Package scan (files outside bundled `node_modules`) | no private-host entry from `scripts/.mirror-forbidden-hosts`; no private-key, token or 32-byte hex pattern; no `.env`, `.pem`, `.key` or `argus.config.json` |
| Pins: WARDEN 0.27.0 → 0.29.0 (`argus/scripts/warden-pin-compat-check.mjs`) | plain and rich tool sets allow with no pinning finding; a changed description gives `TOOL_DEF_DRIFT` |

## State on 2026-11-17

- npm `@alexar76/argus3` latest is 0.4.0 (2026-11-15), depending on `@aimarket/warden` 0.27.0.
- GitHub `alexar76/argus`: last tag v0.4.0. MCP registry `io.github.alexar76/argus3`: 0.4.0. `argus/server.json` now
  says 0.5.0.
- The ARGUS we run on attested: see `artifacts/argus-0.5.0-prod-2026-11-17/`.

Publishing, the mirror, the tag and the registry entry are the owner's and colleague's steps:
`docs/distribution/colleague-tasks.md` §129.

## Published (checked 2026-11-17 ~21:00Z)

- npm `@alexar76/argus3@0.5.0`, published 2026-11-17T20:49:50.604Z (registry time), `dist.shasum`
  6ab4a3232746b4bf4ff62aacf07605b6ebfae33b and `dist.integrity` sha512-+ySOSIHWwVlpTcoru+UXehT… — the tarball above
  (the rebuilt one with `playwright-core` 1.64.1), byte for byte; `latest` = 0.5.0.
- `npm install @alexar76/argus3@0.5.0` in an empty folder: WARDEN 0.29.0, `playwright-core` 1.64.1, `pdfjs-dist` 6.5.438;
  MCP handshake reports `argus 0.5.0`.
- Not yet: GitHub mirror and tag v0.5.0, MCP registry `io.github.alexar76/argus3` (colleague-tasks §129 steps 2–4).
