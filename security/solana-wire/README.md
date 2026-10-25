# Solana legacy wire compatibility

`aimarket-legacy-wire` is a small internal Serde boundary over the maintained
`bincode-next =2.1.0` codec. The 2.1.x branch receives security updates according
to [upstream's support policy](https://github.com/Apich-Organization/bincode/blob/v3.1.1/SECURITY.md).
The selected crate archive SHA-256 is
`dbe9e7e6d14aeb39557f226bff158a30e367fac279d0e69b8b42fb41999f9a86`
(upstream revision `550ee55f12c3546848501bb52001cf1ee848c8a6`). Default
features and codec derive macros are disabled; only Serde and std are enabled.
The only additional runtime dependency is `unty-next`, pinned in all three locks.
MSRV is 1.85.1; actual Solana SBF compilation uses the existing Rust 1.89 tools.

The adapter preserves bincode 1.x **top-level helper** semantics: little endian,
fixed-width integers, u32 enum tags, u64 container lengths, one-byte Option tags,
and accepted account padding / upgradeable loader ELF tails. It preserves borrowed
decoding and exposes only four functions required by the patched SDK crates.
The direct writer propagates short writes and I/O errors; size counting checks
overflow. No hidden buffer or implicit flush is introduced. SDK public error
mappings are unchanged; codec-internal error types are deliberately internal.

Decoding is limited to 16 MiB, above Solana's 10 MiB maximum account and its
2.2 MiB ZK precomputation table. Malformed lengths fail before native string
allocation. This is for the typed SDK schemas tested here; arbitrary recursive
or zero-sized Serde containers require additional structural limits. Encoding
keeps the upstream SDK's generic Serialize API.

```sh
python3 security/solana-wire/vendor_upstream.py --check
python3 security/solana-wire/check_graph.py
cargo test --locked --manifest-path security/solana-wire/Cargo.toml
cargo test --locked --all-targets --manifest-path contracts/solana/Cargo.toml
cargo test --locked --all-targets --manifest-path acex/contracts/solana/Cargo.toml
```

Regression fixtures were captured against bincode 1.3.3 before replacement.
They cover system/stake/loader instructions, loader states, sysvars including the
entire SlotHistory bit vector, keys, ciphertexts, proofs and the complete ZK
lookup-table fingerprint. Negative cases cover truncated containers, invalid
tags/points/scalars/UTF-8 and short account buffers. Existing program ABI,
authorization, transfer, signature and real SBF payment tests remain enabled.
Old bincode is not needed to execute these frozen fixtures and is absent from
all three lockfiles. There is no advisory ignore or warning suppression.

The newer bincode-next 3.1.1 was rejected during this migration: its Serde
sequence access could turn unexpected EOF into a partial successful result;
its buffered Serde std writer could lose write errors on drop. The selected 2.1
implementation propagates those errors and is tested explicitly for them.
