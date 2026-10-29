# WARDEN 0.22.2 release quality evidence

The team ran one isolated full candidate evaluation using the existing root-owned MOMUS hook. It passed. The team did not deploy or promote WARDEN, change the evaluator or release gate, copy signing keys, or inspect private corpus/provider rows. A parallel release subsequently evaluated and promoted another image. The user confirmed that WARDEN release work was running in parallel; the executing identity was not captured.

## Frozen release artifact

| Field | Value |
|---|---|
| npm package | `@aimarket/warden@0.22.2` |
| Tarball | `../warden/aimarket-warden-0.22.2.tgz` |
| Tarball SHA256 | `0256dad4208f750b56ba7c803dc5fe62c927f7930d621536381c653804751a57` |
| JavaScript build digest | `3b6b074cf0be2415a049610d2908787d820b321ae68eb6d4837306dc9f5f16de` |
| Prepared source commit | `0f3be96e391c4d3ac19c21ec7c7fa4aecb860ad9` |

The package contains 345 files and 936,594 bytes. Its 63 top-level compiled JavaScript files and package metadata matched the frozen local release. Source and package metadata matched the prepared commit. The digest algorithm is the unchanged production gate's sorted top-level `dist/*.js` hash.

## Our isolated full evaluation

The evaluation image was built without network access from the enrolled HISTOR base `sha256:befe7e54d444d0d9b2658151725b264fc6bb61dbbdb0927caff60f281ba249d6`, replacing the full vendored WARDEN payload with the verified tarball. This image was never started as a HISTOR service or promoted. The prepared source commit arrived after staging; the evaluation-only image has no source commit label. Provenance is recorded separately in `candidate-artifact.json`.

- Image: `sha256:0f0c4f35da115e7d602701aebae9bff1781d33ce395a700a81e48869da3bdd33`
- One-shot unit: `warden-release-quality-0222-20261027.service`
- Command: `/usr/local/sbin/skopos-warden-quality candidate IMAGE_DIGEST`
- Start: 2026-10-27 14:39:37 UTC; run: `20261027T143941`
- Result: passed; native hook exit status: 0.

| Suite | Coverage | Missed | False positives | Incomplete |
|---|---:|---:|---:|---:|
| Development | 8,244 attacks + 362 benign | 0 | 0 | 0 |
| Sealed holdout | 24 attacks + 24 benign | 0 | 0 | 0 |
| Generated candidates | 31 unlabeled proposals | 0 | 0 | 0 |
| Sandbox behavior | 72 / 72 executed | 0 | 0 | 0 |

Discovery completed and generation succeeded. Unlabeled proposals do not establish attack-detection accuracy. Only aggregate counters were inspected; sealed fixtures and raw provider responses remain on the evaluator host.

The native hook publishes to a single candidate channel. A later evaluation replaced that channel before our completed result was collected, so our first run's signed envelope was not archived. `candidate-first-run-summary.json` is explicitly a sanitized host-report summary, not a signed receipt. No receipt was reconstructed or re-signed.

## Separately observed promotion

At the next public status check, the candidate channel contained run `20261027T144703` for another image with the same JavaScript digest. The parent and quality agent had not started that run or authorized/executed a deployment. Read-only inspection subsequently found this image running in production:

| Field | Observed value |
|---|---|
| Image | `sha256:170a2523716bed3101b1a6420cab17eced83a0096053ba4b90e5ed75d51bddc1` |
| Image created | 2026-10-27 14:42:53 UTC |
| Source label | `0f3be96e391c4d3ac19c21ec7c7fa4aecb860ad9` |
| HISTOR container started | 2026-10-27 14:51:20 UTC |
| Health | healthy |
| Installed WARDEN package metadata version | **0.20.0** |
| Installed JavaScript build digest | Exact frozen 0.22.2 build digest above |

Both the candidate and live public receipts for run `20261027T144703` were saved and verified using the unchanged gate's public key and strict `checkEvidence` function against the frozen JavaScript digest. These establish signed evaluator results for that build. They do not identify the actor who initiated evaluation/promotion. The user subsequently confirmed the parallel release was in progress. The newer live receipt caused the unchanged production release gate to pass.

The initial live receipt bound the older build `a5890becf7f2374b0f3bf13ae3b974da024b19ccf6fc70384a59a147cedacea1`; strict verification correctly rejected it for the new build. The saved before/after receipts preserve this distinction. At the first journal inspection, the existing shared-agent journal contained no entry for the new image; that observation alone does not establish its origin.

## Local recipe correction

`warden/deploy/Dockerfile.histor` originally copied `dist` and source onto the existing HISTOR base while retaining its old WARDEN `package.json`. Runtime version reporting reads package metadata, so matching JavaScript alone could leave version 0.20.0 installed. The observed production image demonstrates that discrepancy.

The local correction adds one `COPY --from=test /warden/package.json` into the installed WARDEN directory. Its intended package metadata matches the frozen tarball exactly and reports 0.22.2; all 63 compiled JavaScript files remain identical. `git diff --check` passed. This corrected recipe was not remotely built or deployed by the quality agent. The observed version 0.20.0 is a point-in-time finding while the confirmed parallel release was still in progress. No further paid evaluation was started after concurrency was discovered.

## Existing release-owner path

The Factory detector scope in `web/backend/services/remediation_fix.py` permits seven detector modules; this release's MCP tool and metadata changes are outside that automatic repair scope. Existing operator enrollment is a separate, honest release-owner procedure. The documented 2026-10-10 acceptance and root-owned `/opt/native-quality-20261010/prove.py`, plus `/var/tmp/histor-warden-operator-deploy-446c2135f.py`, provide prior examples without claiming a manufactured regression or Factory authorship.

The existing procedure uses the enrolled signing services and shared executor:

1. Put the reviewed source commit on an allowed internal Gitea branch under `momus/fix-`, retaining an explicit operator-release identity.
2. Request a BuildOrder signed inside the existing SKOPOS conductor. The shared node executor verifies the enrolled signer, service allowlist and branch, builds its fixed recipe, enforces the component suite, runs full native candidate quality, and creates its own build-journal entry.
3. Request an actual MOMUS candidate `warden_release_quality` retest. Its signed FixVerdict must pass and bind the same immutable image.
4. Only after explicit production authorization, request the conductor-signed DeployOrder and use the existing executor, which checks the signed chain, its journal and latest candidate receipt, verifies health/live binding, and supports rollback.
5. Re-run the unchanged npm quality gate against production `latest.json`.

The native build verifier does not apply the Factory's detector file scope. This owner path therefore supports reviewed MCP/metadata changes without widening the Factory scope, altering host policy, inventing detector findings, copying keys, or manually editing the build journal. None of these build/deployment steps were executed by this quality agent for the later observed image.

## Local verification

From the workspace root:

```sh
node docs/evidence/histor-warden-release-2026-10-27/quality/verify-receipt.mjs \
  docs/evidence/histor-warden-release-2026-10-27/quality/external-candidate-signed.json
node docs/evidence/histor-warden-release-2026-10-27/quality/verify-receipt.mjs \
  docs/evidence/histor-warden-release-2026-10-27/quality/external-latest-signed.json
```

Receipts expire. Verification at a later date can correctly fail freshness checks. `verify-receipt.mjs` only verifies archived evidence; it does not change the npm publication gate or redirect its production receipt URL.

The directory contains only public signed receipts, sanitized aggregates, artifact hashes, safe host recipe metadata, and reproducible staging/verification helpers. No GitHub publication was performed.
