# Roadmap

Living document. Dates are intentions, not commitments. The single source of
truth for what currently blocks a mainnet launch is
[`docs/known-issues.md`](docs/known-issues.md).

## Now — hardening & public-launch readiness

- ~~Cut a tagged `v2.1.0` GitHub release with `CHANGELOG.md` as the body.~~ **Done** (see Releases).
- ~~Clear the initial `next lint` backlog and drop `continue-on-error` from the
  frontend lint step in `.github/workflows/ci.yml`.~~ **Done** — strict lint in CI.
- ~~Commit a refreshed `web/frontend/package-lock.json` so the CI frontend job
  can return to `npm ci`.~~ **Done**
- CI coverage badge regenerated in GitHub Actions (not hand-edited).
- Sample build replay committed under `docs/sample-output/`.
- One-command quickstart: `./scripts/quickstart.sh`.

## Next — close the operator-side KI tracker

These are the items in [`docs/known-issues.md`](docs/known-issues.md). They
cannot be fixed by a code change in this repo alone; each needs operator
action and/or external services.

- **KI-1** — Groth16 trusted-setup ceremony with ≥ 3 independent contributors.
- **KI-2** — External smart-contract audit (Trail of Bits / OpenZeppelin /
  Spearbit or equivalent). All High/Critical findings resolved before mainnet.
- **KI-3** — Diagnose uvicorn supervisor crash-loop root cause under realistic
  production load (`py-spy`, `lsof`, `PROMETHEUS_MULTIPROC_DIR` snapshot).
- **KI-4** — Transfer EVM contract ownership to a 2-of-3 (or 3-of-5) Gnosis
  Safe across geographies; mirror for Solana with Squads.
- **KI-5** — Burn down the CVE backlog from `pip-audit` / `npm audit` /
  `cargo audit` until CI is clean without exceptions.

## Later — mainnet & ecosystem

- Mainnet launch of EVM/Solana payment-channel contracts under `contracts/`,
  gated on KI-1…KI-4.
- Public Immunefi bug-bounty program (see `SECURITY.md`).
- Promote the satellite subtrees (`aimarket-*`, `acex/`, `ai-service-mesh/`,
  `alien-monitor/`, `plugins/`) to fully independent repos with their own
  release cadence. Mirror tooling already lives in
  [`scripts/mirror_satellites.sh`](scripts/mirror_satellites.sh) and
  [`.github/workflows/mirror-satellites.yml`](.github/workflows/mirror-satellites.yml).
- Hosted "AI-Factory Cloud" tier (optional — the self-hosted MIT pipeline
  remains the headline product).

## How to influence the roadmap

- Issue tracker: <https://github.com/alexar76/aicom/issues>
- Security: see [`SECURITY.md`](SECURITY.md)
- Contributing: see [`CONTRIBUTING.md`](CONTRIBUTING.md)
