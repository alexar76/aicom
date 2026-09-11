# Changelog

All notable changes to AI-Factory are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Tagged releases live in
[GitHub Releases](https://github.com/alexar76/aicom/releases). The version
recorded in [`pyproject.toml`](pyproject.toml) is the source of truth.

## [Unreleased]

### Added
- **`https://modelmarket.dev/mcp` — the hub's MCP gateway at the apex, with the trial tier
  reaching it.** The gateway already existed at `/ai-market/mcp`, but it sent no visitor
  header, so a stranger's first `market_invoke` met the payment wall instead of the free
  trial, and it forwarded no `source_hub`, so federated capabilities — most of the
  catalogue — answered 404. Both fixed, the identity derived **per caller** (a shared one
  would spend the whole allowance on whoever arrived first), and the endpoint advertised
  first in `mcp_servers`. Docs: [`docs/hosted-mcp-endpoint.md`](docs/hosted-mcp-endpoint.md).
  An adversarial review of the first cut found and fixed four more: the trial identity is
  attached only to **priced** capabilities (the hub consumes a trial before it reads the
  price, so a free capability was capped at three calls); a spent allowance is re-asked
  without the identity so the caller gets the **402 with a price** instead of a bare `429
  trial_quota_exhausted`; the internal invoke goes to **loopback**, because routing it
  through the public URL let nginx append its own hop and the named caller was discarded,
  putting every visitor in one rate-limit bucket; and `GET /mcp` now answers **405** to a
  stream probe rather than a JSON body the client reads as a dropped stream.
- **`scripts/payment_canary.py`** — external check that a priced capability still answers
  402, that the manifest still reports `payment_configured`, and that `/mcp` still answers
  with a per-caller trial. Probes behaviour rather than the manifest's self-report, because
  those came apart once already. Non-zero exit for cron; `--publish` writes a status JSON.
- **`scripts/deploy_hub_rebuild.sh`** — hub redeploy that copies the live container's
  environment forward, refuses to start if the payment interlock did not survive, verifies
  `/mcp` + `payment_configured`, and rolls back automatically. Payment enforcement has been
  silently dropped by a redeploy twice (2026-07-31, 2026-08-04).

### Changed
- `aimarket-mcp` HTTP mode is safe to expose publicly: per-caller trial identity via a
  context variable (stdio keeps its per-install one), client address read only from a
  declared proxy and from the rightmost hop, `AIMARKET_MCP_PUBLIC` as the explicit opt-in
  for anonymous access in production, CORS + spec-correct `GET`/`DELETE` handling, and
  uvicorn's own `proxy_headers` disabled — it trusts the leftmost, caller-written
  `X-Forwarded-For` entry, which would have made every allowance forgeable with one header.

### Changed
- **KI-1 resolved — ZK migrated to PLONK.** The `input_validity` circuit now
  uses a PLONK backend (universal setup, public Powers-of-Tau) — **no
  per-circuit trusted-setup ceremony**. Committed `verifier/Verifier.sol`
  (`PlonkVerifier`) + `verification_key.json`; new `setup_plonk.sh` (also fixes
  the dead ptau URL); `AIMARKET_ZK_BACKEND=plonk` in the prover and prod guard.
  Verified end-to-end (`snarkjs plonk verify → OK!`). Groth16 path kept optional.

### Fixed
- hub cross-hub local invoke returned 503 without a backend — `AIMARKET_SANDBOX_STUB_INVOKE`
  now also covers local invoke; hub test suite green out-of-the-box (302 passed).
- hub version aligned to `3.0.0` across `__init__`, config default, and README.
- root README: 14 satellite links repointed to standalone repos (404'd on the
  trimmed public GitHub mirror).

## [2.1.0] — 2026-06-06

Public trust & reproducibility release for the factory line.

### Added
- **Honest factory CI** (`.github/workflows/ci.yml`): backend pytest + coverage badge
  generated in Actions, strict frontend `typecheck` / `lint` / `build` (no
  `continue-on-error`), security benchmark, customer API smoke.
- **Security scan workflow** (`.github/workflows/security-scan.yml`): Bandit High
  blocks; pip-audit + npm audit reports uploaded as artifacts.
- **`scripts/quickstart.sh`** — clone → one command → Docker + demo enqueue.
- **`docs/sample-output/`** — static build replay JSON (see without running Docker).
- **`scripts/export_sample_build_replay.py`** — regenerate sample replay from code.

### Changed
- Coverage badge (`docs/badges/coverage.svg`) refreshed by CI on `main`, not
  hand-edited locally.
- `python-multipart` bumped to ≥ 0.0.18 (KI-5 partial).
- KI-3: `USE_SQLITE=true` forces `UVICORN_WORKERS=1`; crash telemetry appended to
  `uvicorn-last-crash.log`.

### Removed
- CI lint `continue-on-error` escape hatch (ROADMAP “Now”).

[Unreleased]: https://github.com/alexar76/aicom/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/alexar76/aicom/releases/tag/v2.1.0
