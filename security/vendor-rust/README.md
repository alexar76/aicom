# Minimal Anchor/Solana codec patches

These are local, source-visible patches of the exact published crates listed in
`UPSTREAM.json`. They keep upstream package names/versions so the entire Solana
graph uses the same public types. Both Solana workspaces explicitly select them
with `[patch.crates-io]`. They are maintained here until upstream accepts a
compatible replacement; upstream updates must repeat the regression suite.

The only changes to upstream sources are `bincode::` call sites (including their
examples) to `aimarket_legacy_wire::`. The only manifest changes replace the old
dependency with `aimarket-legacy-wire` and update its optional dependency feature
reference. Existing public `bincode` feature names and `new_with_bincode` methods
remain for API compatibility. No old codec implementation or dependency alias is
included. The shared adapter uses maintained **bincode-next 2.1.0**, not renamed
bincode 1.3.3. See `../solana-wire/README.md` for supported inputs and tests.

Published archive SHA-256 hashes and Git revisions are recorded in `UPSTREAM.json`.
The transformer verifies each entire archive and permits only the changes above.
It retains the source files and embedded ZK lookup table byte for byte. Upstream
development lockfiles, original workspace manifests and Cargo cache markers are
omitted: these crates are dependencies of the two locked application workspaces.

Reproduce in a fresh checkout (public GETs only if not cached), or verify:

```sh
python3 security/solana-wire/vendor_upstream.py --check
python3 security/solana-wire/check_graph.py
# Add --offline to require existing Cargo archive cache.
```

All four packages declare Apache-2.0. Their published archives do not contain
standalone license files; the Apache-2.0 terms are supplied in `LICENSE`. Original
source copyright notices are retained. Upstream repositories are Otter Sec Anchor
(`anchor-lang`), Anza `solana-sdk` (`solana-instruction`, `solana-sysvar`) and
`solana-program/zk-elgamal-proof` (`solana-zk-sdk`); exact revisions and paths are
recorded in each `.cargo_vcs_info.json` and the provenance manifest.
