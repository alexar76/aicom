# ACS #38 draft verification, 28 October 2026

Read-only production access; no publication or production changes were performed.

## Reproduction

- `recompute_snapshot.py` independently reproduces the registry-export statistics from the fixed 20 October snapshot. `snapshot-result.json` records counts, input checksums and caveats.
- Zenodo record 23512760 metadata was read via its public API. MD5 checksums of local servers, changes and toolsets match that record; SHA-256 checksums match the local manifest.
- `fetch_live_versions.py` captures all 23,821 historical change rows from the public API, keeping complete compressed responses in `api-pages/` plus a compact version-pair export. Its fixed ID cohort is 1 through 23,821.
- `recompute_live_versions.py` verifies every API row has the same server ID and observation time as its snapshot counterpart, then independently computes the version comparisons. `live-version-result.json` has the results.
- Runtime pairs: 17,401 identical strings among 21,401 remote changes with two nonempty values (81.3%). Both runtime-string equality and the registry-export no-publication criterion hold for 15,351 of 21,209 jointly judged changes (72.4%).
- All 21,543 historical remote rows have null `from_registry_version` and `to_registry_version`. The combined statistic uses the separate registry-publication join, not these null columns.
- No duplicate `(target_id, observed_at)` pairs occur among the cohort's changes. This does not by itself exclude duplicate observation timestamps; the implementation's timestamp matching has that edge case.

## Source review

Migration 016, crawler recording, API serialization and dataset export were reviewed. Server versions are backfilled from retained observations. Historical registry versions are left null. Selected existing SQLite migration/crawler/API/dataset checks passed; PostgreSQL variants were skipped without a configured test database.

## Necessary wording corrections

1. Registry intervals start at the previous **change**, or first pin, not at the last successful read of the old list. Runtime comparisons use the last run serving the old list and the run serving the new list.
2. The cached 28 October registry export was fetched without `include_deleted=true`. Default registry reads omit deleted entries. Its figures reproduce exactly, but are results against that export and do not prove complete historical publication history or the active runtime version.
3. MCP has no per-tool version, but ACS does not require integration-supplied tool versions to come only from server metadata.
4. Added/removed tools are expressible in `agbom/changed`. The narrow gap concerns in-place edits when the other standard component fields stay unchanged.
5. October 20 toolsets retain normalized name, description, inputSchema and outputSchema only. Annotations were not captured until October 22. Arbitrary future full-declaration digests cannot be reconstructed from this old snapshot.
6. Description-only means only among fields retained by the snapshot.
7. API version fields may be null. The weekly export code does not guarantee publication on precisely November 2.

## Public references

- https://doi.org/10.5281/zenodo.23512760
- https://histor.modelmarket.dev/api/v1/changes
- https://github.com/GenAI-Security-Project/agent-control-standard/issues/38
- https://modelcontextprotocol.io/registry/versioning
- https://raw.githubusercontent.com/modelcontextprotocol/registry/main/docs/reference/api/openapi.yaml
- https://raw.githubusercontent.com/GenAI-Security-Project/agent-control-standard/main/specification/v0.1.0/agbom/component.json
- https://raw.githubusercontent.com/GenAI-Security-Project/agent-control-standard/main/specification/v0.1.0/hooks/agbom-changed.json
