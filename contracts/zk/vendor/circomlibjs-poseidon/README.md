# Original circomlibjs Poseidon WASM

This private, source-visible package exposes only `buildPoseidon` and
`buildPoseidonWasm` from circomlibjs 0.1.7 (Jordi Baylina / iden3, GPL-3.0).
The two files in `src/` are byte-for-byte upstream npm sources, including all
constants. `UPSTREAM.json` records their SHA-256 hashes and the original npm
tarball integrity. The GPL text is in `COPYING`.

The upstream package's EVM bytecode generators require ethers 5 and the
unpatched elliptic 6 dependency. Neither generator nor ECDSA signing is used
by our witness helper. Keeping only the existing WASM implementation removes
that code and its dependencies without replacing the hash algorithm with a
different implementation. The only runtime dependency is ffjavascript 0.3.1,
also used by snarkjs 0.7.6.

This is the original Poseidon hash with two inputs over BN254, **not** the
different Poseidon2 permutation. Circuit constants, proving and verification
keys are unchanged. `npm test` checks 72 frozen outputs captured from the
previous circomlibjs package, field boundaries, CLI behavior and source hashes.
The hub's `test_zk_schema_binding.py` additionally proves and verifies against
the existing compiled circuit when its build artifacts are available.
