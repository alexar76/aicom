# Qingfeng: reference-only egress boundary checks

26 October 2026. Completed on Linux factory-vps: build, typecheck, **127 tests across four suites**, including **25 new reference-only tests**. Runtime code, thresholds and version were not changed by this check. The tested package metadata is 0.22.1. No model API calls or real external tool transmissions; added API cost USD 0.

## Findings

Handwritten phrases such as “Use the third entry in that spreadsheet” have no recorded secret fingerprint match. With a credential read and outside text observed, the hook still asks before the outbound call; deny mode denies. This persists across 1/3/8 observed intermediate results and a fresh user turn. A user-named or allowed recipient alone does not waive this boundary. Opaque MCP tool names are covered by the MCP branch; a non-MCP tool requires explicit outbound classification.

These are boundary tests, not semantic provenance. An unknown non-MCP tool is not intercepted by this boundary. Without an observed credential or outside text the credential boundary does not activate. Audit/off do not enforce. A protected exact operator rule can allow an opaque reference-only request once; repetition and changed body/recipient/nested arguments/tool ask again. The detector does not certify that the referenced content is public. Exact authorization never waives a known literal credential match.

The existing answer-review suite records a paraphrase gap without shared literal windows. No claim of tracing a model's semantic transformations follows. Existing isolated short-fragment tests still pass; strong windows remain 8 non-hex/10 hex. No runtime defect requiring a patch was established within this scope. Host enforcement, correct integration, source observation and explicit policy remain prerequisites. Task-adapter enforcement was not re-evaluated in this run.

## Execution and custody

User specifically authorized this 101-file, 316 KB payload to factory-vps after automatic review initially rejected the export. No keys, dependencies or server configuration were transferred. npm dev dependencies installed with scripts disabled; build/typecheck/tests ran in an unprivileged, read-only container with no network. No test executed a real sender. Source and output manifests retained; six collected output hashes verified before deleting the owned temporary directory. No failed run or retry; no GitHub/npm write.

[Results](results.json), [protocol](protocol.md), [input manifest](run-01/input-manifest.json), [execution receipt](run-01/execution-local.json), [output manifest](run-01/output-manifest.json), [outputs archive](run-01/outputs.tar.gz). AI assisted test preparation and documentation. Package reports are in EN/RU/ES/FR/ZH.
