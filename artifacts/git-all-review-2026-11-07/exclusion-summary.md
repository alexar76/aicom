# Exact private-data exclusions

The following 61 existing originals remain local. Exact anchored `.gitignore` entries exclude them from Git and from source/report transfer; their adjacent `.receipt.json` files retain only the original path, byte length, SHA256, classification and exclusion reason. These are identity receipts, not redacted copies of the records and not claims that the originals are public files.

| Original path | Classification |
| --- | --- |
| `artifacts/backup-admin-repair-2026-11-07/verification-stderr.private.log` | Owner-private stderr capture; empty when reviewed |
| `artifacts/lottery-migration-2026-11-07/target-live-snapshot.json` | Production runtime, financial and player-related snapshot |
| `artifacts/hub-knocking-log-audit-2026-11-07/factory/execution-metadata.json` | Production execution traces |
| `artifacts/hub-knocking-log-audit-2026-11-07/lab/historical-and-transport.json` | Production HTTP and SSH logs |
| `artifacts/hub-knocking-log-audit-2026-11-07/lab/redacted-log-evidence.json` | Production HTTP and SSH logs with incomplete redaction |
| `artifacts/hub-knocking-log-audit-2026-11-07/factory/log-evidence.json` | Production HTTP and SSH logs |
| `artifacts/hub-knocking-log-audit-2026-11-07/indep/logs-summary.json` | Production request log records |
| `artifacts/hub-knocking-log-audit-2026-11-07/factory/symmartys-capture-evidence.json` | Production request capture |
| `artifacts/hub-knocking-log-audit-2026-11-07/factory/targeted-nginx.json` | Production nginx request logs |
| `artifacts/hub-knocking-log-audit-2026-11-07/indep/internal-app-log-matches.json` | Production application log matches |
| `artifacts/hub-knocking-log-audit-2026-11-07/indep/FINDINGS.json` | Production findings retaining request samples |
| `artifacts/hub-knocking-log-audit-2026-11-07/attested/internal-app-log-matches.json` | Production application log matches |
| `artifacts/hub-knocking-log-audit-2026-11-07/attested/FINDINGS.json` | Production findings retaining request samples |
| `artifacts/hub-knocking-log-audit-2026-11-07/attested/logs-summary.json` | Production request log records |
| `artifacts/hub-security-recheck-2026-11-07/live/competing-lab.json` | Production report retaining request samples |
| `artifacts/hub-security-recheck-2026-11-07/live/factory-vps.json` | Production report retaining request samples |
| `artifacts/hub-security-recheck-2026-11-07/live/attested.json` | Production report retaining request samples |
| `artifacts/hub-security-recheck-2026-11-07/live/indep.json` | Production report retaining request samples |
| `artifacts/hub-security-recheck-2026-11-07/live/BASELINE-SUMMARY.json` | Production baseline retaining request samples |
| `artifacts/hub-security-recheck-2026-11-07/live-after/competing-lab.json` | Production verification retaining request samples |
| `artifacts/hub-security-recheck-2026-11-07/live-after/factory-vps.json` | Production verification retaining request samples |
| `artifacts/hub-security-recheck-2026-11-07/live-after/attested.json` | Production verification retaining request samples |
| `artifacts/hub-security-recheck-2026-11-07/live-after/indep.json` | Production verification retaining request samples |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/attested-inventory.json` | Production database capability inventory |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/competing-lab-inventory.json` | Production database capability inventory |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/factory-vps-inventory.json` | Production database capability inventory |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/indep-inventory.json` | Production database capability inventory |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/attested-logs-proxy.json` | Production log and reverse-proxy capture |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/competing-lab-logs-proxy.json` | Production log and reverse-proxy capture |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/factory-vps-logs-proxy.json` | Production log and reverse-proxy capture |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/indep-logs-proxy.json` | Production log and reverse-proxy capture |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/cleanup-bootstrap-plan.json` | Cleanup plan embedding production catalogue rows |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/attested-cleanup-preview.json` | Production database cleanup preview |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/competing-lab-cleanup-preview.json` | Production database cleanup preview |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/factory-vps-cleanup-preview.json` | Production database cleanup preview |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/indep-cleanup-preview.json` | Production database cleanup preview |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/synthetic-local-candidates.json` | Actual catalogue row subset selected for cleanup |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/synthetic-local-provenance.json` | Catalogue provenance and historical log samples |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/factory-vps-log-details.json` | Production application log records |
| `artifacts/hub-public-endpoints-audit-2026-11-08/live/competing-lab-log-details.json` | Production application log records |
| `artifacts/backup-admin-repair-2026-11-07/final-compact-admin.json` | Unverified key fingerprint report; producer unavailable |
| `artifacts/backup-admin-repair-2026-11-07/quota-admin40.json` | Unverified key fingerprint report; producer unavailable |
| `artifacts/hub-paid-live-2026-11-08/attested/paid-routing-rows.json` | Production paid capability routing rows |
| `artifacts/hub-paid-live-2026-11-08/attested/account-availability.json` | Private production account availability metadata |
| `artifacts/hub-real-payments-2026-11-08/buyer-funding-preflight.json` | Private production buyer funding snapshot |
| `artifacts/hub-real-payments-2026-11-08/factory-preflight.json` | Private production payment preflight snapshot |
| `artifacts/hub-real-payments-2026-11-08/factory-cycle.json` | Private production payment cycle record |
| `artifacts/hub-real-payments-2026-11-08/independent-preflight.json` | Private production payment preflight snapshot |
| `artifacts/hub-real-payments-2026-11-08/attested-preflight.json` | Private production payment preflight snapshot |
| `artifacts/hub-real-payments-2026-11-08/factory-chain-rescue.json` | Private production payment transaction and RPC receipt capture |
| `artifacts/hub-real-payments-2026-11-08/diagnosis/weather-provider-findings.json` | Production payment-linked diagnostic report |
| `artifacts/hub-real-payments-2026-11-08/review/factory-provider-recovery-plan.json` | Recovery plan embedding an actual production payment record |
| `artifacts/hub-real-payments-2026-11-08/independent-cycle.json` | Private production payment cycle record |
| `artifacts/hub-real-payments-2026-11-08/attested-cycle.json` | Private production payment cycle record |
| `artifacts/hub-real-payments-2026-11-08/independent-paid-ledger-proof.json` | Private production payment ledger verification record |
| `artifacts/hub-real-payments-2026-11-08/attested-paid-ledger-proof.json` | Private production payment ledger verification record |
| `artifacts/hub-real-payments-2026-11-08/factory-refund-preflight.json` | Private production refund preflight snapshot |
| `artifacts/hub-real-payments-2026-11-08/factory-refund.json` | Private production refund transaction record |
| `artifacts/hub-real-payments-2026-11-08/paid-ledger-selectors.json` | Private production paid-operation record selectors |
| `artifacts/hub-real-payments-2026-11-08/review/refund-plan.json` | Refund plan embedding actual production payment context |
| `artifacts/hub-real-payments-2026-11-08/FINAL-REPORT.json` | Private production payment and refund financial summary |

The name `redacted-log-evidence.json` did not establish complete redaction: format checks still found client-addressed HTTP and SSH records, so that original is withheld too. Public server URLs and synthetic security fixtures were not excluded merely for containing addresses or attack vocabulary.

The endpoint-audit settings helper emits selected policy flags, host categories and public policy fields rather than credential values; those helper sources and bounded settings reports are not excluded on that basis. Its inventory helper also reads individual capability rows from the production database, while its logs helper retains runtime samples and proxy topology. The eight resulting raw inventory/log captures listed above are withheld independently of whether credential strings were redacted. Source hashes, route/schema descriptions, aggregate operation counts and synthetic callback/invoke test receipts remain eligible for their separate secret review.

The cleanup previews read individual catalogue records from production databases. The assembled cleanup plan copies those records into its review lists, and the synthetic-local candidate/provenance files retain actual runtime catalogue or historical log captures. Their labels do not make them standalone test fixtures. These seven originals are withheld too. Deliberate rejection-policy lists and the separate approval review remain eligible: they express intended security configuration and approval scope rather than publishing the raw database captures. Public keys are not treated as private keys solely because of their names.

The two later log-detail reports also retain individual runtime probe and exception lines from live application containers. Their selected fields and bounded redaction do not turn those original records into standalone synthetic fixtures; both originals remain local.

The complete candidate scan of frozen Git tree `ab46922f863e3f7148d757e9ccf4c72ec60202bb` reported 92 generic API-key findings. Context review accounted for 88 as case identifiers, source hashes, archive paths, public verification identities, pagination cursors or descriptive source strings. Four remaining findings occur in the two backup reports' explicitly named repository key fingerprint fields. Each value has a 64-hex form, but retained producer code does not establish its derivation. The originals are withheld as unverified, without claiming that they contain actual credentials. Their `.redacted.json` companions replace only the four JSON `key` values with `null` and retain all other metadata; their content-free receipts identify the unchanged local originals. No credential-validation request was made.

Existing manifests or reports can continue to identify these local originals by path and hash as provenance. Such references do not include the original bytes in the public candidate. Reuse the adjacent content-free receipts when checking identity, and obtain separately authorized access to originals if their contents are required.

The later paid-routing capture retains individual production catalogue rows with payout and pricing fields. The account-availability capture has an empty per-account candidate list, but retains private database-derived account/funding availability and operational credential-presence metadata. Neither its label nor this exclusion asserts that actual credential values or individual balance rows are present. Both originals remain local; public endpoint payment terms and the source helpers remain eligible for their separate secret review.

The separate buyer-funding preflight associates a wallet with live asset balances, pending nonce and signer-availability context, so that financial snapshot is withheld too. Sanitized quote-only public offers do not retain their payment-secret or nonce values and are not excluded merely for advertising prices or public payout addresses.

A separate, narrowly anchored future-output guard excludes only `artifacts/hub-functional-recheck-2026-11-08/payments/real-paid-plan/*-operator-presence.json`. The reviewed helper can emit private operator/credential availability and designated-canary account balances there. This guard does not exclude helper source or public offers, and anticipated files are not counted among the existing withheld originals until they exist and receive content-free identity receipts.

Six further exact future-output guards cover only `factory-preflight.json`, `factory-cycle.json`, `independent-preflight.json`, `independent-cycle.json`, `attested-preflight.json` and `attested-cycle.json` directly under `artifacts/hub-real-payments-2026-11-08/`. The payment executor can write live balance, pending nonce, transaction and receipt records to these summaries. Anticipated outputs do not increase the existing-original count; their helper and offline guard-test sources remain eligible for separate review. The executor's private protocol journals are already under the ignored `data/secrets/hub-real-payments-2026-11-08/` directory.

Four of those payment-executor outputs now exist and have stable reviewed byte/hash identities: the factory preflight and cycle, independent preflight, and Attested preflight. They are included in the table above and receive content-free identity receipts. Three further exact future guards cover only `factory-ledger.json`, `independent-ledger.json` and `attested-ledger.json` directly under the same artifact directory, anticipating private ledger verification captures. Future files are counted only after they exist and their identities are reviewed; no payment or production ledger query was executed by this review.

The later factory chain-rescue capture retains a complete actual transaction, raw RPC receipt/event records and associated financial context. It is separately withheld. The source collector, public RPC request selectors, sanitized public offer/health plan and source/review hash metadata are distinct from this raw financial response capture and remain eligible for their separate source and secret review.

Two later mixed reports also retain actual financial records: the weather-provider findings identify a paid operation and transaction, and the provider-recovery plan embeds an existing failed payment's amount, transaction identifier and status. Their policy or diagnosis labels do not erase those actual records, so both originals are withheld with content-free receipts. The separate error-code capture uses a retained producer's fixed exception/code allowlist and source-frame/status metadata without raw log messages or environment values; that aggregate technical evidence and its source helper remain eligible for separate review.

The later Independent/Attested payment cycles, their production ledger proofs, the actual-operation selector file and the factory refund preflight/result/linked plan retain live financial records or their explicit associations. These eight originals are also withheld, rather than treating their test, proof, selector or plan labels as anonymization. The refund and read-only ledger helper/test sources remain separate eligible code; their offline verification uses synthetic fixtures only and performs no real payment, refund, production-wallet access or production query.

The consolidated final payment report also retains actual transaction and operation identifiers, paid/refunded amounts, network fees and buyer account balances. It is withheld with an identity receipt. The separate artifact hash manifest remains eligible as path/hash provenance; references to withheld originals do not publish the originals or establish that they are public files.

This review used native read-only file, hashing and pattern tools and ordinary source edits. No local project interpreter, build, test, server or credential-validation request was run. A strict raw-log-format scan of Markdown paths selected in the initial source-transfer manifest found no matching SSH-event or dated nginx-client records; that limited check does not replace the separate remote secret scan.
