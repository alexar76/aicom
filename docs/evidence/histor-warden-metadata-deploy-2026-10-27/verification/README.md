# Independent deployment acceptance

These helpers only observe the enrolled `admin-vps` host, run read-only scanner
description and MCP discovery, read public HTTPS endpoints, and write local
evidence. They cannot deploy, request an evaluation, call MCP tools, write the
production database, access credentials or read private evaluation rows.

The fixed remediation recipe retains the reviewed HISTOR application base and
changes its vendored WARDEN package. It does **not** deploy the separately
published HISTOR 0.5.0 application. The existing application is 0.4.2.

## Final live acceptance

All **17 independent acceptance checks passed** at 20:29:53 Moscow time
(17:29:53 UTC), after the native operator completed deployment. See
[after/acceptance.json](after/acceptance.json).

| Check | Verified result |
| --- | --- |
| Running image | `sha256:1221f1bcc8af9081c923b9064301674d5bc4d8d0ce701cca1075a5b1355b3017` |
| Reviewed source | `4afe0243856d02b6b543b9b9559f2a286fab1a90` |
| Unprivileged metadata access | UID 65532 reads exact WARDEN 0.22.2 package bytes with mode 0644 |
| Installed compiled JS | All 63 files match `3b6b074cf0be2415a049610d2908787d820b321ae68eb6d4837306dc9f5f16de` |
| Scanner and MCP runtime | Both report 0.22.2; nine discoverable tools, zero tool calls |
| Public and local issuer metadata | Both report `@aimarket/warden@0.22.2`; strict stored-issuer check passed |
| HISTOR application | 0.4.2; all 43 Python files match the predeployment fingerprint and reviewed base layers remain intact |
| Production health | Public and loopback HTTP 200, `prod`, PostgreSQL, crawl running |
| Native accepted source and quality binding | Exact running image/source |
| MOMUS signatures and image binding | Candidate and live run `20261027T165628` pass unchanged strict signature/freshness/full-quality checks and bind the exact deployed image; live source matches |
| MOMUS coverage | 8,606 development cases, 48 holdout cases, 72 behavior cases; zero misses, false positives or incomplete inspections |
| Signed log audit | Valid signature and append-only consistency proof from 1,115,959 to 1,116,921 entries |

Stored issuer metadata refreshed through the normal running service; this
verification performed no production database writes, crawl triggers, model
calls or MCP tool calls. The historical interrupted-run marker remains visible
in health while the resumed crawl is running. It is recorded as a Boolean,
without copying raw error text. Current-run error/budget/resume-state inspection
belongs to the separately recorded native operator proof; this verifier does
not clear historical errors or query credentials.

The complete signed public envelopes, sanitized host/HTTP observations, verified
after head and acceptance result are retained under [after/](after/).

## Before deployment

`before-remote.json` records the observed running image and filtered metadata.
At 19:07:27 Moscow time (16:07:27 UTC) on 2026-10-27 it still ran image
`sha256:170a2523716bed3101b1a6420cab17eced83a0096053ba4b90e5ed75d51bddc1`.
WARDEN package, scanner description and MCP initialization reported 0.20.0 while
its 63 compiled JavaScript files already matched the desired 0.22.2 build.

HISTOR application source fingerprint: sort package-relative `.py` paths; hash
each UTF-8 path, a NUL, file bytes and a NUL using SHA256. Before deployment:
43 files, `a24be58d10784e10a1e0bade153d9bd6ac1ccdd5335c063a47b5cb14b0111e41`.
The package path is determined by importing `histor` with bytecode writes disabled.
Only its version, file count and aggregate hash are returned.

The existing `histor.audit` implementation verified the public signed tree head.
`before-head.json` preserves it, and `before-audit.json` records tree size 1,115,959,
root `08ffde0cfbf8ab2cb64da7eb32bf8d85c2eb3a85cf16c6d3c0f0e7f30ee108fa` and
a valid signature. A postdeployment audit uses this witness to verify that the
tree is unchanged or grew with a valid append-only consistency proof.

## Postdeployment verification

Use Python 3.11+ with the repository HISTOR environment (including `awr`,
`cryptography` and `httpx`), Node 20+, existing SSH configuration for `admin-vps`,
and the reviewed immutable image/source identities. From the workspace root:

```sh
histor/.venv/bin/python -I \
  docs/evidence/histor-warden-metadata-deploy-2026-10-27/verification/verify-deployment.py \
  --image sha256:REPLACE_WITH_DEPLOYED_IMAGE_64_HEX \
  --source REPLACE_WITH_REVIEWED_SOURCE_40_HEX \
  --out-dir /private/tmp/histor-warden-acceptance-fresh
```

The output directory must not exist; archived before evidence is never
overwritten. The collector checks that the container image and start time do not
change during its observation. It returns only whitelisted image/source IDs,
package hashes, scanner metadata, MCP version/tool names, health fields and
quality/source bindings. Public responses and receipts are bounded. The full
signed candidate/live envelopes are public aggregate evidence and are preserved.

Acceptance requires:

- Healthy running image and exact reviewed source commit.
- Reviewed HISTOR base layers retained and all application `.py` bytes identical
  to the predeployment fingerprint.
- Exact frozen npm `package.json`, version 0.22.2, and the same 63-file JS digest
  `3b6b074cf0be2415a049610d2908787d820b321ae68eb6d4837306dc9f5f16de`.
- Package metadata mode 0644 and successful reads by the unprivileged runtime UID.
- Runtime scanner description and MCP initialization both report 0.22.2; all
  nine tools are discoverable, with zero tool calls.
- Native quality binding and accepted source pointer match the actual image.
- Original strict MOMUS signature, freshness and full-suite checks, plus exact
  candidate/live phase, image and live source binding.
- Local/public HISTOR production health backed by PostgreSQL.
- Existing signed-log audit proving no history rewrite.

The verifier imports the unchanged production `checkEvidence` function and pinned
public key. It adds deployment identity checks without modifying release gates.
Archived receipts can correctly fail freshness validation at a later time.

## Stored issuer metadata

`/api/v1/issuer.warden` is a database observation, distinct from installed package
and live scanner metadata. It is normally refreshed by
`Crawler._register_rulesets` during crawl, remote polling with due work, or
reobservation. Startup alone does not update it. The helper records this value
honestly as `storedIssuerMatchesRuntime`; it does not start a crawl or edit the
database to make it match. Add `--require-stored-issuer` only when acceptance also
requires that persisted observation to have been refreshed.

The normal registration helper inserts immutable pattern/record blobs if absent
and upserts exactly three metadata keys in one transaction. It does not rewrite
historic observations, labels or Merkle entries. There is no separate public
registration-only CLI/API in the reviewed source; any operator maintenance for
that purpose must be separately recorded by the deployment owner.

## Rejected candidate: metadata permissions

`candidate-diagnosis.json` independently records a real packaging defect in image
`sha256:04c6683cbf8d36201359baf9322aee49c580b6f00b63ab5f59598881bc232639`
from source `231c6b0618670b408c460ce63fe8d5b1af287563`. Its new package metadata
has the intended 0.22.2 bytes but mode 0600, owned by root. The configured runtime
UID 65532 cannot read it (`EACCES`). Root can read it, which alone is insufficient
for deployment. All 63 JS files were readable with the expected digest, and all
43 HISTOR Python files matched the live predeployment fingerprint. Thus the
existing JS quality check correctly reports its own scope but cannot establish
that runtime package metadata is usable. This candidate must not be promoted.

The independent diagnosis uses only ephemeral `docker run --rm --network none
--read-only` Python metadata probes as the default user and as root, plus an
equivalent read-only probe of the currently live container. It never starts the
HISTOR application. Reproduce on the deployment host by passing the script over
SSH stdin; an optional `--image sha256:...` selects another immutable candidate:

```sh
ssh -o BatchMode=yes admin-vps python3 - \
  < docs/evidence/histor-warden-metadata-deploy-2026-10-27/verification/check-candidate.py
```

## Repaired candidate runtime acceptance

`candidate-final-runtime.json` records the independent default-user check at
19:57:19 Moscow time (16:57:19 UTC). Image
`sha256:1221f1bcc8af9081c923b9064301674d5bc4d8d0ce701cca1075a5b1355b3017`
is bound to source `4afe0243856d02b6b543b9b9559f2a286fab1a90`. All nine checks
passed: runtime UID/GID 65532 can read the exact 0.22.2 package metadata with mode
0644; all 63 JS files match; scanner description, pattern/record package names and
actual MCP initialization report 0.22.2; nine tools are discoverable with zero tool
calls. All 43 HISTOR Python files still match the predeployment fingerprint.

`check-candidate-runtime.py` reproduces this check in ephemeral network-none,
read-only containers using their configured default user. It never starts HISTOR
or invokes MOMUS. The signed native build/quality/deployment chain and subsequent
live acceptance remain separate required steps.

```sh
ssh -o BatchMode=yes admin-vps python3 - \
  --image sha256:1221f1bcc8af9081c923b9064301674d5bc4d8d0ce701cca1075a5b1355b3017 \
  --source 4afe0243856d02b6b543b9b9559f2a286fab1a90 \
  < docs/evidence/histor-warden-metadata-deploy-2026-10-27/verification/check-candidate-runtime.py
```
