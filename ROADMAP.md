# Roadmap

Living document. Dates are intentions, not commitments. The single source of truth for
what currently blocks a **public DeFi launch** is [`docs/known-issues.md`](docs/known-issues.md).
For the **pet-project / self-host** scope see [`docs/pet-project-trust.md`](docs/pet-project-trust.md).
For **external scorecard validation + action matrix** see
[`docs/ecosystem-maturity-review.en.md`](docs/ecosystem-maturity-review.en.md)
([RU](docs/ecosystem-maturity-review.ru.md)).

## Now — hardening & public-launch readiness

- ~~Cut a tagged `v2.1.0` GitHub release with `CHANGELOG.md` as the body.~~ **Done**
- ~~Strict frontend lint in CI.~~ **Done**
- ~~Production stack overlay (`docker-compose.prod.yml`).~~ **Done**
- ~~pip-audit real gate (ollama exceptions only).~~ **Done**
- ~~FastAPI/starlette + pytest 9 bump.~~ **Done**
- ~~Redis pipeline wake queue.~~ **Done**
- ~~Hub: O-1 quorum API, O-4 auto-crawl slash pull, supply stake prod guards.~~ **Done**
- ~~React 19 Playwright e2e (recharts + framer-motion).~~ **Done**
- ~~Prod misconfig smoke CI + pip-audit gate script.~~ **Done**
- CI coverage badge regenerated in GitHub Actions (not hand-edited).
- Sample build replay committed under `docs/sample-output/`.
- One-command quickstart: `./scripts/quickstart.sh`.

## Next — operator-side (pet project, no paid audit)

| Item | Action | Script |
|------|--------|--------|
| **KI-3** | Soak test prod stack | `./scripts/load_test_factory.sh` |
| **KI-7** | Factory MVP honesty / minimal pipeline | [`docs/factory-pipeline-profiles.md`](docs/factory-pipeline-profiles.md) |
| **KI-8** | Metis distributed soak + adversarial bench | [`metis/docs/en/MATURITY.md`](metis/docs/en/MATURITY.md) |
| **KI-9** | ARGUS WARDEN red-team corpus | [`argus/docs/security-warden.md`](argus/docs/security-warden.md) §Limitations |
| **KI-10** | Hub federation drill + external peer | [`aimarket-hub/docs/MATURITY.md`](aimarket-hub/docs/MATURITY.md) |
| **KI-4** | Multisig owner | `./scripts/multisig_transfer_runbook.sh` |
| **KI-2** | External audit | **Waived** — Slither + [`docs/pet-project-trust.md`](docs/pet-project-trust.md) |
| **O-1** | Set oracle authorities | `AIMARKET_ORACLE_AUTHORITIES` in hub env |
| **O-1** | Dispute filing API | `POST /reputation/disputes` (consumer-signed or admin) |
| Checklist | Pre-mainnet self-check | `./scripts/pre_mainnet_checklist.sh` |

## Later — mainnet & ecosystem

- Optional Immunefi bug-bounty program (see `SECURITY.md`).
- Satellite subtrees publish cadence via [`scripts/publish_all_repos.sh`](scripts/publish_all_repos.sh).
- Hosted "AI-Factory Cloud" tier (optional).

## How to influence the roadmap

- Issue tracker: <https://github.com/alexar76/aicom/issues>
- Security: see [`SECURITY.md`](SECURITY.md)
- Contributing: see [`CONTRIBUTING.md`](CONTRIBUTING.md)
