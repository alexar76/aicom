# `awr` — an independent AWR/2 implementation in Rust

Written from `awr/SPEC.md` (AWR 2.0.0) alone, as a second implementation for
interoperability testing. No other implementation, vector set or schema was
consulted while writing it.

## Build and test

Offline only; the dependency set is `ed25519-dalek 2.2` and `sha2 0.10`.

```sh
cargo build --offline
cargo test --offline
```

JSON parsing, canonicalization, base58btc, multibase, base64, hex, RFC 3339 and
decimal comparison are all hand-written in this crate. A generic JSON library
cannot express the three properties AWR needs at once (duplicate-key rejection
§4.1(5), the lexical integer/non-integer distinction §4.3, and order- and
unknown-member preservation §3.1/§4.2), so `src/json.rs` provides them directly.

## CLI (SPEC §17)

```
awr verify <file> [--profile L0|L1|L2] [--parents <file>...] [--now <rfc3339>]
                  [--subject <id>] [--skew <seconds>] [--max-depth <n>] [--max-nodes <n>]
awr canonicalize <file>
awr digest <file>
awr hashdata <file>
awr issue <subject-file> --key <file> [--type <type>] [--id <uri>] [--now <rfc3339>]
                  [--issuer-name <name>] [--jwk] [--pretty]
awr keygen [--out <file>]
```

Exit codes: `0` valid / succeeded, `1` invalid document (a result was produced),
`2` usage or I/O error, `3` unimplemented subcommand. Only the specified payload
goes to stdout; diagnostics go to stderr. `canonicalize` emits no trailing
newline.

Beyond §17 this binary adds `keygen` (a key has to come from somewhere),
`--subject` (§9 requires the subject of a bundle to be identifiable by "explicit
caller argument"), `--skew`, `--max-depth` and `--max-nodes` (§8.2 requires both
limits to be configurable).

`verify` accepts a single document or a bundle (§9) as `<file>`, and each
`--parents` argument may itself be a document or a bundle. Auxiliary documents
are verified individually; their outcome is reported under `documents` in the
result, while `reasons`/`warnings`/`valid` always describe the subject document.

### Round trip

```sh
awr keygen --out key.json
awr issue subject.json --key key.json --issuer-name example-hub > receipt.awr.json
awr verify receipt.awr.json
awr hashdata receipt.awr.json
awr digest receipt.awr.json
```

`issue` prints the canonical bytes it signed, so `awr canonicalize` on the
result is byte-identical to it.

The key file is an RFC 8037 OKP private JWK (§17 does not define the format;
§5.2 already makes RFC 8037 part of AWR). `{"seedHex": …}`,
`{"privateKeyMultibase": "z…"}` and a bare 64-character hex seed are also
accepted.

## Modules

| module | specification section |
|---|---|
| `json` | §4 canonicalization and the strict parser §4.1 requires |
| `encoding` | base58btc/multibase (§5.1, §6.1), base64 (§3.2), hex (§17) |
| `didkey` | §5 issuer identity |
| `sri` | §3.2 digest references |
| `proof` | §6 `eddsa-jcs-2022` |
| `decimal` | §4.3 decimal strings, compared as decimals |
| `timefmt` | §3.1 RFC 3339 UTC |
| `report` | §11.1 result shape, §11.2 registry |
| `document` | §3 envelope and subject checks |
| `chain` | §8 work chains |
| `bundle` | §9 bundles |
| `legacy` | §12 AWR/1 |
| `verify` | §6.3 orchestration, §10 profiles |
| `issue` | issuing (§6.2) |

`report::REGISTRY` holds all 66 reason codes with the severity the
specification assigns them, and `Report::push` takes the severity from that
table, so a code can never be emitted at the wrong severity or invented.
`tests/reason_codes.rs` drives one fixture per code and asserts that the whole
registry is exercised.

## Where the specification left a choice

Every such point is marked `IMPLEMENTATION CHOICE` in the source, with the
section number and the reasoning, so that a divergence found in interoperability
testing can be traced to a decision rather than to an accident. `grep -rn
"IMPLEMENTATION CHOICE" src/` lists them. The largest ones: the lexical reading
of "integer" in §4.3 (`1.0` is rejected), `verify_strict` for §6.2 step 7, the
pipe-delimited legacy rendering of §12, the key-file format for §17, and
reporting profile shortfalls only for a profile the caller requested (§10.4).

**After three-way interoperability testing**, four of those are no longer choices:
`SPEC.md` §4.3 now requires the lexical reading, §12.1 writes out the legacy
rendering (this build's reading, with `null` rendered as `null` and empty
containers contributing no entry — both were wrong here and are fixed), §17 fixes
the interoperable key-file form as a bare 64-character hex seed, and §10.4 states
the profile rule. Three defects in this build were found and fixed in the same
pass: `profile` was reported as `"L0"`/`"L1"` on documents it had itself declared
invalid, `AWR-CHAIN-004` and cross-receipt `AWR-CHAIN-006` were never reported
because resolution refused to walk through a digest-mismatched parent, and
`AWR-PROOF-006` was added on top of `AWR-KEY-*` for a signature that was never
checked. It now passes all 106 vectors.
