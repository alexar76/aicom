# HISTOR / WARDEN metadata deployment — 2026-10-27

The user authorized rebuilding and deploying HISTOR with the corrected WARDEN
Docker recipe, verifying WARDEN 0.22.2 and MOMUS, and committing/pushing results
to Gitea only.

## Result

Deployment completed **2026-10-27 20:27:22 Moscow time** (17:27:22 UTC).
Independent live acceptance passed **17/17 checks** at 20:29:53 Moscow time.

| Check | Verified result |
| --- | --- |
| Running image | `sha256:1221f1bcc8af9081c923b9064301674d5bc4d8d0ce701cca1075a5b1355b3017` |
| Deployed source | `4afe0243856d02b6b543b9b9559f2a286fab1a90` |
| WARDEN package / scanner / MCP | 0.22.2; metadata readable by runtime UID 65532 with mode 0644 |
| Public and loopback issuer | `@aimarket/warden@0.22.2`, refreshed by normal application registration |
| HISTOR health | HTTP 200, version 0.4.2, production profile, PostgreSQL |
| Application preservation | All 43 Python source files and all 92 checked application/static/scanner-support files match the preceding image |
| Native component tests | Enforced and passed; no assertion, network or memory gate was relaxed |
| MOMUS | Signed candidate and live receipts, full run `20261027T165628`, bound to the running image and deployed source |
| Quality coverage | 8,606 development cases, 48 sealed holdout cases and 72 behavior scenarios passed with zero misses, false positives or incomplete inspections; 31 unlabeled proposals inspected separately |
| Transparency log | Signed tree head and append-only consistency verified: 1,115,959 → 1,116,921 entries |
| Existing crawl | Run 27185 automatically resumed run 27097 in the same cycle; classifier budget 0 and package budget 8,000 retained |
| Rollback | Previous image retained in the native journal; rollback available and not needed |

See [independent acceptance](verification/after/acceptance.json),
[native deployment](native/final-deployment/verified.json),
[rollback journal](native/final-deployment/native-journal-projection.json) and
[unchanged release gate](verification/live-gate.log).

The health endpoint retains a historical interrupted-run marker from the
intentional restart. The resumed current run has no error. Historical run data
was preserved. Unsaved registry lookups from the planning phase may repeat;
normal crawl checkpoints have 30-second granularity.

## Final closeout check

A fresh [runtime acceptance](verification/final-check/acceptance.json) passed
17/17 checks at **2026-10-27 20:36:21 Moscow time**. The running image/source,
WARDEN 0.22.2 in package/scanner/MCP and both issuer routes, production PostgreSQL
health, unchanged HISTOR application, and signed MOMUS bindings were reconfirmed.
The signed log grew consistently from 1,115,959 to 1,117,580 entries. All six new
JSON witnesses passed an independent local review and secret inspection.

The required closeout order is: verify the running service, stage the results,
commit, push to Gitea, and only then report completion to the user. This check
made no deployment, model call, MCP tool call or authentication change.

## Reviewed source and scope

- Source: `4afe0243856d02b6b543b9b9559f2a286fab1a90`.
- Allowed Gitea branch: `momus/fix-warden-0.22.2-metadata-4afe02438`.
- Recipe: `warden/deploy/Dockerfile.histor`, SHA256
  `d4e40dd761cb6898d11fc5336a9d507caf7b4614ec1c0012ff2b2dcd0c4ff4d2`.
- Expected WARDEN: `@aimarket/warden@0.22.2`; package.json SHA256
  `0411601d6ec47d8d14f608a6643a94589e094940dcd93dde36bdcda52a57a34b`.
- Expected compiled build: 63 JavaScript files, digest
  `3b6b074cf0be2415a049610d2908787d820b321ae68eb6d4837306dc9f5f16de`.

The reviewed remediation recipe preserves the enrolled HISTOR application
(version 0.4.2), its schema and PostgreSQL data. It copies WARDEN's compiled code,
package metadata and reviewed source. This operation does not deploy the PyPI
HISTOR 0.5.0 application.

Before deployment, the healthy HISTOR container ran image
`sha256:170a2523716bed3101b1a6420cab17eced83a0096053ba4b90e5ed75d51bddc1`.
Its WARDEN JavaScript already matched the expected build, but package.json,
scanner describe, MCP discovery and stored issuer metadata reported 0.20.0.
The trusted application base was
`sha256:befe7e54d444d0d9b2658151725b264fc6bb61dbbdb0927caff60f281ba249d6`.

## Execution and independent verification

[Native evidence](native/) records the operator release through the existing
enrolled signed executor. The procedure uses a signed BuildOrder, enforced
component tests, mandatory candidate quality, an actual MOMUS candidate retest,
an image-bound signed FixVerdict, a signed DeployOrder, the executor's journal,
health/live quality gates and signed rollback on failure. No detector regression
or AI-Factory patch authorship is invented.

[Chain review](chain-audit/review.json) records the reviewed helper and guards.
Always invoke the operator helper with the native virtualenv's Python `-I`.
The first helper's filename `operator.py` shadowed a standard-library module
without isolated import; that attempt failed before any native build/action.
The corrected run uses `run-native-release.py` and still requires `-I`.

The first native source, `ce1dd74edc30e7d5775c7583079cc4f9ed5d656f`, was
correctly blocked by enforced component tests: 1,381 passed and one failed.
The failing documentation test found 22 links to seven committed growth documents
outside the WARDEN-only test image. The corrected source includes exactly those
seven documents in the test stage and both supported Docker context allowlists.
All assertions, network/memory limits and final image COPY payloads are preserved.
See [failure and context proof](test-diagnosis/README.md). The original failed
attempt is retained under `native/first-native-attempt/`.

The second source, `231c6b0618670b408c460ce63fe8d5b1af287563`, passed component
tests and signed MOMUS evaluation. Independent default-user inspection nevertheless
rejected its image: root-owned package.json had mode `0600`, so runtime UID 65532
could not read the otherwise correct 0.22.2 metadata. It was not deployed.
See [candidate diagnosis](verification/candidate-diagnosis.json).
The final recipe normalizes this public file to `0644` and performs a JSON read
under the inherited runtime USER during the image build. It preserves metadata
bytes, compiled JavaScript, runtime user identity and all existing gates.

An initial deployment attempt stopped before the executor because the custom
idle guard observed a newly started crawl. Actual production resume/checkpoint
methods were verified against the reviewed source. The reviewed resume-aware
operator helper uses the same signed native deployment and verifies continuation
of the existing cycle, including successful-completion races; its optional API
fallback was not needed. The image did not require another build or quality run.

[Independent acceptance](verification/README.md) checks immutable image/source,
package bytes, scanner/MCP runtime metadata, application preservation, PostgreSQL
health, strict signed MOMUS receipts and the append-only transparency log. It
makes no MCP tool calls or model calls.

Stored issuer metadata and actual installed/runtime metadata are recorded
separately: the issuer is a stored observation refreshed by normal ruleset
registration, not a direct read of package.json.

## Credential-output incident

During read-only preflight, a repository URL containing an embedded transport
credential appeared in a tool output. Its setting is `SKOPOS_AGENT_REPO_URL` in
`/etc/skopos-deploy-hand/env`. The value is not copied into these files. Subsequent
commands use explicit safe-field projections, omit native stdout/stderr and raw
exception messages, and keep existing credentials in service/process memory.
Authentication was not changed. The exposed repository transport credential
requires a separate owner rotation; removing it from evidence cannot revoke it.

All source and evidence Git writes target the `alexar76/aicom` Gitea repository.
No GitHub push, pull request, tag, release or API write is part of this operation.
