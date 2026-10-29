# Public-history secret audit — 2026-10-25

All changes are local to `main`. The initial audit performed no GitHub/PyPI publication, external credential validation, live payment, deployment, key rotation or peer-pin replacement. The subsequent user-authorized replacement of four local identity files is recorded in [local identity recovery](local-identity-rotation-2026-10-25.md). Secret values are absent from this report, source changes and sanitized audit results.

The anonymous audit covered all 61 public `alexar76` repositories, their 6 public direct forks and 2 accessible wikis: 69 Git stores, 938 refs, 30,618 commit visits and 81,475 blob visits (cross-repository duplicates included). All 594 Gitleaks rule/fingerprint groups were reviewed against their source objects. A separate pass inspected every raw blob, including binary key files omitted by ordinary text diffs. Ref names, commit/tag payloads and historical tree-entry names were also checked.

Gitleaks 8.30.1 used its default rules independently of repository ignore/configuration files, ignored `gitleaks:allow` comments, traversed archives to depth 3 and decoded supported encodings to depth 5. A gzip-member positive control was independently verified in memory. There were no failed accessible-store scans and no LFS pointers. Sixteen enabled wikis were anonymously unavailable. Seven historical external gitlink entries refer to four third-party dependency commits; their external histories were outside this audit. Deleted/unadvertised/unreachable history cannot be certified absent.

## Confirmed own disclosures

| Material | SHA-256 fingerprint prefix | Local comparison at audit snapshot |
| --- | --- | --- |
| Oracle Gateway / Platon Ed25519 identity | `df4d28848d05` | Exact runtime-file match |
| Hub Provenance Ed25519 identity | `39f031936ed3` | Exact runtime-file match |
| UNI receipt Ed25519 identity | `7623f3105275` | Exact runtime-file match |
| Sortes VRF secret file | `a3d43ce8789e` | Exact runtime-file match; decoded seed/public identity also checked |
| Lottery Mesh administrator token | `5b023816d239` | No current configuration match found |
| Dataset pseudonymization salt | `8fe500034ccb` | No current salt match found |

These materials remain reachable through public tags; the UNI identity and salt also remain in public fork tags. Removal from the current public branch did not revoke them. Four private identities matched local runtime files at the audit snapshot. The user instructed that unknown revocation status be treated as compromise. Their subsequent local replacement is documented in the recovery report linked above.

Seventeen additional rule/fingerprint groups describe widely public or upstream/test wallet material: Anvil/Hardhat accounts, an RFC8032 vector, Stellar test seeds, inconsistent Solana/Algorand keypair examples and a valid non-Anvil EVM test-log private key. They were not dismissed merely because of their paths. Other results include public browser API configuration and two explicitly uncertain literals: a localhost MCP authentication example and a string quoted in old scanner judgments. They have no current runtime-configuration matches. Provider acceptance, ownership and live balance/status were not tested. A separate raw pass also identified an official AWS example ID, a Slack placeholder and a provider-shaped SAF demonstration input of unknown live status.

## Local corrections

* Known exposed signing/VRF private and public identities are rejected on file/env restoration, signing and verification, including UNI trust pins, cached provenance identities and pure VRF verification. Healthy signature formats remain unchanged.
* Ed25519, ML-DSA, VRF and dataset-salt files use complete atomic private writes and validated reads. Existing malformed identities fail closed. FIFO, leaf-symlink and persistent-hardlink cases are refused before permission changes. Published salt restoration is refused without silently changing stable dataset IDs.
* Provider API keys migrate from inline YAML to private references. Provider files, backups and VAPID material receive mode `0600` before writing. Failover uses stdin for credentials; model probing refuses redirects. Responses, streamed chunks, errors, health state and durable LLM logs redact the configured credential.
* Mirror checks inspect ignored files and the actual staged Git objects, recognize structured/binary/private encodings, and cover all commit paths. Plugin exports exclude runtime data and use canonical secret exclusions. Frozen public proof exceptions require exact contents. Security workflow tokens have read-only repository permission.
* Published Anvil/Hardhat and the non-Anvil EVM sample wallet cannot sign for external production chains. Lottery/Alien validate actual RPC chain identity, fallback endpoints and signed transaction domains. Forge explicitly binds its development chain. Normal private-wallet production use and local development payments remain supported. RPC diagnostics no longer reveal URL credentials.
* Python release archives now receive a bounded content check before upload or dry-run success. A Python filename cannot exempt private material. The one storage-module name exception requires the exact current trusted source. Archives are read without extraction/execution; unsafe links, traversal and hidden directory payloads are refused. This release check inspects outer archive members; nested-container/decode coverage above refers to the history audit.

## Validation and operational recovery

Separate recorded batches include provider storage (161 passing), signing/package compatibility (903 passing), EVM and RPC safety (236 passing), and additional UNI/VRF/salt tests (311 passing), including fresh disposable PostgreSQL. The final root export/echo/credential/release batch passed all 153 tests, including staged object aliases and malicious archive layouts. Some batches overlap; these counts must not be summed as unique tests. Existing deprecation warnings remain visible. All disposable PostgreSQL instances were stopped and removed. An isolated Sortes process also verified compatibility with the older public Oracle Core interface without installed cryptography packages.

The four exposed identity files have subsequently been replaced locally under explicit user authorization. Remote peer pins and deployed identities, if present, still require coordinated recovery on those nodes. Confirm replacement of the historical Mesh token, and never restore the published salt. Changing the salt cannot undo linkage of datasets already published with it. Local changes do not revoke historical copies or update running deployments. No real secret was used against an external service.

Sanitized evidence and per-batch validation are under `artifacts/code-security-2026-10-25/public-secrets/`: `final-public-history-scope.json`, `context-triage-final.json`, `new-raw-material-public-history.json`, `current-public-private-material-summary.json`, and the provider/signing/EVM/runtime-material subdirectories. Original public Git-object caches have been removed after triage; `cache-cleanup.json` records the cleanup.
