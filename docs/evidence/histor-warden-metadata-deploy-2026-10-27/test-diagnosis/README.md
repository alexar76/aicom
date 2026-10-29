# Native component-test diagnosis

The native executor's enforced component test gate stopped the initial
`ce1dd74edc30e7d5775c7583079cc4f9ed5d656f` candidate before MOMUS or deployment.
An exact diagnostic repeat preserved `--network none`, `--memory 1g` and
`npm test -- --maxWorkers=2`, adding only Vitest's JSON reporter.

The repeat ran 1,382 tests: 1,381 passed and one failed, with no unhandled errors.
The sole failure was `test/docs.test.ts`, `documentation set resolves every
relative link`, which found 22 missing paths. Its test-stage image was
`sha256:5527cf401e8da1277df27827b177dd5d2361dede086079da03f91a112f5a8dd1`.
The production image was unchanged.

## Cause

The five `docs/flow-guard*.md` pages contain 22 links to seven committed documents
under the monorepo's `docs/growth/`. The full checkout contains those files, so the
same documentation check passes locally. The isolated Docker test stage copied
only WARDEN into `/warden`, leaving its referenced `/docs/growth/` files absent.
No runtime or security assertion failed.

[Full-checkout link audit](full-workspace-links.json) checks the same 45 documents
and 718 relative links as the existing test. It records all 22 external
references and their seven-file closure. [Static context proof](context-proof.json)
records the correction from 22 missing paths to zero; it is explicitly a static
proof, separate from the native Docker/Vitest run.

## Correction

The Dockerfile's **test** stage now copies exactly the seven referenced documents
to `/docs/growth/`. Both its BuildKit-specific ignore file and the root legacy
fallback allowlist exactly those seven files while keeping other workspace docs
excluded. The root fallback also exposes those seven public files to the generic
root build context. The WARDEN final image still copies only `dist`,
`package.json` and reviewed WARDEN source from the test stage; these public
reference documents do not enter that final image.

No assertion, test selection, worker count, resource limit, network restriction or
release gate changed. WARDEN runtime source, package metadata and frozen npm
archive were not modified. [Frozen release check](frozen-release.json) confirms
version 0.22.2, the original package.json hash and original compiled JS digest.

The corrected recipe SHA256 is
`74a4ade4589ce9ff79f0ae4281a8bd84eb6043c8fe67319eea375070c8e055cf`.

## Local checks and reproduction

The unchanged existing documentation suite passed **13/13**; see
[scoped result](docs-scoped-local.log). This does not substitute for the native
executor's full enforced suite, which must run against the new pinned source.

From the workspace root:

```sh
node docs/evidence/histor-warden-metadata-deploy-2026-10-27/test-diagnosis/audit-doc-links.mjs warden
node docs/evidence/histor-warden-metadata-deploy-2026-10-27/test-diagnosis/check-test-context.mjs
cd warden
npm test -- --maxWorkers=2 test/docs.test.ts
```

The two Node scripts read only committed documentation/context inputs. They do
not perform network requests, model calls, deployment or Git mutations.
