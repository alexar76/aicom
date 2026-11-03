# HISTOR 0.5.3 release preparation (2026-11-01)

**Not uploaded.** PyPI has 0.5.2 (2026-10-30). Built with `./scripts/publish_pypi.sh aimarket-histor --dry-run` from
the committed tree (git `4a59de709`, clean worktree), never from the main checkout.

| Check | Result | File |
|---|---|---|
| Test suite (histor/.venv, Python 3.12) | 1,336 tests, 0 failures, 0 errors, 256 skipped | `histor-tests.xml`, `histor-tests.log` |
| Build, `twine check`, secret gate, freshness gate | passed; tree 0.5.3 ahead of PyPI 0.5.2 | `histor-dry-run.log` |
| Wheel against git | 54 files outside `.dist-info`, all byte-identical to `git show HEAD:histor/<path>` | `wheel-vs-git.txt` |
| Artifacts | wheel sha256 `62ec5920…2367`, sdist sha256 `ce47c2dc…9748` | `aimarket_histor-0.5.3-*` |
| Legacy servers, fresh venvs | 0.5.3 reads mcp.quotewise.io (21 tools) and mcp.kaiku.tech (203 tools) over 2025-06-18; published 0.5.2 gets "HTTP error did not match our request id; no downgrade" and `http-401` | `legacy-read.jsonl`, `read_legacy.py` |

Why it matters: the 0.5.2 wheel on PyPI carries the strict modern-first reader (9 "no downgrade" refusals in
`histor/mcpclient.py`), although the commits of 2026-10-30 do not: it was built from a working tree. The same reader
serves `histor tool-cost`, `/check` and self-hosted crawls, so 0.5.2 users cannot read most legacy remote servers.
Production HISTOR has run the fix since 2026-11-01 08:44:57Z.

## Upload (owner)

```bash
PYPI_API_TOKEN=pypi-… ./scripts/publish_pypi.sh aimarket-histor
```

From this worktree or any checkout whose `histor/` equals git `4a59de709` (the script builds the working tree;
compare the built wheel with `wheel-vs-git.txt`). Then `./scripts/publish_mcp_registry.sh --publish --only histor` so
the registry entry `io.github.alexar76/histor` moves from 0.5.2 to 0.5.3.
