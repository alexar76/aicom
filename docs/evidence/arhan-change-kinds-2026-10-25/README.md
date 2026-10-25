# Arhan change-kind study, 25 October 2026

This directory holds a local research result, not a released HISTOR feature or a
public publication. [Russian report](../../growth/arhan-change-breakdown-2026-10-25.ru.md)
and [unsent reply](../../growth/arhan-reply-2026-10-25.en.md).

## Evidence

| File | Purpose |
|---|---|
| protocol.md | Cohort, normalization policy and limitations fixed before execution |
| analyze.py / test_analyze.py | Full-blob classifier and 20 independent counterexample tests |
| cohort_readonly.py / cohort.log | Independent reconstruction of the original cohort and legacy 2,719 count |
| run_remote.py / execution.json | Scoped transfer of four research files and pinned-image Linux execution |
| tests.log / analysis.log | Successful tests and full classification output |
| runtime-unavailable.log | Failed initial runsc attempt before any research code executed |
| summary.json | Primary/overlapping aggregates, examples, snapshot/code/runtime hashes |
| transitions.jsonl | 10,543 base transitions, including cohort2036 membership and per-event flags |
| servers.jsonl | Earliest recorded prechange versus latest postchange for the 2,036 cohort |
| detail_tables.py / detail-tables.json | Strict-only event and whole-history server counts from exported classifications |
| verify_results.py / verification.json | Independent aggregate/chain/hash recount, without importing classifier |
| check_public.py / public-links.json / public-examples/ | Unauthenticated GET verification of five example links against frozen digests/timestamps |
| cleanup_remote.py / cleanup.json | Remote/local output SHA comparison and removal of only this study's temporary directory |
| manifest.json | Original public snapshot manifest, preserved without claiming signature verification |

## Frozen input

The public dataset was already present read-only on admin-vps at
`/var/lib/histor-datasets/2026-10-20`. No project source archive, credentials,
configuration or production database was copied. Full analysis ran in the
existing own HISTOR image, pinned by immutable ID:

`sha256:79bc0c21f402e16b32ce00a2ac73782b9985ef9a8595adb936080db2c7b0cc13`

Python 3.11.2 / Linux amd64 / Docker runc. Container network disabled, root
filesystem read-only, input mounts read-only, UID 65532, all capabilities dropped,
no-new-privileges, 1 CPU and 1,536 MiB. Only the research scripts and our installed
canonicalizer ran; no MCP server or external package was executed. The attempted
runsc runtime was unavailable and stopped with exit 125 before code execution.

| Input | SHA-256 |
|---|---|
| manifest.json | a7bfc9e09ab9782157ad6c7a4bb136477609746a7e7e6f9c6695ea2012e926fc |
| servers.jsonl.gz | 7e96f47212faac4a25dcdeb13a2920c20d548ae0f5b2df823f604117cf5b8b0b |
| changes.jsonl.gz | 8df3d75824a2505014422c63583f1b2d987c21509e218a662c4ece26e6147a6f |
| toolsets.jsonl.gz | 9d5f8493910741c084a4e8315375d6bba918d5a0fad8d7bbc02f1e216773e2a2 |

All gzip bytes were hashed on Linux before classification. All 14,869 required
blobs were found and digest-verified there. The classifier measures the four
canonical core fields; it does not equate lexical normalization with safety.
After downloading and verifying the outputs, the temporary study directory was
removed from admin-vps at 08:48:55 UTC. The existing public snapshot was untouched.

## Reproduce

Copy `analyze.py`, `test_analyze.py`, `cohort_readonly.py`, `protocol.md` and
`run_remote.py` into a fresh study directory before running the orchestration
script. It refuses to overwrite an existing execution record. It expects the
same configured admin-vps alias, existing frozen input path and pinned image;
it neither changes production state nor downloads/installs dependencies.

```sh
python3 run_remote.py
```

Alternatively, in a Linux Python environment with the own HISTOR canonicalizer
whose module hash is recorded in summary.json, run against a local read-only
copy of the snapshot and a fresh output directory:

```sh
python3 -m unittest discover -s . -p test_analyze.py -v
python3 cohort_readonly.py /path/to/snapshot
python3 analyze.py --data /path/to/snapshot --out /path/to/new-output
```

After downloading outputs, the independent verifier checks exported counts and
provenance without reading raw gzip blobs or rerunning the classifier:

```sh
python3 verify_results.py --write
python3 detail_tables.py
```

These local output checks do not constitute a second external replication. Hashes
prove consistency with the pinned inputs; the manifest signature was preserved
but not independently verified in this study. Recorded digest chains do not
establish that daily polling captured all intermediate states.

Disclosure: AI agents produced the research, analysis scripts and reports under
the maintainer’s direction. The maintainer is affiliated with HISTOR and WARDEN.
