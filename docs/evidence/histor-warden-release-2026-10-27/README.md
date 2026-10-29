# HISTOR / WARDEN release evidence — 2026-10-27

Prepared versions: `aimarket-histor` **0.5.0** and `@aimarket/warden` **0.22.2**.
The packaged application source is recorded in Gitea commit
`0f3be96e391c4d3ac19c21ec7c7fa4aecb860ad9`.

Both releases were confirmed in the official registries at 14:58:52 UTC:

| Registry | Release | Download verification |
| --- | --- | --- |
| PyPI | [aimarket-histor 0.5.0](https://pypi.org/project/aimarket-histor/0.5.0/) | Exact sdist; separately audited wheel has identical application files and Core Metadata |
| npm | [@aimarket/warden 0.22.2](https://www.npmjs.com/package/@aimarket/warden/v/0.22.2) | Exact frozen tarball SHA256 and SHA512 integrity |

See [final registry verification](registry-final.json). The earlier snapshots
preserve intermediate states before the parallel publications completed.

## Validation

| Package | Result | Evidence |
| --- | --- | --- |
| HISTOR | All 1,102 unique source tests exercised successfully; strict Twine, secret inspection, reproducible sdist rebuild, clean installed-wheel smoke in five languages and modern MCP | [HISTOR preparation](histor/README.md) |
| WARDEN | Typecheck/build, 1,382 tests, 28 red-team scenarios, ruleset, archive/secret inspection, clean consumer and strict `server_info` compatibility/rejection checks passed | [WARDEN preparation](warden/README.md) |
| Native macOS | Final complete run: 55/55 passed. Earlier full runs were intermittent; diagnostics were improved without changing assertions or the packaged runtime. The cause remains unconfirmed. | [Final native result](warden/native-final.json), [all run details](warden/README.md) |
| MOMUS candidate | Our isolated full run passed 8,606 development cases, 48 sealed holdout cases, 31 candidate cases and 72 behavior scenarios, with zero misses, false positives or incomplete inspections. | [Quality evidence](quality/) |

English remains the default report language. English, Russian, Spanish, French and
Chinese were checked in installed local and publicly downloaded HISTOR wheels.
The release does not change runtime dependency declarations.

## Registry observations and concurrency

The release team did not obtain registry credentials or execute an upload. During
preparation, PyPI 0.5.0 appeared at 14:39 UTC through a parallel publisher; the user
subsequently confirmed that the WARDEN release was also in progress. Its sdist is
byte-identical to our frozen artifact. Its wheel contains
identical application files and Core Metadata; only the Hatchling generator
version and its corresponding RECORD entry differ. The downloaded public wheel
also passed isolated installed-consumer checks. Both wheel identities are retained;
the original build manifest is unchanged. See the [public artifact audit](histor/registry-observation/README.md).

Our isolated MOMUS run did not deploy a container. A different actor subsequently
built/evaluated image `sha256:170a2523716bed3101b1a6420cab17eced83a0096053ba4b90e5ed75d51bddc1`
with the same JS digest and source commit. A read-only observation found that image
running as HISTOR at 14:51 UTC, and the unchanged WARDEN live release gate passed
against signed run `20261027T144703`. The user confirmed a parallel release; the
actor's individual identity is not captured by this evidence. No deployment,
promotion, signing-key access or
quality-gate change was performed by this release team.

The observed live image still reported WARDEN package metadata version `0.20.0`
despite the correct new compiled JS digest. The local remediation recipe now
copies `package.json` together with `dist` to prevent this mismatch in a future
authorized deployment; that local fix has not been deployed by this team.

Registry snapshots record the status actually observed; they are not upload
receipts. `verify-registry.py` reads only official HTTPS registries, verifies
downloaded bytes and checks the separately audited public wheel's complete
payload/RECORD. Run with Python 3.11+:

```sh
python3 docs/evidence/histor-warden-release-2026-10-27/verify-registry.py \
  --output /private/tmp/histor-warden-registry-status.json
```

It returns nonzero while either package is absent or a verification fails.
It does not publish or use credentials. Check the newest snapshot before any
future upload, especially after an uncertain upload outcome; do not blindly retry
an immutable registry version.

## Artifacts and Git scope

Frozen upload candidates and their hashes are retained in
[HISTOR artifacts](histor/artifacts/), [HISTOR manifest](histor/artifact-manifest.json)
and [WARDEN manifest](warden/artifact.json). Local tool environments, duplicate
build output, live databases and raw evaluator/provider data are excluded.

The post-preparation changes only add native assertion diagnostics, preserve the
correct WARDEN `package.json` in the HISTOR remediation image recipe, and record
release evidence. They do not modify either frozen registry candidate's runtime.

Git operations target only `ssh://git@gitea2/alexar76/aicom.git`. Release commits
use `[skip ci]` to request suppression of the main-branch deployment workflow.
The documented `SKIP_LINK_GATE=1` option is used because that link gate targets a
trimmed public satellite mirror; this evidence belongs to the complete Gitea
monorepo. Author, trailer and Python bug gates remain enabled. GitHub publication,
tags, releases and API writes are outside this release and were not performed.
