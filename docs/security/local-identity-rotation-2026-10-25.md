# Local signing identity recovery — 2026-10-25

The user explicitly authorized replacement after the public-history audit. Four exposed identity files were replaced locally with independently generated cryptographic keys. New private material was never printed, committed, uploaded or used against an external service. No GitHub write or remote deployment was performed.

| Identity | Replaced private file | Encoding |
| --- | --- | --- |
| Oracle Gateway / Platon | `plugins/aimarket-oracle-gateway/data/platon_signing_key` | 64-byte Ed25519 seed + public key |
| Hub Provenance legacy identity | `aimarket-hub/plugins/aimarket-provenance/data/hub_signing_key` | 64-byte Ed25519 seed + public key |
| UNI receipts | `data/secrets/uni_receipt_ed25519.key` | 64-byte Ed25519 seed + public key |
| Sortes VRF | `plugins/aimarket-oracle-gateway/data/sortes_vrf_sk` | 32-byte seed encoded as ASCII hex |

Each target was checked against its audited private/public fingerprints and original regular-file inode before replacement. All four replacement identities passed cryptographic checks before cutover. Complete mode-`0600` temporary files were flushed, atomically renamed, and their directories synchronized. There are no new private-key backups. All targets remain ignored and untracked by Git.

Local pin/configuration/cache searches found no references requiring an old-to-new public-key update. The three plugin-directory files are retained legacy identities; current default Platon, Sortes, primary Hub and Provenance configurations use separate healthy identities, which were preserved. UNI reads its primary identity on every sign/verification call and needs no key-cache refresh. No local target service was found running during cutover.

The production UNI signer and payment service were exercised against the actual replacement key and a disposable SQLite database: new receipt verification, tamper refusal, payment retry idempotency, accounting-history preservation, signer-failure rollback and a fresh-process restart all passed. Actual accounting databases and ledger files were compared by digest and remained unchanged. The actual local UNI ledger contained no historical receipts requiring migration. Historical receipts under a compromised identity remain revoked; they were neither rewritten nor re-signed.

Oracle manifest/receipt, Sortes VRF and AWR/2 Provenance checks use the actual replacement files with the production signers/verifiers, entirely offline. Their sanitized results and the per-file replacement fingerprints are under `artifacts/code-security-2026-10-25/public-secrets/rotation/`.

The old public identities remain on the revocation lists. This local recovery does not remove public Git history or replace identities on remote nodes. The previously disclosed Mesh token and dataset salt had no current local configuration match; their restoration remains refused.
