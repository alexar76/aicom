# Local x402 security migration

The upstream x402 2.28.0 and CDP 1.57.1 graphs still require Zod 3. The application graph now uses native Zod 4.6.7 metadata throughout; there are no dependency overrides.

* `x402-core/` retains the original Apache-2.0 source from the exact upstream release and rebuilds the schema API and declarations for Zod 4, with bounded payment/capability collections.
* `upstream/` holds integrity-pinned original EVM/extensions release archives. `build.mjs` migrates their Zod dependency metadata and the SIWx schema declarations in both module formats. All original runtime, crypto and source-map bytes are preserved.
* `x402-cdp/` supplies the configured EVM facilitator/server surface needed by the sellers. JWT signing uses JOSE, and tests verify signatures, malformed/wrong keys, payment tampering, URI binding, discovery, initialization, HTTP failure outcomes, and parity with the original CDP SDK when a disposable baseline is supplied.
* Each consumer has its own `vendor/` archives, so standalone Docker contexts work. The SDK dependencies are bundled by `npm pack`, preserving the native Zod 4 graph when installing a package in an empty project.

Rebuild and verify from a clean checkout:

```sh
npm ci --prefix security/vendor/x402-core --ignore-scripts --no-audit --no-fund
node security/vendor/build.mjs --check
npm ci --prefix security/vendor --ignore-scripts --no-audit --no-fund
npm test --prefix security/vendor
```

Run `node security/vendor/build.mjs` after changing the preserved sources/metadata, refresh consumer lockfiles with npm 11.21.1, then run `--check` again. The check verifies source/archive equality and all archive lockfile integrities. The ignored `archives/` directory is always generated before the validation harness is installed. The optional `CDP_BASELINE_PATH` points to the original SDK inside a disposable temporary install; it is never an application dependency.
