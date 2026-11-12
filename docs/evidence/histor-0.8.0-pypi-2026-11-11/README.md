# HISTOR 0.8.0 for PyPI: what was checked

Built on 2026-11-11 from commit `25e945ec1` (branch `claude/release-histor-0.8.0`, cut from main `89ed03abf`),
with `scripts/publish_pypi.sh aimarket-histor --dry-run`, Python 3.12.13, hatchling 1.33.0. Not uploaded.

| File | SHA-256 |
|---|---|
| `aimarket_histor-0.8.0-py3-none-any.whl` | `d0f7c8452f4b2be98b80b3c06cf0fea5fb4f3e1865da792d67a8c972b5d5d4b2` |
| `aimarket_histor-0.8.0.tar.gz` | `40b98dd4ef79975b3e811adf52345aae21a47f825eae968bbaf0cc4c33cf2e12` |

The files are in the main checkout at `artifacts/pypi-release-histor-0.8.0-2026-11-11/` (git-ignored), with
`SHA256SUMS` and `build.log`.

**Publication confirmed 2026-11-12.** The [PyPI release files](https://pypi.org/project/aimarket-histor/0.8.0/#files)
record uploads of both files on 2026-11-11 and show the two SHA-256 values above. The build checks below
describe the pre-upload run.

## Why this release

PyPI's newest HISTOR is 0.7.0 (2026-11-08). It has no `histor revision` command, so the check that our
OWASP MCPSTG #21 comment points readers to (`histor revision verify`) only worked from the repository tip. 0.8.0 is
the first release with it. It also ships the HISTOR side of the signed-revision log: `signedRevision` on `/check`,
the revision tree (migration 022, `histor revision-sync`) and the SUPP-06 (e)/(f) monitor. The full list is the
`## 0.8.0` section of `histor/CHANGELOG.md`.

The seven satellite Sign workflows now install `aimarket-histor[sigstore]==0.8.0` from PyPI instead of the unpinned
tip of `alexar76/histor`. Merge this branch only after 0.8.0 is on PyPI, or those workflows cannot install.

## Checks

- **Files equal git.** All 64 files of the wheel and all 295 files of the sdist (except generated `PKG-INFO` and
  `.dist-info`) are byte-identical to `git show 25e945ec1:histor/<path>`. twine check, the secret gate and the
  freshness gate passed (`build.log`).
- **Tests.** `uv run --frozen --all-extras pytest` on the release tree: 1,244 passed, 314 skipped, 0 failed.
  - An earlier run had two failures: `test_invalid_stdio_cursor_never_marks_listing_complete[0]` and
    `test_toolcost_client_and_histor_server_interoperate_modern_without_initialize`. Both pass when run alone.
  - The second also fails the same way on an untouched copy of main `89ed03abf` on its first, cold run. The client
    gives `server/discover` at most a quarter of its 20 s deadline. A cold `histor mcp` start with an empty data
    directory took 5.14 s once (1.34 s warm), so the client fell back to `initialize`. This is a timing limit in the
    test, not a protocol fault: with metadata, the server answers `server/discover` in 0.3–0.7 s.
- **As an outsider.** The wheel was installed with `[sigstore]` in a new Python 3.12 venv:
  - `histor revision --help` lists `build, envelope, record, verify`; PyPI 0.7.0 prints usage without `revision`.
  - `histor revision verify` on `revisions/1.json` from the `manifest-revisions` branch of `alexar76/histor`, with
    the expected workflow identity and `--stdio "uvx --from aimarket-histor==0.7.0 aimarket-histor"`, gave
    `"ok": true`, logIndex `3803861704`. Against production Sigstore, and with `--offline` once the trust root is
    cached.
  - The MCP server of this wheel (`aimarket-histor`) serves the same three tools as 0.7.0. `histor revision build
    --if-changed` against index revision 1 printed `unchanged: sha256:4789b5c9…c842 is revision 1`. So the existing
    signed revision covers 0.8.0, and running the Sign workflow for 0.8.0 adds no Rekor entry.

## After upload

1. `pip download aimarket-histor==0.8.0 --no-deps` and compare both SHA-256 values with the table above.
2. `./scripts/publish_mcp_registry.sh --publish --only histor` moves `io.github.alexar76/histor` to 0.8.0.
3. Merge this branch into main, then sync the mirrors (`histor` and the seven satellites with Sign workflows).
