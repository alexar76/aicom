# aimarket-hub 3.22.3 — built 2026-11-26, PyPI = colleague step §176

PyPI has 3.22.2 (uploaded 2026-11-26 17:19Z; rebuilt, contents equal to artifacts/hub-3.22.2-release-2026-11-26 file
for file). 3.22.3 adds one change, main ee9b8835e: validity in HTTP — Cache-Control max-age + stale-if-error and a weak
ETag (304 on If-None-Match) on the signed catalogue and both discovery documents; a peer's stated period
(max-age + stale-if-error) shortens how long its entries are served; migration 073 (`capabilities.serve_until`).
Details and the live rollout (six hubs, 17:37–17:40Z): ../hub-http-validity-2026-11-26/README.md.

Built with `uv build` from `git archive ee9b8835e aimarket-hub` (clean tree). Sums: wheels/SHA256SUMS.

## Checks

- `twine check`: both PASSED.
- The wheel's 231 package sources equal the commit byte for byte (230 + the new http_validity.py); the 6 `static/ui`
  files are generated at build, as before.
- Fresh Python 3.12 venv: `aimarket_hub.__version__` 3.22.3; `http_validity.stated_period` present.
- Full hub suite on the change: 4397 passed, 2 failed — the two failing since 3.22.0.
