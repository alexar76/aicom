# Vulnetix source audit — 2026-11-07

The current local source and exact dependency versions have **no affected-version
matches** in the fetched Vulnetix snapshot. A separate confirmed HELIOS withdrawal
bug in the same approval class was fixed locally and regression-tested. No release,
deployment, remote account change or GitHub write was performed.

## Fresh database and coverage

- Public database: [Vulnetix advisory-database](https://github.com/Vulnetix/advisory-database/tree/dfd869723b41544660fd11cecc972974ae10e0af).
- Immutable commit `dfd869723b41544660fd11cecc972974ae10e0af`, committed
  `2026-11-07T06:50:56Z`; read-only retrieval on 2026-11-07.
- Manifest contains 61,078 total records. Downloaded all 2,936 published records
  in PyPI, npm, Go and Cargo malware/weakness/vulnerability families. Classification
  counts: 625 malware, 2,276 weakness, 35 vulnerability.
- Matched 3,543 distinct exact dependency package versions and 170 owned source
  package/version manifests. Twenty-seven advisories concern our owned package
  names. All current owned versions fall outside their affected ranges.
- Result: zero affected-version matches, zero comparison errors. The source
  dependency inventory is matched locally; no source or credentials were uploaded.
- Full read-only snapshot, immutable URLs, SHA-256 hashes, timestamps and record
  completeness checks: `provenance.json`, `manifest.json`, `records/`.
- Reproducible matching: `fetch_snapshot.py`, `match_snapshot.py`, `matches.json`,
  `owned-packages.json`, `owned-advisories.json`.

## Confirmed fix: HELIOS unpublish was undone by auto approval

Before the fix, `unpublish_job` made a YouTube video private, then persisted
`awaiting_approval`. The next auto-approval worker cycle published every job in
that state, undoing the operator's withdrawal. The initial regression run
reproduced two failures, including a stale automatic approval after withdrawal.

The fix records `unpublished`, serializes publication/withdrawal per job across
processes, and refreshes stale automatic approval decisions under that lock.
Explicit `helios approve` restores publication. Local upload-state privacy now
tracks a successful withdrawal, and a failed YouTube update preserves the last
confirmed local state.

For old queue files, the worker reads the audit once per run and recovers
`awaiting_approval` entries whose last publication action was
`youtube.unpublished`. A later approval is preserved. Missing, malformed or
truncated audit history pauses automatic publication of an uncertain backlog;
explicit operator approval remains available. Existing audit data is preserved.

The current `videos.update(part="status")` request omits `publishAt`, which also
cancels a scheduled release under the [documented YouTube update semantics](https://developers.google.com/youtube/v3/docs/videos/update).
No live YouTube action was used for verification.

Modified source: `helios/helios/queue.py`, `helios/helios/worker.py`,
`helios/helios/youtube/upload.py`, `helios/README.md`; regressions in
`helios/tests/test_publication_control.py`.

## Existing advisory regression verification

The targeted suites exercise the actual boundaries mentioned in all 27 owned
advisories: default HTTP authentication, local proxy opt-ins, trusted forwarding
peers, paid-tier identity, DNS pinning and encoded private addresses, owner code
rights, SSH host keys, login lockout keys and sandbox persistence tracing.

| Package family | Result |
| --- | --- |
| HELIOS (full suite, including new migration/failure regressions) | 91 passed |
| aimarket-mcp | 32 passed |
| Metis | 30 passed |
| Hestia | 98 passed |
| Platon | 39 passed |
| Logos | 32 passed |
| Oracle core | 75 passed, 1 skipped |
| SKOPOS | 62 passed |
| Signal Hunt | 12 passed |
| Treasury | 21 passed |
| Atlas | 29 passed |
| HISTOR | 135 passed, 5 skipped |
| Hub | 143 passed |

Exact commands and outputs are in `regressions.json` and `*-tests.log`.
Initial environment failures are retained separately. Hestia required an isolated
test interpreter exposing the local source through site-packages because tenant
processes deliberately strip `PYTHONPATH`; loopback permission was needed for its
temporary local servers. SKOPOS used the existing prepared Streamlit dependencies.
Metis's one public-DNS test passed when DNS access was allowed. HISTOR's five skips
are the PostgreSQL variants without a configured disposable test database; Oracle
core's one skip also requires a disposable PostgreSQL database. Deprecation
warnings were not filtered.

## Limits

This checks known published advisory records and the named source boundaries; it
is not proof that unknown vulnerabilities are absent. Dependency ranges without
resolved pins are not fully represented by exact-version matching. This subtask
does not audit OS images, JVM/Android/iOS components or deployed runtimes, and does
not claim that published wheels or running services received the local fixes.
An audit log cannot prove the absence of historical events deleted as complete
lines; uncertain or damaged retained history is handled conservatively.

The root scanner change adding `requirements*.lock` coverage in both copies and
its tests was reviewed independently against the actual signer/deployer install
inputs; no issue was found.
