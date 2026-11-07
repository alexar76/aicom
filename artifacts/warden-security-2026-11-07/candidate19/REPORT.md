# Warden v19: conservative post-hoc repair, both gVisor hosts

Operational/protocol acceptance: **true**. This is not a claim that every malicious definition is detected.

Both hosts:1536/1536 tests in63 files, zero test failures; typecheck,build,redteam commands pass; source witness unchanged and no OOM. Final baseline evidence is baseline-final-v4; initial metadata diagnostics and the interrupted obsolete Blip second attempt remain preserved. The final validation copy changes only five README suite counts; every other source and compiled file is byte-identical to the immutable detector used for the paired measurement, checked before and after the full suite. The Vitest JSON has no dedicated runtime-error count; acceptance requires its success flag, zero failed suites, and successful command exits.

| Cohort/view | N | v18 blocked | v19 blocked | v19 errors |
|---|---:|---:|---:|---:|
| author-labelled | 35 | 23 | 23 | 0 |
| independent | 12 | 10 | 10 | 0 |
| mcptox-clean | 45 | 0 | 0 | 0 |
| mcptox-decorated | 225 | 225 | 225 | 0 |
| mcptox-scenarios | 1348 | 1331 | 1331 | 0 |
| mcptox-served | 485 | 457 | 459 | 0 |
| public-carryover | 41 | 1 | 1 | 0 |
| public-main | 986 | 3 | 3 | 0 |

Actual MCP/library parity:3177/3177 for each version on each host. Cross-host:12708/12708 full compared rows. Inputs, opaque IDs, harness, replay and source trees match; all retained source/input witnesses are unchanged.

Verdict transitions: mcptox-served/X-FileSystem_20 true→false; mcptox-served/X-FileSystem_23 true→false.

The pure public-key-read native case FileSystem_22 remains allowed/advisory. Restoring a benchmark label alone does not justify classifying public material as a secret. The repair blocks forced overwrites of SSH security files and reads of actual secret stores bound to another mandatory tool call. It was designed after observing the retained v18 results, so it is post hoc regression work, not an unseen holdout result.

MCPTox native, decorated and full-scenario views overlap and are not additive independent trials. Public snapshots are unlabelled: block frequency is not a whole-corpus false-positive rate. No upstream implementations, model attack-success experiment, live secrets, production mounts, or local project runtime were used.

Candidate:0.23.1-dev.20261107.1; rules19; sha256-XfRh1+VZoAM6PGtbmqprnSX/eF16qNYOk0o+ilRFxXw=. Public npm was0.23.0 at the retained registry check; no npm publication is part of this run.
