# Legacy Solana serialization vectors

`legacy-wire-v1.tsv` was captured from actual bincode 1.3.3 code before replacing
the backend. It includes 67 complete byte vectors, 27 observed error/wrapper
results, and a SHA-256 fingerprint for the 131097-byte SlotHistory vector.

The integration tests exercise the public Solana instruction constructors and
Anchor loader/sysvar decoding. They do not depend on the removed codec.
Instruction argument data, account padding/trailing bytes, error mapping,
fixed integer widths, enum/Option tags, floating-point bits, and large sequence
behavior are covered.

Full baseline provenance and the original SlotHistory bytes are retained in
`artifacts/security-bincode-2026-10-25/lottery-baseline/` at the repository root.
The TSV reference remains unchanged when the maintained backend is upgraded.
