# npm releases prepared on 2026-11-03

**Not uploaded.** Each tarball here was packed from git `10ca42566` in a clean export (`git archive`, then
`npm ci`, `npm run build`, `npm test`, `npm pack`), never from the main checkout. The tarballs are git-ignored;
`SHA256SUMS` is tracked. Publish these files as they are rather than rebuilding: the main checkout's
`dioscuri/dist/` holds eight stale `images/cards*` files that `scripts/publish_npm.sh dioscuri` would pack.

| Package | npm now | Here | Why |
|---|---|---|---|
| `@alexar76/awr-verify` | 2.0.0 | 2.0.1 | security: small-order Ed25519 forgery accepted on the default (WebCrypto) and BigInt paths |
| `@aimarket/widget` | 0.1.1 | 0.1.2 | security: hub-relayed result fields escaped; paid channel calls send the channel secret |
| `@aimarket/agent` | 0.3.0 | 0.4.0 | security: paid invokes never replayed, no redirects, strict seeds (with Rust and Dart, below) |
| `@aimarket/esim-rails` | 0.3.0 | 0.4.0 | one supplier purchase per paid order; patched Zod 4 x402 builds bundled |
| `@alexar76/dioscuri` | 0.1.0 | 0.2.0 | audit pseudonyms, bounded LLM answers, modules added since July |
| `aicom-landing` | 0.1.1 | 0.2.0 | security: prompt firewall, image-probe SSRF guard, sandboxed previews |
| `create-aimarket-agent` | never published | 0.1.1 | optional: claims the name; same version as the PyPI flavour |

Changelogs: `docs/verifier/js/CHANGELOG.md`, `aimarket-widget/CHANGELOG.md`, `aimarket-sdks/*/CHANGELOG.md`,
`esim-kit/CHANGELOG.md`, `dioscuri/CHANGELOG.md`, `aicom-landing/CHANGELOG.md`.

## Checks

| Check | Result |
|---|---|
| Package tests in the clean export | all pass; DIOSCURI 390/390 (one run hit the known `ENOTEMPTY` temp-dir race in `theoxenia.test.ts`; two reruns clean) |
| AWR/2 conformance, `browser-node` | 118 of 118 |
| New `test-ed25519-small-order.js` | fails on the previous `verifier.js`, passes now |
| Contents against the published version | only the files the changelogs name; against a build of the previous commit, only `package.json`, README and `verifier.js` differ |
| Secret gate (`scripts/verify_distribution_secrets.py`) | clean, except 19 hits in esim-rails, all inside bundled third-party `node_modules/` (`@noble/curves` BLS12-381 constants, `ox` test files), as in the published `@alexar76/argus3` 0.3.4 |
| Install into an empty project | each installs; awr-verify refuses the forgery and accepts RFC 8032 TEST 1; the SDK refuses a short seed; esim-rails loads its bundled `@x402/*` and `@aimarket/x402-cdp`; DIOSCURI starts without credentials and opens its health port; CLIs answer `--help` |
| SDK parity (`scripts/check_ecosystem_parity.py`) | all three SDKs at 0.4.0 |
| Rust `aimarket-agent` 0.4.0 | `cargo test --locked`: 55 passed; `cargo publish --dry-run` passes |
| Dart `aimarket_agent` 0.4.0 | `dart test`: 106 passed; `dart pub publish --dry-run`: one layout warning (plural directory name), as before |

`esim-rails` grows from 30 KB to 13 MB packed: its patched `@x402/*` builds are not on the registry, so npm bundles
them with their dependencies, as `@alexar76/argus3` has done since 0.3.4.

## Upload (owner)

From the `aicom` folder, after `npm login` as alexar76 (npm asks for the 2FA code on each publish):

```bash
cd artifacts/npm-release-2026-11-03 && shasum -a 256 -c SHA256SUMS
npm publish ./alexar76-awr-verify-2.0.1.tgz --access public
npm publish ./aimarket-widget-0.1.2.tgz --access public
npm publish ./aimarket-agent-0.4.0.tgz --access public
npm publish ./aimarket-esim-rails-0.4.0.tgz --access public
npm publish ./alexar76-dioscuri-0.2.0.tgz --access public
npm publish ./aicom-landing-0.2.0.tgz --access public
npm publish ./create-aimarket-agent-0.1.1.tgz --access public   # optional, claims the name
```

The SDK release is three registries at one version. Either the usual route (mirror `aimarket-sdks`, then the
`v0.4.0` GitHub release runs `release.yml` for all three; then skip the `@aimarket/agent` line above), or by hand
from a clean export of `10ca42566`: `cargo publish` in `aimarket-sdks/rust`, `dart pub publish` in
`aimarket-sdks/dart`.

After upload, compare what the registries serve with these files (`npm view <name>@<version> dist.shasum` against
`shasum <file>`), and check `npm view <name> version` for each.
