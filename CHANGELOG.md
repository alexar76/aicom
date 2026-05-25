# Changelog

All notable changes to AI-Factory are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Tagged releases live in
[GitHub Releases](https://github.com/alexar76/aicom/releases). The version
recorded in [`pyproject.toml`](pyproject.toml) is the source of truth.

## [Unreleased]

### Added
- Public `ROADMAP.md` summarising the path to mainnet.
- Pre-mainnet banner and `status: pre-mainnet` badge in `README.md` linking
  to `docs/known-issues.md`.
- `web/frontend` ESLint config (`eslint-config-next`) and `typecheck` /
  `lint` npm scripts.
- CI: frontend `tsc --noEmit` and `next lint` steps in `frontend-build`
  (`continue-on-error` on lint until the initial backlog is cleared).

### Changed
- `SECURITY.md` no longer promises a live Immunefi program before mainnet; bug
  bounty table is marked as a target structure.
- CI `backend-tests` now commits the regenerated coverage badge back to
  `main` (`[skip ci]`) so the README badge stays fresh between releases.

### Removed
- Internal audit/strategy notes (`plans/`, `EXTRACTION_REPORT.md`) moved out of
  the public tree to `.internal/` (gitignored). No code paths reference them.

### Security
- Removed a stray hardcoded production host IP from
  `tests/test_sandbox_localhost_rewrite.py` (test-only, never executed against
  the real host, but visible in clone).
- Dropped the embedded access token from the local `origin` remote URL.

## [2.1.0] — 2026-05

First public-facing release of the v2.1 line. Snapshot of the platform state
prior to the cleanup above. Highlights from the git history:

- Multi-agent pipeline (Analyst → PM → Architect → Developer → QA → Security
  → DevOps → Marketing → Sales → Evolution) with conditional Design-critic
  and Hardening gates.
- Discovery pre-pipeline (`director/discovery_pipeline.py`) and ranked-ideas
  ingestion.
- Storefront, admin panel, Prometheus/Grafana, sandbox previews.
- ZK Groth16 backend skeleton, EVM/Solana payment-channel contracts,
  multisig ownership transfer tooling (`scripts/transfer_contract_ownership`).
- Audit remediation pass: Vault integration, OIDC/SSO, ZK ceremony scripts,
  security CI (Bandit, pip-audit, Slither, Dependabot).
- Risk mitigation: PostgreSQL CI path, scoped ruff/mypy, EventBus queues,
  real LLM token accounting, CostGuard.
- Alien Monitor 3D ecosystem visualiser deployed at `/monitor/`.

Known operator-side items that remain open and block a mainnet launch are
tracked in [`docs/known-issues.md`](docs/known-issues.md) (KI-1…KI-5).

[Unreleased]: https://github.com/alexar76/aicom/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/alexar76/aicom/releases/tag/v2.1.0
