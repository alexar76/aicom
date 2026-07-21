# OSS distribution — agent prompts (Master setup + Release)

Use **Prompt #1** once (~3 h, idempotent). Use **Prompt #2** on every version bump (~15 min) or via `./scripts/release.sh patch`.

**Order:** agent runs #1 → #2 → thereafter human/agent runs #2 only.

**Canonical map:** [`scripts/satellite-map.yaml`](../scripts/satellite-map.yaml)

---

## Architecture (2026-05 update)

Source of truth: **private/dev monorepo `aicom`**. Public GitHub mirrors are **satellites** — subtree or filter-repo exports with preserved history where possible.

### Repo groups

| Layer | Monorepo path | Satellite repo | Notes |
|-------|---------------|----------------|-------|
| **Desktop** | `desktop-integrations/*` + `packages/` | `alexar76/aimarket-desktop` | All 8 SKUs in one Melos workspace; **no** embedded SDK |
| **SDKs** | `aimarket-sdks/` (dart, typescript, rust) | `alexar76/aimarket-sdks` | **Separate repo** — pub.dev / npm / crates.io |
| **Pulse Terminal** | `apps/pulse-terminal/` | `alexar76/pulse-terminal` | ACEX dashboard; WebSocket pricing UI |
| **Capital** | `acex/` | `alexar76/acex` | Contracts + protocol; Terminal is **not** inside acex |
| **Mesh** | `ai-service-mesh/` | `alexar76/ai-service-mesh` | Standalone orchestration layer |
| **Commerce** | `aimarket-hub/` | `alexar76/aimarket-hub` | Hub API, federation |
| **Embed** | `aimarket-widget/` | `alexar76/aimarket-widget` | Static widget + governance |
| **Protocol** | `aimarket-protocol/` | `alexar76/aimarket-protocol` | Spec + schemas |
| **Plugins** | `plugins/*` + provenance | `alexar76/aimarket-plugins` | Plugin monorepo |
| **Factory** | root minus splits | `alexar76/aicom` (optional) | Pipeline; often private |

### Language packs — colocate with app

**Do not** keep a top-level `language-packs/` folder in the satellite desktop repo.

| Monorepo (canonical) | Export target in `aimarket-desktop` |
|----------------------|-------------------------------------|
| `desktop-integrations/<app>/language-packs/*.json` | `apps/<app>/language-packs/` |

Runtime path on user machine stays: `~/Documents/AICOM/language-packs/<app-id>/`.

Example: `desktop-integrations/reputation-dashboard/language-packs/de.json` → `apps/reputation-dashboard/language-packs/de.json`.

---

## Промпт #1 — Master setup (one-time bootstrap)

```
You are setting up the AIMarket open-source distribution pipeline inside the aicom monorepo.

### Mission
Configure satellite mirroring, legal docs, CI, and release hooks so public repos stay in sync with monorepo main and tagged releases publish to registries.

### End state
1. **Satellite repos** exist on GitHub (org from existing remotes, default `alexar76`) — see mapping table below.
2. **Push to monorepo `main`** mirrors to all satellites within ~2 minutes (GitHub Actions `workflow_dispatch` + push trigger).
3. **Git tag** triggers coordinated release (group tags preferred — see Prompt #2).
4. **Idempotent** — re-run on current state → no-op, exit 0.
5. **Governance** on every public repo: LICENSE, SECURITY.md, CONTRIBUTING.md, CONTRIBUTORS.md, README.

You have GitHub credentials in the environment. Infer org/user from remotes; do not ask unless auth fails.

Read and implement `scripts/satellite-map.yaml` as the single source of truth.

### Subdir → satellite map

| Monorepo path | Satellite repo | License | Primary registry / artifact |
|---------------|----------------|---------|----------------------------|
| `desktop-integrations/` + `packages/` | `aimarket-desktop` | MIT | GitHub Releases; Flutter web builds |
| `aimarket-sdks/` (dart, typescript, rust) | `aimarket-sdks` | MIT | pub.dev, npm, crates.io |
| `apps/pulse-terminal/` | `pulse-terminal` | MIT | ghcr.io pulse-terminal, GitHub Releases |
| `acex/` | `acex` | Apache-2.0 | GitHub Releases (contracts) |
| `ai-service-mesh/` | `ai-service-mesh` | MIT | PyPI, ghcr mesh-api + mesh-dashboard |
| `aimarket-hub/` | `aimarket-hub` | Apache-2.0 | PyPI, ghcr |
| `aimarket-widget/` | `aimarket-widget` | MIT | npm / CDN static |
| `aimarket-protocol/` | `aimarket-protocol` | MIT | GitHub Release (docs) |
| `plugins/` + provenance | `aimarket-plugins` | MIT / Apache | PyPI per plugin |
| *(optional)* factory core | `aicom` | MIT | ghcr factory |

### Desktop monorepo layout (target `aimarket-desktop`)

```
aimarket-desktop/
├── apps/
│   ├── interview-prep-coach/
│   │   └── language-packs/     # de.json, fr.json, …
│   ├── reputation-dashboard/
│   │   └── language-packs/
│   └── … (8 SKUs from desktop_sku_manifest.py)
├── packages/                   # aicom_desktop_core, aicom_platform_init
├── melos.yaml
├── LICENSE  SECURITY.md  CONTRIBUTING.md  CONTRIBUTORS.md  README.md
└── .github/workflows/ci.yml
```

**SDK dependency:** apps declare `aimarket_agent` from `github:alexar76/aimarket-sdks` path `dart` — NOT vendored under `sdks/`.

**Language packs:** mirror script MUST:
1. Copy `desktop-integrations/{app}/language-packs/` → `apps/{app}/language-packs/`
2. Never emit a top-level `language-packs/` folder in the satellite

### aimarket-sdks repo (target `aimarket-sdks`)

Export entire `aimarket-sdks/` as repo root:

```
aimarket-sdks/
├── dart/           # pub.dev aimarket_agent (primary)
├── typescript/     # npm @aimarket/agent
├── rust/           # crates.io aimarket_agent
├── README.md
└── LICENSE
```

CI: `dart test`, `npm run build` (typescript), `cargo test`.

### pulse-terminal repo (target `pulse-terminal`)

Export `apps/pulse-terminal/` as repo root (Vite + React dashboard).

- Consumes `GET/WS /api/v2/capital/pricing` from factory or hub
- Docker image → ghcr.io
- Optional future: Electron wrapper over `dist/`
- Governance: MIT + SECURITY + CONTRIBUTING

### ACEX monorepo (target `acex`)

Export `acex/` as root. **Pulse Terminal is a separate satellite** — do not nest under acex/.

### Mesh repo (target `ai-service-mesh`)

Export `ai-service-mesh/` as root. Require strong MESH_* tokens in compose.

### Implementation tasks (checklist)

- [ ] `scripts/publish_aicom_factory.sh` — push **trimmed** aicom (excludes all satellites; deletes them on remote)
- [ ] `scripts/publish_satellite.sh` — push one satellite subtree to its own repo
- [ ] `scripts/aicom_publish_config.py` — exclude list from `satellite-map.yaml`
- [ ] Implement `scripts/mirror_satellites.sh` from `satellite-map.yaml`
- [ ] `.github/workflows/mirror-satellites.yml` — matrix all satellites
- [ ] `.github/workflows/release.yml` — group tags
- [ ] `scripts/release.sh patch|minor|major`
- [ ] `scripts/bootstrap_repo_legal_docs.py` — add kinds: desktop-monorepo, sdks, pulse-terminal
- [ ] Secrets: GH_PAT, PYPI_TOKEN, NPM_TOKEN, PUB_CREDENTIALS, GHCR_TOKEN, CRATES_TOKEN

### Do not

- Split each desktop SKU into its own GitHub repo
- Embed aimarket-sdks inside aimarket-desktop
- Put Pulse Terminal inside acex/ or aimarket-desktop/
- Ship default MESH_* tokens or API keys

When done, print: satellite URLs, workflow paths, command for Prompt #2.
```

---

## Промпт #2 — Idempotent release (repeatable)

```
You are running an AIMarket **idempotent release** from the aicom monorepo.

Read `scripts/satellite-map.yaml` for the authoritative satellite list.

### Release groups (independent tags recommended)

| Group | Version files | Satellite | Tag example |
|-------|---------------|-----------|-------------|
| Desktop | `desktop-integrations/*/pubspec.yaml`, melos | aimarket-desktop | `desktop-vX.Y.Z` |
| SDKs | `aimarket-sdks/dart/pubspec.yaml`, ts package.json, rust Cargo.toml | aimarket-sdks | `sdks-vX.Y.Z` |
| Pulse Terminal | `apps/pulse-terminal/package.json` | pulse-terminal | `pulse-vX.Y.Z` |
| ACEX | acex contracts / CHANGELOG | acex | `acex-vX.Y.Z` |
| Mesh | mesh backend pyproject, frontend package.json | ai-service-mesh | `mesh-vX.Y.Z` |
| Hub | aimarket-hub pyproject | aimarket-hub | `hub-vX.Y.Z` |
| Widget | widget.js semver comment | aimarket-widget | `widget-vX.Y.Z` |
| Plugins | plugins/*/pyproject.toml | aimarket-plugins | `plugins-vX.Y.Z` |
| Protocol | spec version | aimarket-protocol | `protocol-vX.Y.Z` |
| Factory | docker / VERSION | aicom | `factory-vX.Y.Z` |

### Diff-based skip

Only release groups with changed paths since last group tag.

Path hints:
- Desktop: `desktop-integrations/`, `desktop-integrations/*/language-packs/`
- SDKs: `aimarket-sdks/`
- Pulse: `apps/pulse-terminal/`
- ACEX: `acex/` (exclude apps/pulse-terminal)

### Steps

1. Fail if `scripts/satellite-map.yaml` or mirror workflow missing (“run Prompt #1”).
2. For each affected group: bump versions, run targeted tests, update CHANGELOG snippet.
3. Commit `chore(release): …`
4. Push group tag(s) → CI mirrors + publishes registries.
5. Verify satellites updated within 5 min.

### Tests by group

| Group | Command |
|-------|---------|
| Desktop | `flutter analyze` (matrix sample); verify language-packs under each app |
| SDKs | `cd aimarket-sdks/dart && dart test` |
| Pulse | `cd apps/pulse-terminal && npm run build` |
| ACEX | `forge test` + `pytest tests/test_acex_*.py` |
| Mesh | `pytest ai-service-mesh/backend/tests/` |
| Hub | `pytest aimarket-hub/tests/test_api.py` |

### Governance gate

Each touched satellite must ship LICENSE, SECURITY.md, CONTRIBUTING.md, CONTRIBUTORS.md.

### Output

Markdown release notes grouped by: Desktop, SDKs, Pulse Terminal, ACEX, Mesh, Hub, Widget, Plugins, Protocol.
```

---

## Quick reference — monorepo paths

| Path | Role |
|------|------|
| `desktop-integrations/*` | 8 Flutter desktop/web SKUs |
| `desktop-integrations/<app>/language-packs/` | Per-app i18n JSON (canonical) |
| `aimarket-sdks/` | Dart + TypeScript + Rust SDKs |
| `apps/pulse-terminal/` | ACEX Pulse Terminal UI |
| `acex/` | Agent Capital Exchange |
| `ai-service-mesh/` | Mesh orchestration |
| `aimarket-hub/` | Commerce hub |
| `aimarket-widget/` | Embeddable widget |
| `aimarket-protocol/` | Protocol spec |
| `plugins/` | Hub plugins |

## Existing helpers

| Script | Purpose |
|--------|---------|
| `scripts/publish_aicom_factory.sh` | Push factory aicom **without** satellite folders |
| `scripts/publish_satellite.sh` | Push one satellite to its own remote |
| `scripts/aicom_publish_config.py` | Exclude list for factory rsync |
| `scripts/bootstrap_repo_legal_docs.py` | LICENSE + SECURITY + CONTRIBUTORS |
| `scripts/publish_aimarket_widget_standalone.sh` | Widget-only sync |
| `scripts/bootstrap_desktop_localization_docs.py` | Per-app localization docs |
| `scripts/desktop_sku_manifest.py` | 8 SKU list |

---

*When adding SKUs or satellites: edit `scripts/satellite-map.yaml` and this doc.*
