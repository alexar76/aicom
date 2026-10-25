# Bincode replacement — 2026-10-25

The final RUSTSEC-2025-0141 dependency is removed from both Solana workspaces.
All changes, tests and Git commits are local; no GitHub write, publication,
production deployment or real-chain payment was performed.

## Implementation

- `security/solana-wire` provides four required legacy Serde functions using
  maintained **bincode-next =2.1.0**, std+serde only, with default features disabled.
  Its archive and sole added runtime dependency (`unty-next 0.1.2`) are pinned
  by checksum in the adapter and both program lockfiles. The 2.1.x branch receives
  security updates under the upstream support policy.
- Four minimal local patches replace the dependency and call qualifiers in
  anchor-lang 1.2.1, solana-instruction 4.0.0, solana-sysvar 3.1.1 and, for ACEX,
  solana-zk-sdk 4.0.0. Package versions and public API/feature names stay upstream.
  The old codec is neither vendored nor aliased. There is no audit ignore or new
  lint suppression. Upstream deprecated sysvar macros remain visible as compiler
  warnings when building these path dependencies.
- `security/vendor-rust/UPSTREAM.json` records published archive hashes, Git
  revisions and every changed file. `vendor_upstream.py --check` verifies all
  120 upstream files, allowing only 18 files with dependency/call changes.
  Source notices and Apache-2.0 terms are retained. Published development locks
  and original workspace manifests are omitted from these dependency copies.
- The adapter preserves fixed-width little-endian values, Option/enum tags,
  borrowed reads, account padding, loader ELF tails, direct short-write errors
  and checked size counting. Its 16 MiB decode envelope exceeds Solana's 10 MiB
  account maximum and the 2.2 MiB ZK table. Only typed SDK schemas are supported;
  arbitrary recursive or zero-sized Serde containers need structural limits.
  Program IDs, PDA seeds, discriminators and stored account layouts are unchanged.
- Newer bincode-next 3.1.1 was rejected after differential tests exposed partial
  sequence acceptance on unexpected EOF and lost buffered writer errors. The
  selected supported 2.1 branch propagates those errors and passes negative tests.

## Validation after replacement

| Area | Result |
| --- | --- |
| Adapter | 5 unit tests; 9 independent differential tests against the prior codec |
| Lottery | 23 Rust tests; 67 frozen public SDK vectors and full SlotHistory fingerprint |
| Client signatures and amounts | 5 JS tests plus TypeScript typecheck; legacy/v0 messages and Ed25519 signatures |
| ACEX | 8 Rust tests, including 45 ABI cases and native payment authorization/transfer scenarios |
| ZK compatibility | 7 frozen key/ciphertext encodings; all 65,536 lookup entries; decrypt 0/77/65536/u32::MAX; old proofs verify; tampered proofs fail |
| IDL and release binaries | Both programs pass; unchanged Agave 4.1.2 / platform-tools 1.54, Rust 1.89 |
| Real lottery execution | Compiled SBF runs full purchases, funding, draw, prize/residual payments, replay rejection, refunds, rent recovery and vault closure on isolated loopback validator |
| Rust SDK | 51 tests including fixed payment/signature vectors and recovery |
| Dependency graph | All three locks contain zero packages named bincode; selected local patches, codec version and checksums checked |

ACEX payment tests use the actual Anchor entrypoint with official host syscall
stubs and an emulated token ledger; its SBF binary is built. The lottery payment
flow additionally executes on a real local validator. Test wallets and proof
fixtures are disposable. The validator was stopped after completion.

The frozen fixtures were captured before replacing the codec. Old bincode was
used only by an isolated temporary baseline/differential harness and is absent
from committed dependency manifests and regression-test dependencies. Local raw
logs, fixture provenance, binary hashes and independent reviews are recorded in
`artifacts/security-bincode-2026-10-25/`.

## Known-advisory audit

Offline OSV matching inventories 296 manifests and 3,751 distinct pinned registry
versions across five ecosystems, including all three final Cargo locks. No Rust
advisory matches and no known advisory classes remain in owned, nonignored source
manifests: all 19 classes from the previous residual set are closed.
Both existing shared JS vendor build/runtime locks retain their separately
checked zero-match result; they are unchanged by this Rust-only replacement.

Raw results retain 153 npm advisory classes in ignored, untracked upstream
OpenZeppelin development tooling and the alien-monitor frontend snapshot. These
were outside the owned-source migration and have not been silently removed from
audit evidence. The malformed upstream PYSEC-2024-311 record for wasmtime 49.0.0
retains its explicit manual disposition: all listed affected upper bounds end
below version 49. There are zero manifest parse errors.

This is a source dependency and local runtime result. Unpinned requirements,
deployed versions, OS/toolchain packages and undiscovered flaws are outside that
known-advisory count. Reproduction and future CI checks are described in
`security/solana-wire/README.md`; CI runs provenance checks, the graph guard,
adapter regressions and both existing Solana suites when these sources change.
