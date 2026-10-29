# Local ecosystem code audit — 2026-10-25

This review follows the dependency and wire-compatible Solana/bincode migration.
Changes are local to `main`. No GitHub writes, publication, deployment, real
payments, production databases or live chain transfers were used.

## Scope and evidence

The initial tracked-source inventory contains 7,109 files: 4,783 runtime sources,
1,811 tests/fixtures and 515 reference/vendor/evidence files. Review combined
repository-wide searches with manual trust-boundary/data-flow inspection and
executable adversarial regressions. This is not a line-by-line proof of every
source file or of unknown production configuration.

Detailed local evidence is under `artifacts/code-security-2026-10-25/`. These
reports are excluded from factory export. Secret reports are fully redacted;
their counts include test credentials and false positives.

## Corrected boundaries

- Factory/UNI signing fails closed without Ed25519, validates stored identities
  and creates private identity files atomically with mode 0600. Factory/CHARON
  ML-DSA identities receive equivalent publication and consistency checks.
- Generated code cannot run host pytest, package lifecycle hooks, runtime servers
  or imported property checks by default. Factory JWTs are stripped from sandbox
  proxy requests; production also checks persisted customer JWT secret strength.
- Generated file edits cannot target `.git`, including symlink aliases. Factory
  Git operations import validated legacy metadata once into a private mode-0700
  store outside the product mount, serialize operations across workers and use
  fixed safe configuration/environment. Later product-side config replacement
  cannot change the executed policy. Hooks, filters, helpers, indirect Git
  directories and inherited credentials cannot supply executable policy.
- Hub payment admission refuses malformed/NaN prices. SDKs and Argus do not retry
  ambiguous paid POSTs. Credential-bearing transports refuse unsafe redirects.
  Provider response signatures bind the request, and real ZK public signals must
  equal the signed commitment/nullifier/schema before replay consumption.
- Solana singleton initialization requires the actual upgrade authority through
  canonical loader-owned ProgramData. Valid instruction argument/state bytes are
  preserved; initialization clients append the required account. The legacy
  escrow Ed25519 parser now validates all instruction indexes. ACEX EVM debt
  share rounding no longer permits debt-free tiny borrows.
- Verified Stripe refunds/disputes freeze new Hub spending atomically, including
  historical reversals on one-time migration. Balances and existing reservations
  remain available for operator reconciliation; trusted reactivation is durable.
- eSIM Stripe fulfilment binds the issued checkout session, order and USD payment
  terms. Pre-upgrade orders recover their missing binding only after matching an
  authenticated merchant-side session retrieval; API failure returns 503 so
  Stripe retries. New unissued orders cannot use this compatibility path.
  See [Stripe session retrieval](https://docs.stripe.com/api/checkout/sessions/retrieve)
  and [webhook delivery](https://docs.stripe.com/webhooks).
- AEGIS/CHARON amount allocation is serialized across workers. AEGIS deposits use
  the shared Hub transfer claim authority. Known conflicting payment recipients
  fail closed. Cite desks reserve separate new identifier bands and refuse
  automatic settlement of ambiguous unpaid legacy invoices.
- Attested billing and domain credit updates share a transaction; team ownership,
  paid memory search, publisher identity, LSAG subgroup checks and canonical
  key-image replay protection are enforced.
- Attested actor proof v2 signs the final product, HTTP method/path, ordered query
  pairs and exact body digest. Destination databases consume nonces atomically
  across workers/restarts. First-party browser/Python/Personal/Team/Expert clients
  use the new protocol; a proxy can relay only explicitly signed targets. Legacy
  identity-only proofs are refused on protected routes.
- Metis host code execution is disabled by default and always refused from HTTP
  and WebSocket requests. Distributed signing fails closed without a key. SSRF
  transport pins validated public addresses and removes cross-origin credentials.

Package-specific migration notes are in `docs/sandbox-trust-model.md`,
`aimarket-sdks/SECURITY-MIGRATION.md`, `contracts/solana/SECURITY-MIGRATION.md`,
`attested/docs/SECURITY-CODE-AUDIT-2026-10-25.md`,
`cite-desks/docs/payment-security-2026-10-25.md` and
`metis/docs/SECURITY-2026-10-25.md`.

## Verification

- Factory/core security suites and financial compatibility checks passed,
  including 281 SQLite/PostgreSQL payment, checkout and failure-recovery cases.
  The final separate-worker deposit handover/topup/registry run passed 63 on
  SQLite and 63 on disposable PostgreSQL.
- Argus passed 395 tests with 10 pre-existing skips; eSIM passed all 48 tests,
  including old-session recovery, API outages, wrong-session refusal and replay.
  Provider-key guard and adjacent provider suites passed 17 tests.
- SDK checks passed for TypeScript (75), Rust (54 plus doctest) and Dart (106).
  EVM suites passed for market (148), ACEX (74) and lottery (55). Solana native
  suites, SBF/IDL builds and the real disposable local-validator payment/refund
  lifecycle passed; no public-chain funds or real wallets were used.
- Hub signed Stripe reversals/historical migration passed on SQLite and
  PostgreSQL. The 38-test ZK suite includes real local PLONK proofs and envelope
  replay rejection. Protocol/agent/signer/bridge suites also passed.
- The first satellite suites passed 469 cases. The final Attested client/server,
  actual browser-signature and Personal/Team proxy suites passed 212 cases after
  the proof migration. PostgreSQL nonce contention accepted one of twelve
  attempts and rejected reuse after connection-pool restart.
- Independent review reproduced and retested the legacy Stripe compatibility
  issue and the unequal-amount claim-release race. Those findings were corrected
  before completion. Counts from overlapping suites are not added together.
- Final private Git metadata, import-race, environment and admin-auth regressions
  passed 54 cases; private export exclusions passed 13 cases. All Git fixtures
  use disposable local repositories and no network publication.

Owned temporary PostgreSQL databases/pools were cleaned up and the disposable
cluster was stopped. Existing deprecation warnings were left visible; no warning
filters or vulnerability-report suppression were added.

## Secret review

Gitleaks 8.30.1 scanned 14,511 ordinary tracked text files and all local Git refs/history
(3,840 commits at scan time), without repository ignore rules or inline allow
comments. A supplementary run scanned all nine larger text/evidence files
(109.65 MB); nine large binary media files were not decoded for embedded secrets.
Default rules produced 2,108 ordinary current, 69,700 large-text and 72,316 historical alerts; these are
scanner hits, not counts of confirmed credentials. Public identifiers, signatures,
locale prose, checksums and disposable regression tokens dominate those results.
The supplementary hits comprise 69,698 public benchmark row identifiers, one
public chain contract address and one natural-language label false positive.

A likely historical LLM credential was found in old local versions of
`data/config/model_providers.yaml`, with SHA-256 fingerprint beginning
`ac4a4bc2`. It is absent from the checked current configuration. The user confirmed
that it has already been revoked. Presence in GitHub history was not established.
No plaintext was copied into reports or tests; a fingerprint-only provider and
admin-probe guard prevents accidental restoration. Local Git history was not
rewritten, and no external credential was tested or changed.

## Material operational limits

- Previously host-backed generated-code checks now return
  `generated_code_isolation_required` until supplied by an isolated worker. This
  audit does not implement a complete container adapter for every legacy gate.
  Existing hardened Docker/Compose and built static preview paths remain usable.
- Factory product Git history/index now lives in `data/private_product_git/`;
  preserve this private store in operator backups. Original product `.git` is
  imported once and subsequent product-side changes are ignored. New product
  repositories are managed through the Factory Git API. This store and audit
  evidence are excluded from public factory export and Git tracking.
- Old identities actually exposed by a historical missing-crypto fallback need
  deliberate operator rotation and public-key re-pinning; corrupt legacy files
  are refused rather than silently replaced.
- Independent deployments with undisclosed shared treasury addresses cannot
  obtain global amount-only invoice uniqueness from local databases. Dedicated
  recipients, a shared atomic claim authority or invoice-bound payments are still
  required. Known local overlaps are rejected; no live overlap was established.
- The trusted Solana lottery oracle can still withhold its seed and force refunds.
  Removing abort bias requires a separate VRF/bond/economic design. Funds are
  protected by the tested refund path; oracle unbiasedness is not claimed.
- The excluded legacy escrow program has no standalone Cargo manifest: its exact
  parser is tested through the active workspace, but the full legacy binary was
  not built. Browser E2E requiring an unavailable Playwright installation was not
  run. Fixes have not been deployed to published services.
