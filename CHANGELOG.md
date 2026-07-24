# Changelog

All notable changes to AI-Factory are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Tagged releases live in
[GitHub Releases](https://github.com/alexar76/aicom/releases). The version
recorded in [`pyproject.toml`](pyproject.toml) is the source of truth.

## [Unreleased]

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
