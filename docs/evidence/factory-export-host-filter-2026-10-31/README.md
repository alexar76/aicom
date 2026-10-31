# Factory export host-filter regression — 31 October 2026

The failure was reproduced in an offline rsync candidate using the canonical factory exclusions. Twelve files still carried forbidden infrastructure literals: security-rollout inventories, fleet-cleanup/resource evidence, and two native social-page captures. The local private-host policy file also reached the candidate; it was exempt from its own content rule and therefore needed an explicit filename rejection.

The export now excludes operator evidence and raw captures while keeping public product source, summaries and Kaggle examples. The shared rsync defaults also exclude `.mirror-forbidden-hosts` for satellite exports. Exclusions do not weaken the secret scanner.

A reused export needs cleanup as well as rsync filtering: rsync does not delete an excluded destination file, and the former quoted shell deletion did not expand wildcard exclusions. `purge_factory_local_paths` expands the canonical policy in both local-export and mirror-clone paths. It refuses the workspace and parent directories and checks that intermediate symlinks cannot lead deletion outside the candidate. The clone's `.git` is preserved.

The private-host error now prints candidate-relative filenames only, without matched lines or host values. A policy file anywhere in a candidate is rejected, even when its values differ from the trusted external policy.

Validation:

- 64 Python export/structured-secret regression tests passed.
- 28 publishing-path regression tests passed, using dry runs and disposable local Git repositories.
- 43 shell secret-guard checks passed.
- A real local factory candidate was rebuilt; seven stale internal paths were removed. See `local-export-check.json`.
- `full-export-secret-check.txt` records the full candidate guard result.

No GitHub clone, push, API write or remote publication was performed for this fix. No forbidden host values are included in this evidence bundle.
