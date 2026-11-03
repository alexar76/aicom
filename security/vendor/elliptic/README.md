# elliptic 6.6.1 nonce-width backport

This private development-tooling package fixes CVE-2025-14505 / GHSA-848j-6mx2-7j84.
It applies Debian's exact `CVE-2025-14505.patch` to the integrity-pinned npm release
of elliptic 6.6.1. The patch preserves the length of the generated RFC 6979 nonce
until truncation, including leading zero bytes. The custom `options.k` API is
preserved. All other runtime files and the upstream MIT license are unchanged.

`6.6.1+aicom.1` identifies a local backport, not a new upstream release. OSV still
matches its base version; the matching advisory is resolved by the source patch
and regression evidence, not suppressed or hidden by a version bump.

OpenZeppelin's ignored tooling checkout uses this archive as a direct development
dependency and `$elliptic` override. Both `@ethersproject/signing-key` and the
`secp256k1` JavaScript fallback resolve this same package. Hardhat, gas reporting,
network helpers and upgrades tooling are retained. No production deployment is
required for this local development dependency.

From the repository root:

```sh
python3 security/vendor/elliptic/build.py --check
python3 artifacts/security-maintenance-2026-10-31/legacy-tooling/apply_repaired_locks.py --apply
# Run npm 11.21.1 in contracts/evm/lib/openzeppelin-contracts:
# npm ci --ignore-scripts --no-audit --no-fund
python3 security/vendor/elliptic/build.py --check-installed
node --test security/vendor/elliptic/regression.test.cjs
```

`build.py` deterministically rebuilds the archive without network access. The
provenance file pins the npm integrity, Debian patch and archive hashes, and the
public Rooterberg fixture revision. `p521-leading-zero.fixture.json` contains a
**public disposable test key**, not an application credential: case 29 from that
fixture reproduces the bug on upstream 6.6.1.

To repeat the full 1560-vector comparison, download the exact file and revision
named in `provenance.json`, then run `node security/vendor/elliptic/check-vectors.cjs
/path/to/ecdsa_rfc6979_secp521r1_sha_512.json`. The runner verifies its SHA-256 and
compares both elliptic and Noble against every expected DER signature.

Sources: [Debian security tracker](https://security-tracker.debian.org/tracker/CVE-2025-14505),
[upstream analysis](https://github.com/indutny/elliptic/issues/321),
[Rooterberg test data](https://github.com/bleichenbacher-daniel/Rooterberg/blob/d446fbab802cb8289de36f715231b638066a0fa8/test_vectors/ecdsa/ecdsa_rfc6979_secp521r1_sha_512.json).
