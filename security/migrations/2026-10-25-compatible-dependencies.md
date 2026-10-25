# Compatible dependency migration — 2026-10-25

All changes are local. No live-chain deployment, real payment, GitHub write,
release, or publication is part of this migration.

## Compatibility and security boundaries

- Both Solana programs use Anchor 1.2.1, default Solana 3 interfaces, Borsh 1.x
  and curve25519-dalek 4.1.3. Program IDs, PDA seeds/bumps, instruction bytes,
  discriminators and stored account layouts match fixtures captured and tested
  before the upgrade. The removed legacy graphs include Borsh 0.9/0.10,
  ed25519-dalek 1, curve25519-dalek 3, rand 0.7, serde_with 2, im,
  sized-chunks, memmap2 0.5, atty and libsecp256k1 0.6.
- ACEX now requires the configured administrator's signature over option quotes
  (premium and settlement index), restricts price observations to that authority,
  binds token mint/owner, validates fee and payout arithmetic, keeps slashed
  collateral reserved, credits only added coverage, rejects a purchase after
  exercise, and persists pause updates. Existing clients must append the admin
  signer for option purchase/exercise and mark admin configuration writable.
  See `acex/contracts/solana/README.md` for exact account requirements.
- Lottery vault closure uses a signed System Program CPI instead of an invalid
  direct debit of a System-owned PDA. Append the executable System Program as
  the first remaining account to `close_vault`. See
  `contracts/solana/SECURITY-MIGRATION.md`.
- ZK retains the original circomlibjs 0.1.7 Poseidon WASM and constants, with
  source hashes, tarball provenance and GPL-3.0 license. Unused EVM generators,
  ethers 5 and unpatched elliptic are removed. Commitments, nullifiers, existing
  circuit keys and proofs are unchanged. Private witness fields now travel over
  bounded stdin, rather than process arguments. Custom Poseidon helper scripts
  must accept `--stdin`; the two-argument operator CLI remains available.
- x402 schema migration uses real Zod 4 record constructors and collection
  bounds. Original payment/signing code remains upstream code. Address-configured
  CDP sellers use a narrow authenticated transport instead of the unused wallet,
  policy and Solana SDK surface. JOSE performs JWT cryptography. Shared sources,
  upstream revisions, licenses, reproducible archive tooling and regression tests
  are under `security/vendor/`.

## Validation

- Frozen Solana ABI/PDA/account fixtures: lottery 13 instruction encodings,
  3 layouts and 4 PDA cases; ACEX 21 instructions, 10 layouts and 14 PDA cases.
- Both programs: native entrypoint authorization and exact transfer scenarios,
  IDL feature compilation, and actual release SBF build with checksum-verified
  Agave 4.1.2 / platform-tools v1.54. Host Rust is 1.96; SBF Rust is 1.89.
- Lottery: real compiled SBF on isolated loopback validator; purchases, funding,
  pinned-slot draw, oracle/reveal rejection, exact prize/residual transfers,
  replay refusal, cancellation refunds, rent recovery and vault closure.
- Rust SDK: 51 tests, including fixed EIP-712/payer signature vectors and recovery.
- Hub: 161 payment/signature/x402/channel regressions; 14 ZK tests with actual
  PLONK proofs and replay/schema/capability binding against existing artifacts.
- Poseidon: 72 frozen pre-migration hashes, source identity, compatible CLI and
  bounded private stdin tests.
- x402/CDP: disposable ES256/Ed25519 JWTs, operation URI binding, real EIP-3009
  signing/recovery and tamper rejection, verify/settle/error behavior, discovery
  declarations and initialization behavior compared with the prior SDK offline.
- Application tests, typechecks/builds, clean installs and package portability
  are recorded with local migration evidence. CI retains ABI, signature, schema
  and SBF lifecycle regression checks.

## Final bincode closure and audit scope

The initial migration closed 18 of 19 residual advisory classes. The follow-up
replacement now also removes bincode 1.3.3 (RUSTSEC-2025-0141) from both Solana
graphs. Minimal local patches of four upstream consumers use maintained
bincode-next 2.1.0 through the tested legacy wire adapter. No ignore, warning
suppression or renamed old implementation is used. The final offline matching
reports zero known advisory classes in owned, nonignored manifests. See
`2026-10-25-bincode-replacement.md` for exact changes, tests and limits.

Known-advisory matching uses local OSV datasets and includes owned source
manifests, lockfiles and the new shared vendor build manifests. Ignored upstream
OpenZeppelin development tooling and the ignored, untracked alien-monitor UI
snapshot retain their separate findings; they are not changed by this migration.
The malformed upstream PYSEC-2024-311 record for wasmtime 49.0.0 retains the
previous explicit manual disposition: all affected boundaries end below 49.
This is a source and local-runtime validation, not verification of deployed
production versions or a guarantee that no undiscovered vulnerabilities exist.
