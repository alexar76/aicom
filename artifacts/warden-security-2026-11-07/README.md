# WARDEN security comparison: evidence index

The five published products each received 18,110 target rows independently on
Attested and PingBlip under remote gVisor. Inputs overlap across benchmark
views; the row total is not a count of independent attacks or live servers.

| Product | Published package/version |
|---|---|
| WARDEN | `@aimarket/warden` 0.23.0, ruleset 17 |
| mcp-audit | `mcp-audit-scanner[mcp]` 0.28.0 |
| mcp-shield | `mcp-shield` 1.0.4 |
| truecopy | `@askalf/truecopy` 0.10.5 |
| mcpsentry | `@roshan6335/mcpsentry` 0.1.5 |

The final coverage and full native-signature pairing are in
[comparison-final/figure-cross-host.json](comparison-final/figure-cross-host.json).
All completed comparable results agree across hosts; errors and partial scans
remain outside that denominator. High/critical signals are not a common native
enforcement outcome. Public/HISTOR positive frequency is not a false-positive rate.

- [Full inventory and licensing notes](inventory/README.md): 18,110 metadata rows.
- [Final grouped metrics](comparison-final/grouped-results-v2.json).
- [Paired primary outcomes](comparison-final/paired-case-outcomes.csv.gz): 90,550 pairs.
- [Separate frozen candidate outcomes](comparison-final/paired-case-outcomes-candidate19.csv.gz): 18,110 pairs.
- [Definition methods](comparison-final/comparison-methods.md) and
  [native enforcement mapping](comparison-final/enforcement-mapping.json).
- [Frozen candidate .1 report](candidate19/REPORT.md): post-hoc ruleset 19,
  1536/1536 tests on each host; MCPTox public-key-read miss retained.
- [Frozen compatibility .2 report](binary-resource-fix/REPORT.md): optional-MIME
  embedded blob fix, 1536/1536 full tests and 304 focused tests on each host.
- [Frozen .1 live interoperability](live/README.md): 8/8 SDK sessions per host,
  plus separate public HTTP discovery.

The current 0.23.1-dev.20261108 source additionally contains Codex/OpenCode
hooks absent from .1/.2. Its [separate acceptance report](current-source-20261108/attested/results/final-report/REPORT.md)
records 1574/1574 full tests, 262/262 focused tests, all five pipeline stages,
8/8 SDK sessions and 4/4 list parity on each host. The representative CLI/library
comparison has 92/92 equal cross-host rows. All 448 local source files match both
tested snapshots, with source-manifest SHA256
`92b4759c6a2ea19a1cc19f3924283b3d5956c755245eb5e6bcc27614a4131758`.
This acceptance is never substituted for either frozen comparative measurement.

The [scoped Gitleaks review](scoped-secret-scan/safe-summary.json) covers only
that already-present WARDEN snapshot in Blip: one prose false positive and two
synthetic test fixtures. Its native exit code 1 is preserved. It is not a
whole-aicom secret scan.

The illustrated article was published as alexar76:
[Five MCP security scanners on the same tool definitions](https://dev.to/alexar76/five-mcp-security-scanners-on-the-same-tool-definitions-5gmp).
The author maintains WARDEN and HISTOR; this is a maintainer-run comparison.
Exact replay of maintainer fixtures/adapters needs their source release.

The [public ZIP](https://modelmarket.dev/blog/media/warden-security-comparison-2026-11-07/reports-and-data.zip)
contains 47 files: five HTML/Markdown reports, metadata inventories/outcomes,
methods, hashes, safe receipts and figures. It contains no product source or
raw unlicensed MCPTox content. ZIP SHA256:
`15c58377202a7a9012f67ddda8bcdbcdec3ed634e3176fdf776798b51b0a5029`.
The final packet manifest SHA256 is
`17d6e7ebd85dede970d77f319bf3734478a037bf9fd971a53f5bbd07b4fce3f8`.

[Publication receipt](publication/devto-publication.json),
[public HTML verification](publication/devto-render-verification.json), and
[public asset verification](publication/public-assets-verification.json)
record exact-body agreement, author, disclosure setting, HTTP 200 and asset
hashes. Article originals, figures and publication responses are stored in the
user-authorized sibling PromoMaterials/devto/warden-security-comparison-2026-11-07/.

An earlier local pilot is excluded from these measurements. Its generated
`warden/dist`, `warden/.vitest` and `warden/node_modules/.vite` were removed.
Pre-existing dependencies/coverage were preserved. The counted comparative,
compatibility and current-source acceptance jobs execute remotely only.
[Native cleanup checks](local-cleanup.json) also found no local WARDEN/Vitest process.
