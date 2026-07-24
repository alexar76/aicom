# Green badges & Pages — publish runbook

How to keep **GitHub Actions badges** and **GitHub Pages** green after monorepo changes.
For agents and humans who run `push_gitea` + `publish_all_repos`.

Related: [`gitea-publishing.md`](./gitea-publishing.md) (Gitea dual-push), [`agent-github-factory-publish.md`](./agent-github-factory-publish.md) (trimmed factory mirror).

---

## Mental model

| Remote | What it is | Workflows that paint badges |
|--------|------------|-----------------------------|
| **Monorepo** (Gitea#1+#2) | Full tree including satellites | Not the public badge source |
| **`alexar76/aicom`** | Trimmed factory (satellites excluded) | `.github/workflows/factory/{ci,security-scan}.yml` → copied as `ci.yml` / `security-scan.yml` |
| **Satellite repos** | One folder → one GitHub repo | Each repo’s own `ci.yml` / `pages.yml` via `mirror_satellites.sh` |

Badges go red when the **published** tree’s CI fails — not when local Gitea is fine.
Never copy monorepo `.github/workflows/ci.yml` onto the factory mirror: it expects satellites that are not there.

---

## Happy path (factory badges)

```bash
# 0. Auth
export GH_PAT=…   # repo scope

# 1. Fix + commit in the FULL monorepo
git commit -am "…"

# 2. Push both Giteas
GITEA_FACTORY_HOST=root@modeldev.modelmarket.dev ./scripts/push_gitea_monorepo.sh

# 3. Publish trimmed factory (gitleaks runs on trimmed tree only)
./scripts/publish_all_repos.sh --factory-only

# 4. Wait for Actions
gh run list --repo alexar76/aicom --workflow=ci.yml --limit 1
gh run list --repo alexar76/aicom --workflow=security-scan.yml --limit 1
```

Factory CI source of truth:

- Edit: `.github/workflows/factory/ci.yml` and `.github/workflows/factory/security-scan.yml`
- Copy on publish: `scripts/publish_aicom_factory.sh` → `copy_factory_github_assets()`
- Deps for excluded satellites: `scripts/ci_fetch_factory_test_deps.sh` + `scripts/ci_install_factory_test_deps.sh`
- Pytest entry: `scripts/run_factory_pytest.sh` (needs `pytest-timeout` in `requirements.txt`)

---

## Happy path (one satellite)

```bash
./scripts/publish_all_repos.sh --satellite <id>   # id from scripts/satellite-map.yaml
gh run list --repo alexar76/<repo> --workflow=ci.yml --limit 1
# Pages landings (when the satellite has pages.yml):
gh run list --repo alexar76/<repo> --workflow=pages.yml --limit 1
```

Coverage / static badges with `AICOM_CI_ENFORCE_BADGE_SYNC=1` must match committed `docs/badges/*` in the monorepo **before** mirror — otherwise CI passes tests then fails on SVG drift.

---

## Do / don’t

| Do | Don’t |
|----|--------|
| Change factory workflows under `.github/workflows/factory/` | Expect monorepo `ci.yml` to work on `alexar76/aicom` |
| Run gitleaks on the **trimmed** tree (script already does) | Scan the full monorepo with `--no-git` before publish (hundreds of satellite/doc FPs) |
| Prefer `# gitleaks:allow` on known demo literals | `ALLOW_PUBLISH_WITHOUT_GITLEAKS=1` unless gitleaks is missing |
| Bump CI version pins when `package.json` / Cargo versions change | Leave hardcoded `test … version = "0.1.x"` in satellite CI |
| Pass Kantor `plan` (+ potentials) into `verify` in courses | Dual-only transport verify (fails optimization-with-proofs course) |
| Commit updated `docs/badges/coverage.svg` before re-mirror | Rely on Actions to push badge commits (many repos forbid bot pushes) |

---

## Audit all badges & Pages

Inventory: `scripts/satellite-readme-badges.yaml` + `scripts/satellite-map.yaml` + known `alexar76.github.io/*`.

Quick checks:

```bash
# Latest workflow conclusions
gh run list --repo alexar76/aicom --limit 5

# Badge SVG (prefer GitHub-native — shields.io workflow-status often 5xx)
curl -fsSL https://github.com/alexar76/aicom/actions/workflows/ci.yml/badge.svg | grep -i passing
curl -fsSL https://github.com/alexar76/aicom/actions/workflows/security-scan.yml/badge.svg | grep -i passing

# Pages landings
for p in aimarket-courses dioscuri gaia helios metis skopos theoros linked-in-profile-coach; do
  code=$(curl -fsSL -o /dev/null -w '%{http_code}' "https://alexar76.github.io/$p/")
  echo "[$code] $p"
done
```

Enable / re-dispatch Pages: `python3 scripts/ensure_github_pages.py alexar76 <repo> --dispatch-pages`.

---

## Failure cheat sheet

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Factory CI: missing `aimarket-hub` / ModuleNotFound | Monorepo workflow on trimmed tree | Use factory workflows; fetch deps scripts |
| Factory Security: gitleaks noise | Full-tree or docs/examples scanned | Critical-path stage (see factory `security-scan.yml`) |
| Publish blocked: “leaks found: 400” | Local gitleaks on whole monorepo | Use current `publish_aicom_factory.sh` (trimmed scan) |
| `unrecognized arguments: --timeout=` | Missing `pytest-timeout` | Pin in `requirements.txt` |
| `No module named pip_audit` | Gate without install | `pip install pip-audit==2.9.0` in job |
| Satellite: `coverage.svg drift` | Badge % changed | Regenerate via `scripts/generate_coverage_badge.py`, commit, re-mirror |
| Satellite: version pin `test … = "0.1.x"` fails | Manifest bumped, CI not | Update pin in `.github/workflows/ci.yml` |
| `aimarket-courses` optimization job | Kantor verify needs `plan` | Pass `solve_out["plan"]` into `kt.verify` |
| Broken image in GitHub **email** | Client not loading status icon | Ignore if Actions badge SVG is PASSING |
| CI badge broken / shields **520** | `img.shields.io/.../workflow/status` down or stale | Use GitHub-native `…/actions/workflows/<file>/badge.svg` (see `inject_readme_badges.py`). After changing badge URLs: `./scripts/publish_all_repos.sh --satellites-only` (+ `--factory-only` for `aicom`) |

---

## Order of operations (checklist)

1. Fix in monorepo; run the failing test locally if possible.
2. Commit (do **not** commit `argus/.argus-warden-scan-memory/` or secrets).
3. `push_gitea_monorepo.sh`
4. `publish_all_repos.sh --factory-only` and/or `--satellite <id>`
5. `gh run list` / badge SVG / Pages HTTP 200
6. Only then declare badges green

Auth: `GH_PAT` or `GITHUB_TOKEN`. Gitea#1 often needs `GITEA_FACTORY_HOST=root@modeldev.modelmarket.dev` when local creds are missing.
