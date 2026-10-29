# Native operator deployment evidence

This directory records the authorized WARDEN metadata correction inside the
existing HISTOR deployment. The native signed build, component-test, full quality,
MOMUS candidate verdict, deployment and rollback guards remain enabled. This is
an honest operator release, not a claimed autonomous detector repair.

## Verified deployment

The native signed executor deployed image
`sha256:1221f1bcc8af9081c923b9064301674d5bc4d8d0ce701cca1075a5b1355b3017`
from source `4afe0243856d02b6b543b9b9559f2a286fab1a90`, with final verification at
2026-10-27 20:27:22 Moscow time (17:27:22 UTC). WARDEN metadata reports 0.22.2;
its package JSON hash is `0411601d6ec47d8d14f608a6643a94589e094940dcd93dde36bdcda52a57a34b`
and all 63 JavaScript files match the published 0.22.2 build digest.

The final recipe explicitly normalizes package metadata to mode 0644 and checks
readability/identity using the inherited service user during image construction.
Independent candidate acceptance verified UID 65532, scanner metadata and MCP
initialization/version/nine tools without making a tool call. The native full
component suite and signed full MOMUS candidate run `20261027T165628` passed.
The operator also compared 92 application/scanner/landing files outside WARDEN
against the previously running image; all matched. HISTOR application version
0.4.2, its PostgreSQL data and deployment profile were preserved.

`final-build/` contains the final candidate evidence. `final-deployment/` contains
the actual MOMUS retest/verdict and conductor order projections, native deployment
result, rollback journal projection, live metadata, health and signed public live
receipt. Rollback is available to the recorded previous image
`sha256:170a2523716bed3101b1a6420cab17eced83a0096053ba4b90e5ed75d51bddc1`.
The trusted remediation base advanced only after successful native promotion and
post-deployment verification. No rollback was needed.

## Existing crawl continuation

An initial pre-promotion attempt stopped at the operator's custom idle guard while
a legitimate crawl was active; it made no production change. Its prepared
verdict/order/health projections are preserved separately in `idle-guard-attempt/`.
The user-authorized deployment then used a reviewed helper revision that retains
all native gates and verifies the normal scheduler's continuation of that cycle.

Run 27185 automatically resumed run 27097 within the same cycle beginning
2026-10-27 16:56:37 UTC. No fallback administrative API request was needed. The
classifier budget stayed zero and package budget stayed 8,000; committed attempts
and classified count were zero in both bounded snapshots while planning was in
progress. The actual production scheduler/crawler source and critical Store resume
methods matched the reviewed source hashes in `crawl-resume-source-proof.json`.
The snapshot reads Store methods using read-only database connections; it does not
construct Services, apply migrations or edit run statistics/plans.

The previous run is correctly recorded as interrupted. Consequently the historical
`last_crawl_error` marker can remain present during the continuation; the current
resumed run has no error. History was not cleared to make the health response look
cleaner. Progress checkpoints have 30-second granularity, and unsaved registry
version planning may repeat after restart. No stronger refund or exactly-once
provider-call guarantee is claimed. The current classifier budget is zero.

The immutable original helper is `run-native-release.py`; the deployed
resume-aware helper is `run-native-release-resume.py`, SHA256
`15fddc27fda0223005fb8a4519503084385396f8276dd3ab5bc247c70e2635a3`.
`resume-contract-validation.json` records three offline completion-race checks;
none issued API calls or native operations. Helpers must use Python 3.11+ with
`-I`; the enrolled native interpreter is Python 3.12.3.

`preflight.json` records the starting image and safe configuration projections.
`lock-journal-preflight.json` contains only lock occupancy and image/order metadata.
No credentials, full configuration dumps, private corpus, provider responses or
raw native command logs are retained here.

## Initial attempts

The first process launch failed before `main`: the staged filename `operator.py`
shadowed Python's standard-library `operator` module. The host interpreter was
Python 3.12.3; upgrading it was unnecessary. A standard-library import failed in
ordinary mode and passed with `-I`. The unchanged reviewed helper was then run
using isolated mode. See `launcher-preflight.json`.

All commands invoking this archived helper must use the native interpreter with
`-I`; do not run it by bare filename from this directory. The subsequent helper is
named `run-native-release.py` to avoid the standard-library filename collision,
and still uses isolated mode.

The native build from `ce1dd74edc30e7d5775c7583079cc4f9ed5d656f` produced image
`sha256:7ba5aa4fc83b311f2eb47aee7f2ee62e44b3f4b5295021dfba8a4f8859c29211`
but its enforced component suite blocked progress. The exact test-stage
reproduction used image
`sha256:5527cf401e8da1277df27827b177dd5d2361dede086079da03f91a112f5a8dd1`,
with the same network isolation, 1 GiB memory and two-worker limit; only a JSON
reporter/output mount was added. It passed 1,381 of 1,382 tests, with one failed
documentation-link assertion and no unhandled errors. The assertion found 22
references to seven committed growth documents absent from the WARDEN-only test
stage. No quality campaign or deployment was attempted after this failure.

The safe records are in `first-native-attempt/`. The component assertion, resource
limits and native gates were not weakened to address the missing test inputs.

## Evaluated candidate rejected by runtime acceptance

The corrected test context at source
`231c6b0618670b408c460ce63fe8d5b1af287563` passed the enforced component suite and
full MOMUS candidate evaluation. Image
`sha256:04c6683cbf8d36201359baf9322aee49c580b6f00b63ab5f59598881bc232639`
was recorded by the native build journal and signed candidate run
`20261027T163801`. Its public receipt is retained in `completed-build/`.

The subsequent default-user metadata check failed before deployment. Independent
inspection found the correct package bytes/version 0.22.2, but `package.json` was
root-owned mode 0600 and unreadable by the image's service UID 65532. All 63
compiled JavaScript files were readable mode 0644 and matched the released build;
the HISTOR application fingerprint also matched the running image. The operator's
restrictive process umask had propagated to the source checkout, while `COPY`
preserved that source file mode. This candidate was not promoted. The recipe must
set a readable metadata file mode explicitly; passing the JS quality measurement
alone is not a runtime metadata acceptance check.

Order and verdict files ending in `projection` intentionally omit signed payloads
and signature values. They are safe audit summaries, not reconstructed signed
objects. Independent public signed MOMUS receipts provide locally verifiable
cryptographic evidence; native execution itself verifies the real signed chain.
