# esim-rails 0.5.0 for npm: built, checked, published 2026-11-17 20:38:43Z

Built on 2026-11-17 around 20:45Z from a clean export (`git archive`) of main `d5b99cb63`
(`esim-kit/rails` and `esim-kit/config`), Node 22.22.1, npm 10.9.4: `npm ci`, `npm test`, `npm run build`,
`npm pack`. Since npm 0.4.0 (2026-11-03): kept quote prices and fresh offers (asked on DEV 2026-11-17), the sample
catalogue behind `./onboard.sh --try` — see `esim-kit/CHANGELOG.md`, section 0.5.0.

The tarball is not in git (13.5 MB). It is kept at
`aicom/artifacts/npm-release-esim-rails-0.5.0-2026-11-17/aimarket-esim-rails-0.5.0.tgz` in the main checkout; that
folder ignores itself (`.gitignore` = `*`). `SHA256SUMS` here pins it:

```
d367f96cab5ac22f8a51bb0dae935f1f1e389469e5be5cd362405a8956dd4faa  aimarket-esim-rails-0.5.0.tgz
```

npm `shasum` 3142378abbfc20c0080cf80d637041ca445798ab, integrity `sha512-VSHc6OInp+vGjoq8raE7Usr…` (full value in
`npm pack --json`), 15,446 files, 68,523,327 bytes unpacked. As since 0.4.0, the patched `@x402/*` builds are not on
the registry, so npm bundles them with their dependencies.

## Checks run

| Check | Result |
|---|---|
| `npm test` in the clean export | 76 of 76 (`test/quote.test.js` 9, `test/agent-buy.test.js`: the example buyer with its x402 client against a node whose wholesale price moves: refused, re-offered, paid the kept 0.70 not 0.75) |
| `npm run build` (syntax, `esim-rails schemas`) | exit 0 |
| Storefront `esim-kit/store` (imports `../../rails/src`) | 55 of 55, on 4afd47640 |
| `npm install <tarball>` in an empty folder | `@aimarket/esim-rails@0.5.0`, bundled `@x402/express` 2.28.0 and `@aimarket/x402-cdp` 0.1.0 load; a demo node on the sample catalogue quotes 2 FR offers that validate against the schema, each with a `quote_token` that `readQuote` accepts (240 cents); an order with that token answers 403 `demo_mode`; `quoteTtlFromEnv({})` = 600000 |
| `npm publish <tarball> --access public --dry-run` | `+ @aimarket/esim-rails@0.5.0`, tag `latest` |
| Unpacked tarball vs npm `@aimarket/esim-rails@0.4.0`, `diff -rq` | own files: `examples/agent-buy.mjs`, `package.json`, `spec/esim-v1/offer.schema.json`, `src/{check,config,index,node,paywall,server}.js` differ; new `src/quote.js`, `src/sample-supplier.js`. Bundled `node_modules`: no difference |
| Package scan (files outside bundled `node_modules`) | no private-host entry from `scripts/.mirror-forbidden-hosts` (10 entries); no private-key, npm, GitHub or API token pattern; no `.env`, `.pem`, `.key` |
| GitHub mirror export (`audit_satellite_exports.py --satellite esim-kit`, Python 3.12; `mirror_satellites.sh --dry-run esim-kit`) | passed, on dc4f8d98e |

## Production

The reference node at https://modelmarket.dev/providers/esim (factory-vps, demo mode) runs kept prices since
2026-11-17 ~19:17Z and this release's sources since ~20:08Z (`esim-rails:prod-20261117-d5b99cb63`, `package.json`
0.5.0; `rails/deploy.sh` from a clean worktree of `d5b99cb63`). The `esim-rails check` of the installed tarball
against it: "Conforms to esim.*@v1", including "quoted price kept — 10 min" and "a changed quote_token is a 400
before any price". Rollback: container `esim-node-prev` (`esim-rails:prod-20261117-4afd47640`); the image that ran
before 2026-11-17 (`aicom-security:esim-node-os-20261031`, code of 2026-10-15) is kept on the host.

## State on 2026-11-17

- npm `@aimarket/esim-rails` latest is 0.4.0 (2026-11-03).
- GitHub `alexar76/esim-operator-kit` has no tags; the mirror predates kept prices.

Publishing and the mirror are the owner's and colleague's steps: `docs/distribution/colleague-tasks.md` §129.

## Published (checked 2026-11-17 ~21:00Z)

- npm `@aimarket/esim-rails@0.5.0`, published 2026-11-17T20:38:43.336Z (registry time), `dist.shasum`
  3142378abbfc20c0080cf80d637041ca445798ab and `dist.integrity` sha512-VSHc6OInp+… — the tarball above, byte for byte; `latest` = 0.5.0.
- GitHub `alexar76/esim-operator-kit` synced at 20:38Z from a commit before the version bump (kept prices are there,
  `rails/package.json` still says 0.4.0); the re-sync is colleague-tasks §129 step 3.
