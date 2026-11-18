# esim-rails 0.5.1 for npm: built and checked 2026-11-18, not yet published

Built on 2026-11-18 around 05:24Z from a clean export (`git archive`) of main `d4d159425` (`esim-kit/rails` and
`esim-kit/config`), Node 22.22.1, npm 10.9.4: `npm ci`, `npm test`, `npm run build`, `npm pack`. Since npm 0.5.0
(2026-11-17): the example buyer in the package compares again after a refused order (asked on DEV 2026-11-18). The node
is unchanged — see `esim-kit/CHANGELOG.md`, section 0.5.1.

The tarball is not in git (13.5 MB). It is kept at
`aicom/artifacts/npm-release-esim-rails-0.5.1-2026-11-18/aimarket-esim-rails-0.5.1.tgz` in the main checkout (with
`pack.json`, the `npm pack --json` output); that folder ignores itself (`.gitignore` = `*`). `SHA256SUMS` here pins it:

```
d077bb57998439b0778e4bc456f0b9c38bfbeac0b72378b5c654161809c6acf9  aimarket-esim-rails-0.5.1.tgz
```

npm `shasum` 278ca1e786b73ae08ab1735138fb911d4d013fb0, integrity `sha512-WHd77wbkpZp0RLLwZZPowRjT+…` (full value in
`pack.json`), 15,446 files, 68,526,501 bytes unpacked.

## Checks run

| Check | Result |
|---|---|
| `npm test` in the clean export | 80 of 80; `test/agent-buy.test.js` runs the example with its x402 client against two kit nodes behind a test hub: moves to the other seller when the refused seller's new price is above that seller's quote, stays when the kept price is still the cheapest, signs nothing for a seller asking more than its quote, pays a lone seller's new price within `--max-usd` and stops at it. The five fail on the 0.5.0 example |
| `npm run build` | exit 0 |
| `npm install <tarball>` in an empty folder | `@aimarket/esim-rails@0.5.1`; the packaged `examples/agent-buy.mjs` quotes https://modelmarket.dev/providers/esim and skips it (demo); `esim-rails check` of that node: "Conforms to esim.*@v1", "quoted price kept — 10 min", "a changed quote_token is a 400" |
| `npm publish <tarball> --access public --dry-run` | `+ @aimarket/esim-rails@0.5.1`, tag `latest` |
| Unpacked tarball vs npm `@aimarket/esim-rails@0.5.0` (sha256 `d367f96c…`), `diff -rq` | own files: `examples/agent-buy.mjs` and `package.json` only. Bundled `node_modules`: no difference |
| Package scan (47 files outside bundled `node_modules`) | no private-host entry from `scripts/.mirror-forbidden-hosts`; no private-key, npm, GitHub or API token pattern; no `.env`, `.pem`, `.key` |
| GitHub mirror export (`audit_satellite_exports.py --satellite esim-kit`, Python 3.12) | passed, on `a932b6106` (the code; `d4d159425` changes only versions and CHANGELOGs) |

## State on 2026-11-18 05:35Z

- npm `@aimarket/esim-rails` latest is 0.5.0 (2026-11-17).
- The reference node (modelmarket.dev/providers/esim) is unchanged: the node code is the same as 0.5.0.
- GitHub `alexar76/esim-operator-kit`: synced 2026-11-17 20:38Z from a commit before the 0.5.0 version bump.

Publishing and the mirror are the owner's and colleague's steps: `docs/distribution/colleague-tasks.md` §130.
