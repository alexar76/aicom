# Independent review of the783 native Gitleaks findings

All783 findings from the exact1761-file changed-source candidate were reviewed in gVisor. No unresolved finding or secret credential remains in these detections. Native Gitleaks exit1 and both redacted reports are retained; triage does not rewrite scanner results or add broad ignores.

Every row in per-finding-proof.json records its source file and location, JSON field or source construct, value form, producer context and independent witness. The new683 file-hash detections were recomputed against retained file bytes; four GPG fingerprints match the official Python image; eight issuer identifiers decode to Ed25519 public keys. Both Discord-rule detections are the SHA-256 entry for theoros/docs/DISCORD.md. The prior88 findings were independently rechecked semantically and are bound to14 unchanged native Git blobs relative to ab469.

Category counts:

- archive-path-name: 3
- artifact-file-sha256: 9
- container-name-list: 1
- descriptive-postcondition-strings: 1
- documented-public-did-key: 1
- public-benchmark-case-identifier: 46
- public-ed25519-did-key: 8
- public-indexnow-verification-key: 1
- public-pagination-cursor: 3
- public-python-image-gpg-fingerprint: 4
- public-well-known-verification-key: 2
- runtime-provenance-source-sha256: 16
- runtime-source-file-sha256: 6
- source-sha256-manifest: 490
- tested-source-sha256: 168
- warden-source-immutability-sha256: 24

All1761 input file hashes remained unchanged. Containers used UID1000, runsc, no network, a read-only root and source mounts, dropped capabilities, and no published ports. No project code ran locally, and raw match/secret values were not exported.
