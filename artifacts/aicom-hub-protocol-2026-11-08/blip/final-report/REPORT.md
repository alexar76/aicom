# Hub/protocol final V4 validation

The requested 45-file Hub selection and 68 protocol cases passed independently on BOTH hosts: 1,091 unique main cases per host, zero failures, errors or skips. The separate 7-case pilot is not added to the main total.

| Check | Blip | Attested |
| --- | ---: | ---: |
| Hub core, 44 files | 1021/1021 | 1021/1021 |
| Actual Anvil, 1 file | 2/2 | 2/2 |
| Protocol main | 64/64 | 64/64 |
| Protocol wire | 4/4 | 4/4 |
| Unique main cases | 1091/1091 | 1091/1091 |
| Separate pilot, included above | 7/7 | 7/7 |

Both hosts ran immutable Git tree 1400f9f8e6f0b104298835b1f9bcfd35f4a75aa3. All 574 relevant source/test/config files matched the root's 10,101-file SHA256 mapping 7085e9f236ccd276b89a3f864421751fb468f9da18b17b05376ffccb40068f16 and remained unchanged before and after testing. The paired audit matches 1,088 raw case IDs/statuses exactly. Three gzip.compress parameter IDs contain import-time MTIME bytes: the checker verifies that every differing decoded byte lies inside the gzip-header MTIME fields, then zeroes those fields only for report pairing. All 1,091 canonical cases/statuses match. Raw vectors remain unchanged. Randomized fixture bytes and host runtimes are not compared.

Tests ran in gVisor/runsc with network none, UID 1000, read-only root and source, all capabilities dropped, no-new-privileges, no published ports and isolated writable fixture/output storage. Blip was capped at 2 CPU / 2 GiB; Attested at 1 CPU / 768 MiB; swap was disabled for both. No production mounts, data or credentials were used.

The Python 3.13.18 image was pinned by immutable ID. Hub dev+escrow dependencies came from uv.lock with required artifact hashes. Provenance 2.3.1 was built offline from the exact frozen project, installed with its real plugin entrypoint, and every installed Python file matched source. Both wheels had SHA256 b95afc0e1f594d5f7a3ecbaafe3b64ba47d6ed7111c1be67ff5d547539bc7f73. Foundry 1.9.0, solc 0.8.28 and OpenZeppelin 5.6.1 exercised actual disposable Anvil settlement. Protocol HTTP/TLS tests used disposable loopback fixtures only.

The new inbound-crawler regression tests both header spellings with opposite rejection policies in the actual versus environment/config database. Both directions of the policy difference are asserted. A separate omission negative control recorded two EXPECTED failures on the same target/test source bytes. The supply-chain fixture correction uses a mocked public provider so admission-before-catalog assertions remain meaningful; the private-provider production guard was unchanged.

Earlier v1/v2/v3 diagnostics remain separate and were not overwritten: read-only-cwd setup failure, interrupted non-final v2 tmpfs run, missing basetemp parent setup errors, and V3's missing-provenance/stale-private-provider fixtures. Only final V4 results establish this acceptance.

This is explicit changed-area coverage, not every Hub/aicom test or every supported Python version. The historical 379-selection argv was not preserved; the current 45-file argv and per-case results are recorded directly. Synthetic pytest databases and generated signing keys are excluded from evidence exports.
