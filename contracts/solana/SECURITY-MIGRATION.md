# Local Solana security migration (2026-10-25)

The lottery program uses Anchor **1.2.1**, its default split Solana 3 crate
interfaces, and Borsh 1.x. The reproducible host toolchain is Rust 1.96; the
SBF build was verified with Agave 4.1.2 / platform-tools v1.54 (Rust 1.89).
`Anchor.toml` pins the matching stable Anchor/Agave tools.

Program ID, PDA seeds/bumps, all 13 application instruction discriminators and
argument encodings, and the serialized LotteryConfig/Round/Ticket layouts remain
unchanged. Golden tests were first run against Anchor 0.30.1, then against 1.2.1.
Allocation sizes remain 144 / 192 / 88 bytes, including the discriminator.

## Client requirements

`close_vault` now performs the required signed System Program transfer. Its old
implementation directly debited a System-owned PDA and was rejected by the real
runtime. Keep its four existing accounts and append the executable System Program
(`11111111111111111111111111111111`) as the first remaining account:

```typescript
program.methods.closeVault().accounts({ authority, config, round, vault })
  .remainingAccounts([{ pubkey: SystemProgram.programId, isSigner: false, isWritable: false }]);
```

The instruction bytes, fixed account order, signer requirement, and PDA remain
the same. Missing or forged remaining program accounts are rejected. Prize,
residual, and cancelled-round refund accounting is unchanged.

The legacy JavaScript client remains on web3.js 1.99.0 for synchronous PublicKey
and Keypair API compatibility. Anchor's supported package is `@anchor-lang/core`
1.2.1. Jayson 5, TOML 5.0.1 and fixed serializer/diff dependencies replace their
vulnerable transitive versions. The native, unmaintained `bigint-buffer` dependency
is replaced by a clearly named local package, `@alexar76/bigint-buffer-safe`,
through an npm override. It implements only the four unsigned conversion APIs
used by SPL layouts, rejects negative/overflowing values, and bounds widths to
4096 bytes. It contains no native code. Independent byte vectors and real
SPL u64/u128/u256 layout tests verify its encoding. `npm audit` reports zero.

## Verification

```sh
cargo test --locked
cargo check --locked --features idl-build
npm ci --ignore-scripts
npm run typecheck
npm run test:client
```

The Rust tests execute real Anchor entrypoint dispatch, signer/owner/PDA checks,
and a strict System Program transfer stub. They cover funding, prize/residual
payouts, treasury checks, replay rejection, the pinned draw hash and commitment,
unauthorized oracle rejection, cancelled funding reclaim, and reserve closure.
The JavaScript tests compare both legacy and v0 transaction signatures against
independent Node Ed25519 signatures and fixed message bytes, plus Anchor/PDA and
SPL amount vectors.

For real SBF execution, start an isolated validator with the built program
preloaded at its declared ID, then run:

```sh
LOTTERY_LOCAL_RPC=http://127.0.0.1:18999 npm run test:localnet
```

The script rejects non-loopback URLs. It generates ephemeral wallets in memory
and uses only local validator SOL. It verifies initialize/open/buy/fund,
pinned-slot draw, failed oracle/reveal checks, exact prize/residual payments,
replay rejection, vault reserve return, cancellation, permissionless ticket
refund including account rent, funding reclaim, and final vault closure.

The old `tests/aimarket_escrow.ts` suite is retained and type-checked with the new
client. Its escrow source has no Cargo manifest in this workspace, so it is not
presented as an executed integration suite.

## Legacy Serde codec replacement

The migration removes the legacy Borsh 0.9/0.10, curve25519-dalek 3, rand 0.7,
memmap2 0.5, im, sized-chunks, bitmaps, derivative, libsecp256k1, and paste graph.
The remaining bincode 1.3.3 dependency (RUSTSEC-2025-0141) is now removed.
Three minimal, checksum-verifiable local patches of Anchor, solana-instruction
and solana-sysvar use `aimarket-legacy-wire` over maintained bincode-next 2.1.0.
The original package names, public feature labels and instruction APIs remain.
This replaces the actual codec implementation; no advisory ignore or warning
suppression is used. Sources and provenance are under `security/vendor-rust`.

An additional 67 frozen pre-replacement instruction/sysvar/loader vectors and
the full 131097-byte SlotHistory fingerprint pass. Seven new tests check public
SDK APIs, malformed and truncated data, padded accounts, and short writes.
After replacement, 23 native Rust tests, all five JS signature/amount tests, IDL,
the original SBF toolchain and the complete real local-validator payment lifecycle
pass. See `security/migrations/2026-10-25-bincode-replacement.md` for scope.

Official migration references:
- https://www.anchor-lang.com/docs/updates/release-notes/1-0-0
- https://www.anchor-lang.com/docs/updates/release-notes/1-2-0
- https://www.anchor-lang.com/docs/updates/release-notes/1-2-1
- https://rustsec.org/advisories/RUSTSEC-2025-0141.html


Code authorization hardening (2026-10-25): initialization now appends a read-only
`program_data` account. It must be the canonical PDA derived from this program ID
under `BPFLoaderUpgradeab1e11111111111111111111111`, owned by that loader, contain
`ProgramData`, and name the initializer signer as its current upgrade authority.
Initialize before making a program immutable. This prevents a stranger from
front-running deployment and choosing the singleton admin/authority and treasury.
Existing config/state layouts and instruction argument bytes are unchanged; fresh
initialization clients must append the loader ProgramData account. The local
validator test uses `--upgradeable-program` and a published throwaway authority
seed, confined to loopback. No on-chain deployment was performed.
