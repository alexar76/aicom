# HISTOR 0.5.0 release validation — 2026-10-27

Prepared `aimarket-histor` 0.5.0 from source recorded in commit
`0f3be96e391c4d3ac19c21ec7c7fa4aecb860ad9`. The artifact payload is also tied
directly to current source bytes in `source-files.sha256.json`; no commit identity
is inferred from the contents of a wheel.

This directory records local validation and candidate artifacts. Registry upload
and Gitea push are handled separately by the parent release task. No GitHub write
was performed by this validation task.

## Release contents

- Version metadata: `pyproject.toml`, `histor.__version__` and `uv.lock` agree on
  0.5.0. The former Unreleased changelog section is dated 2026-10-27.
- Existing functionality in this release includes MCP 2026-07-28 discovery and
  request metadata, preserved legacy initialization, observation provenance,
  typed schema differences and offline personal upgrade reports in English,
  Russian, Spanish, French and Chinese. English is the default.
- Added `/examples` to the sdist include list. The sdist now contains all 19
  upgrade-brief fixture/walkthrough/verifier files, three existing tool-cost
  example files and five upgrade-brief guides.
- Wheel and sdist explicitly use Core Metadata 2.4. The installed Hatchling 1.32.4
  defaults to 2.5, which Twine 6.2.0 rejects; 2.4 artifacts pass strict validation.
  Runtime dependencies were not changed.

## Results

| Check | Result | Evidence |
| --- | --- | --- |
| Ruff on package, tests, sandbox and example verifier | Passed | `ruff.log` |
| Lock consistency, offline | Passed | `lock-check.log` |
| Non-integration suite | 1089 passed, one optional-tokenizer test initially skipped | `pytest-unit.log`, `pytest-unit.xml` |
| Entire tool-cost suite after installing locked tiktoken 0.14.0 | 18 passed, including the initially skipped test | `pytest-toolcost.log`, `pytest-toolcost.xml` |
| Integration suite with real sockets, WARDEN sidecar and PostgreSQL | 12 passed; no skips | `pytest-integration.log`, `pytest-integration.xml` |
| Wheel and sdist build | Passed | `build.log` |
| Strict Twine check of both final artifacts | Passed | `twine-check.log` |
| Exact distribution secret inspection | All three archives passed | `secrets-wheel.log`, `secrets-sdist.log`, `secrets-rebuilt-wheel.log` |
| Source-to-artifact comparison | Every source byte matched; 245 sdist and 53 wheel members | `artifact-validation.log`, `source-files.sha256.json` |
| Sdist rebuild, offline and outside checkout | Byte-identical wheel | `sdist-rebuild.log`, `artifact-manifest.json` |
| Installed wheel, clean environment | Five languages, repeatable findings/checklists, English default | `consumer-smoke.log`, `consumer-reports/` |
| Installed MCP startup and discovery | Modern 2026-07-28, three tools, version 0.5.0 | `consumer-smoke.log` |
| Runtime dependency compatibility | 22 packages compatible | `consumer-pip-check.log`, `consumer-runtime.txt` |
| Packaged standard-library walkthrough | All five languages and 12 offline CLI runs passed | `sdist-example.log` |
| Ruff on evidence scripts | Passed | `ruff-evidence.log` |

Across the original suites and the targeted tokenizer follow-up, all 1102 source
tests were exercised successfully; the follow-up repeats 17 already passing
tool-cost tests. There are no remaining untested skips. Source tests emitted one
FastAPI/Starlette deprecation warning about using the existing httpx TestClient;
it did not fail validation.

PostgreSQL 18.3 ran in a dedicated temporary trust-auth cluster, bound to loopback
port 65437, with synthetic database `histor_release`. The test cluster was stopped
after validation (`postgres-stop.log`). No production database was used.

## Artifacts and reproducibility

The two candidate upload files are archived under `artifacts/`. Their SHA256
digests are recorded in `artifact-manifest.json`:

| File | SHA256 |
| --- | --- |
| `aimarket_histor-0.5.0-py3-none-any.whl` | `bae7ec5b50582f3c2fda8eaa69814dec046cfac9ec011a424c2cbe6fe1648a99` |
| `aimarket_histor-0.5.0.tar.gz` | `1d912338b46b0cadc4176a09715d7b03f12c22c41cebf9956be621189ca4266c` |

The wheel has only the `histor` import package and distribution metadata. The
sdist contains only HISTOR-owned files: no monorepo evidence, local data,
virtualenv, `node_modules`, keys or foreign project directories. The packaged
`.gitignore` is the exact package-owned `histor/.gitignore`.

The release tools virtualenv is ignored and local to this evidence directory:
`tools/.venv/bin/python -m twine`. Tool versions are in `release-tools.json`.
No global Python environment was installed or upgraded. Dependency/build
downloads used `/private/tmp/histor-release-uv-cache-20261027`.

The following are original session commands, recorded for traceability. Their
temporary directories and cached build environment existed during the run; use
the complete setup below when starting from a fresh checkout.

```sh
UV_CACHE_DIR=/private/tmp/histor-release-uv-cache-20261027 uv build histor \
  --out-dir docs/evidence/histor-warden-release-2026-10-27/histor/dist \
  --no-create-gitignore

docs/evidence/histor-warden-release-2026-10-27/histor/tools/.venv/bin/python \
  -m twine check --strict \
  docs/evidence/histor-warden-release-2026-10-27/histor/dist/*

UV_CACHE_DIR=/private/tmp/histor-release-uv-cache-20261027 uv build --wheel --offline \
  /private/tmp/histor-release-sdist-050-20261027/aimarket_histor-0.5.0 \
  --out-dir docs/evidence/histor-warden-release-2026-10-27/histor/sdist-rebuild \
  --no-create-gitignore

/private/tmp/histor-release-consumer-050-20261027/bin/python -I \
  docs/evidence/histor-warden-release-2026-10-27/histor/verify_installed_wheel.py \
  --source /private/tmp/histor-release-sdist-050-20261027/aimarket_histor-0.5.0 \
  --out-dir /private/tmp/histor-release-consumer-050-20261027/smoke
```

The clean consumer is a fresh virtualenv with the final wheel and declared runtime
dependencies, with no source checkout on its import path. Its commands use Python
`-I`, run outside the checkout and clear inherited HISTOR/AIMARKET configuration.
MCP smoke uses a temporary empty local log, reads discovery and tool definitions,
and makes no tool calls or external requests. Only the generated report files
were copied into evidence; local database/signing state was left in temporary
storage. Reproduction scripts intentionally do not publish anything.

## Complete clean-checkout rerun

Requires Python 3.11 or newer with `venv`/`pip`, a POSIX shell and access to public
PyPI for setup. Run from the workspace root. The temporary work directory can be
changed; all extracted files, virtualenvs, rebuilt output and fresh reports stay
there. The archived artifacts and original manifests are read-only inputs.
The recorded backend version is pinned so the rebuilt wheel can be compared
byte-for-byte. Nothing is uploaded.

```sh
histor_release_evidence="$PWD/docs/evidence/histor-warden-release-2026-10-27/histor"
histor_release_work="$(mktemp -d "${TMPDIR:-/tmp}/histor-release-rerun.XXXXXX")"
python3 -c 'import sys; assert sys.version_info >= (3, 11)'
python3 -m venv "$histor_release_work/tools"
"$histor_release_work/tools/bin/python" -m pip install --index-url https://pypi.org/simple \
  build==1.6.1 hatchling==1.32.4 packaging==26.3 twine==6.2.0

"$histor_release_work/tools/bin/python" -I "$histor_release_evidence/verify_artifacts.py"
"$histor_release_work/tools/bin/python" -m twine check --strict \
  "$histor_release_evidence/artifacts/aimarket_histor-0.5.0-py3-none-any.whl" \
  "$histor_release_evidence/artifacts/aimarket_histor-0.5.0.tar.gz"

python3 - "$histor_release_evidence" "$histor_release_work" <<'PY'
import sys, tarfile
from pathlib import Path, PurePosixPath
evidence, work = map(Path, sys.argv[1:])
with tarfile.open(evidence / 'artifacts/aimarket_histor-0.5.0.tar.gz') as archive:
    for item in archive:
        path = PurePosixPath(item.name)
        assert item.isfile() and not path.is_absolute() and '..' not in path.parts
        assert path.parts[0] == 'aimarket_histor-0.5.0'
        target = work / 'source' / item.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.extractfile(item).read())
        target.chmod(item.mode & 0o777)
lines = (evidence / 'consumer-runtime.txt').read_text().splitlines()
(work / 'runtime.txt').write_text('\n'.join(line for line in lines
    if line and not line.startswith('aimarket-histor')) + '\n')
PY

"$histor_release_work/tools/bin/python" -m build --no-isolation --wheel \
  --outdir "$histor_release_work/rebuilt" \
  "$histor_release_work/source/aimarket_histor-0.5.0"
"$histor_release_work/tools/bin/python" -I "$histor_release_evidence/verify_artifacts.py" \
  --rebuilt-wheel "$histor_release_work/rebuilt/aimarket_histor-0.5.0-py3-none-any.whl"

python3 -m venv "$histor_release_work/consumer"
"$histor_release_work/consumer/bin/python" -m pip install --index-url https://pypi.org/simple \
  -r "$histor_release_work/runtime.txt" \
  "$histor_release_evidence/artifacts/aimarket_histor-0.5.0-py3-none-any.whl"
"$histor_release_work/consumer/bin/python" -m pip check
"$histor_release_work/consumer/bin/python" -I "$histor_release_evidence/verify_installed_wheel.py" \
  --source "$histor_release_work/source/aimarket_histor-0.5.0" \
  --out-dir "$histor_release_work/reports"
"$histor_release_work/consumer/bin/python" -I \
  "$histor_release_work/source/aimarket_histor-0.5.0/examples/upgrade-brief/verify.py" \
  --out-dir "$histor_release_work/walkthrough-reports"
```

`verify_artifacts.py` defaults to `artifacts/`, verifies the frozen artifact and
source hashes, and prints its result without changing any file. Use
`--artifact-dir` and `--source-root` for relocated inputs. `--rebuilt-wheel` is
optional: without it, rebuild identity is reported as untested rather than
inferred. `verify_installed_wheel.py` takes explicit extracted-source and report
paths; no session-specific temporary path is required.

To repeat the separately observed public-wheel smoke, create another clean
consumer using the same recorded runtime requirements:

```sh
python3 -m venv "$histor_release_work/public-consumer"
"$histor_release_work/public-consumer/bin/python" -m pip install --index-url https://pypi.org/simple \
  -r "$histor_release_work/runtime.txt" \
  "$histor_release_evidence/registry-observation/aimarket_histor-0.5.0-py3-none-any.whl"
"$histor_release_work/public-consumer/bin/python" -I "$histor_release_evidence/verify_installed_wheel.py" \
  --source "$histor_release_work/source/aimarket_histor-0.5.0" \
  --out-dir "$histor_release_work/public-reports"
```

See `registry-observation/README.md` for the distinct public hash and the exact
builder-metadata difference. The original candidate hash is preserved.
