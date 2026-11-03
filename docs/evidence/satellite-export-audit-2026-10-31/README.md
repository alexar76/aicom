# Local satellite export audit — 2026-10-31

All **59 mapped satellite entries** passed the unchanged final `verify_mirror_secrets.sh` gate: **13,965 exported files**. This covers optional and closed entries and the nested Emberline alias; the factory entry is outside this audit.

The audit uses the production export functions with offline adapters for remote preparation and publication. Git transports are disabled. Course assets build in an isolated source copy. Closed entries receive local source exports without changing their publication flags or production refusals. Warden's registry workflow is checked from local source; the production comparison against the live remote blob remains required and unchanged.

## Fixes

- Every transfer, including special layouts and vendored dependencies, now uses the canonical exclusion policy. Public example files and the digest-checked signing-storage source module remain available.
- Excluded files left in preserving exporters are removed before staging. The live Warden registry workflow is preserved.
- Attested's internal `DNS-PLAN.md` and PingBlip's internal `deploy/` directory no longer enter export candidates. These contained private infrastructure literals.
- PingBlip's local `clips/` outputs are excluded. An incomplete 262-byte render triggered the raw-binary safety check; the check remains unchanged.
- A missing optional README anchor no longer aborts banner insertion under `pipefail`.
- Public satellite and factory maps omit every closed entry, including knowledge-visible local components. Local knowledge keeps its existing visibility rules.
- Dioscuri cleanup removes stray files from the candidate rather than deleting workspace source files. Transfer/filter failures stop the export explicitly, including aggregate dispatch where Bash's `errexit` is disabled.

## Evidence

- `report.json`: scope, results for every entry, source fingerprints, resolved findings and audit limits.
- `manifests.jsonl`: paths and SHA-256 hashes of exported files; no file contents.
- `all-secret-checks.txt`: all 59 successful final gate logs.
- `rejections-before-fix.txt`: path-only rejection evidence; no private host values.
- `pytest.txt` and `shell-secret-guard.txt`: regression results.
- `static-checks.txt`: syntax, Python bug lint, links and knowledge synchronization checks.

The final report combines the full pass with targeted rebuilt exports for Attested, PingBlip and Alien Monitor after their relevant policy/public-map fixes. Original local export trees are referenced by path in the report. This certifies local export hygiene, not application runtime behavior or live remote history. No GitHub publication occurred.

Reproduce in a new output directory:

```sh
.venv/bin/python scripts/audit_satellite_exports.py --output /private/tmp/aicom-satellite-audit-new --jobs 4
```
