## AI-Factory (aicom) v0.1.0 — public trimmed factory

**What works today**
- Trimmed open-source factory mirror (satellite folders excluded)
- Core pipeline, orchestrator, agents, web admin, pytest CI
- Ecosystem landing via GitHub Pages workflow
- Publish scripts and satellite map in-repo

**Unstable / may change**
- What ships in factory vs separate satellites (`scripts/satellite-map.yaml`)
- Local `data/` runtime paths — never commit secrets; see `.gitignore`

**Not in this release**
- One-click cloud deploy; use docs + `docker-compose` / your own infra
- Bundled copies of aimarket-hub, acex, desktop apps (separate repos)
