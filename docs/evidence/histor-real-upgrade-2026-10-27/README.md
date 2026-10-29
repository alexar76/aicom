# Real HISTOR upgrade brief

Date: 2026-10-27. Collection reads public HISTOR JSON and builds a local report without production
MCP tool calls, production databases, deployment or publication. A separate bounded check invokes
three read-only handlers in the existing local WARDEN build, with isolated temporary state and
no network or pin writes. No packages were installed.

## Results

- [Review and concrete retest scenarios](../../../output/histor-upgrade-brief-real-2026-10-27/review.ru.md).
- [Generated prototype report](report.md) and [JSON](report.json).
- [Watchlist and snapshots](../../../output/histor-upgrade-brief-real-2026-10-27/bundle/watchlist.json).
- [Projection provenance](projection-provenance.json) and [input integrity](input-integrity.json).

Four first-party components were selected: Hub, WARDEN, Oracle Gateway and MCP Packager. Hub,
Oracle Gateway and Packager have a recorded real internal Metis integration check on 27 October.
WARDEN is included as the ecosystem's MCP review interface; an IDE skill describes its use, but
does not prove installation in a particular IDE.

There are two real before/after core-definition pairs: Hub and WARDEN. Four immutable toolsets
were checked against their change-record digests. A fifth toolset provides a successful Packager
2.1.1 baseline under the separate `mcp<2` dependency profile. Oracle has no successful toolset in
the downloaded record. Packager has no second compatible HISTOR observation for its new release.

Every snapshot comes from a saved timeline row or the explicitly recorded alternate-profile
capture. `timeline.from` is used so the first row's metadata is not attached to the last time of
a collapsed interval. Package and self-reported server versions remain distinct. Historical
extras and protocol gaps are left unknown; current annotations are not pasted onto old lists.

All four overall comparisons remain `unknown`: this is uncertainty about complete comparable
evidence, not absence of observed differences. The report preserves the observed Hub description
change and WARDEN schema changes with their workflow retest checklists.

The existing published-package integration results are context only. Their success does not
replace HISTOR observations, and old HISTOR launch failures do not prove that fixed releases
still fail.

## Sources

`raw/` holds bounded responses from public HISTOR endpoints. `search-index.json`, `detail-index.json`
and `blob-index.json` record retrieval URLs, timestamps and SHA-256. One broad search request
failed, while the selected server-detail and blob requests succeeded. Public GET requests use
no credentials. No log-label signature or dataset-manifest signature was verified in this run.

The four comparison toolsets are identified by Hub change 26174 and WARDEN change 28932.
Packager's additional baseline is linked by `server.packageSignals.legacy.toolSetDigest`.
Missing execution metadata is not reconstructed from current source or package names.

## Reproduce offline

From the `aicom` root:

```bash
histor/.venv/bin/python docs/evidence/histor-real-upgrade-2026-10-27/build_bundle.py
```

The builder uses saved JSON only and checks content addresses again before creating the bundle.
The personal prototype now accepts `extrasCoverage: "unknown"` to distinguish four-field MTL/1
captures from full MCP tool definitions. This avoids claiming added/removed annotations from
unmatched historical metadata. See [prototype guide](https://github.com/alexar76/histor/blob/main/docs/upgrade-brief.ru.md).

Focused prototype checks are recorded in [pytest.log](pytest.log). No new full-suite result is
claimed here; only the importer, report and capture-related checks were repeated for this task.

The [WARDEN contract check](warden-contract-check.json) records the local runtime finding:
`server_info.extra` is disallowed by the advertised schema but accepted and ignored by the
existing compiled WARDEN 0.22.1. Valid input is accepted and numeric version is rejected. This
is a local-artifact check, not a claim about an independently downloaded published wheel/package.

The subsequent [local fix](../warden-server-info-fix-2026-10-27/README.md) rejects unknown
`server_info` keys and adds regression coverage. The original contract-check JSON remains
unchanged as evidence of the pre-fix behavior.
