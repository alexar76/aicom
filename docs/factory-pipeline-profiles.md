# AI-Factory pipeline profiles

The default Factory stack runs **many conditional stages** (PM spec gates, architect,
developer, QA, security, deploy, marketing, director integration). That is powerful for
showcase builds but **over-engineered** for a simple landing page — a fair external critique.

This doc defines **profiles** operators can aim for. Configuration lives in
`config/fragments/*.yaml` merged via Admin overlay.

---

## Profiles

| Profile | Stages (typical) | Best for | Honest output tier |
|---------|------------------|----------|-------------------|
| **minimal** | PM (light) → developer → deploy | Single-page landing, demo hackathon | **MVP storefront** — real deploy, limited backend |
| **standard** | PM → architect → developer → QA → deploy | SaaS-style web app | **MVP+** — more structure, still not enterprise |
| **full** (default image) | All agents + quality gates + security + marketing + director | Ecosystem showcase, SplitEasy-class demos | **Showcase MVP** — see [`sample-output/`](sample-output/) |

---

## Why full pipeline feels heavy

- **12 config fragments** (`config/fragments/00-core.yaml` … `100-storefront.yaml`)
- **Director integration** can re-queue tasks on SLO alerts
- **Quality gates** on PM spec (structure, methodology) — pipeline pauses on reject
- **Conditional paths** per product type (storefront readiness, crypto overlay)

For pet-project/self-host, prefer **minimal** unless you need the demo narrative.

---

## Tuning toward minimal (operator)

1. Admin → Settings or edit overlay YAML:
   - Lower agent fan-out in `40-agents.yaml` priorities (skip marketing/sales if unused)
   - `orchestrator.enable_director_integration: false` for simpler runs
2. Use `./scripts/quickstart.sh` for a bounded demo path
3. Run **KI-3** load test only when running **full** profile in production:
   `./scripts/load_test_factory.sh --duration 600 --concurrency 10`

---

## Production readiness (honest)

Not complete until:

- **KI-3** — uvicorn worker root cause under load
- **KI-2** — external contract audit (waived for pet project; see [`pet-project-trust.md`](pet-project-trust.md))
- **KI-4** — multisig on escrow contracts
- **KI-7** — Factory production maturity tracker in [`known-issues.md`](known-issues.md)

---

## Sample outputs

Static artifacts in [`docs/sample-output/`](sample-output/) are **MVP-tier examples** —
same JSON shape as live build replay, not proof of complex shipped software.

Regenerate: `python scripts/export_sample_build_replay.py`
