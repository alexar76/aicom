=== GITHUB_HOUSE_CONTRACT (industry OSS bar — binding) ===

Ship the product like a well-run GitHub house (gaia / atlas / momus class):
discoverable README, green CI badges, a real release, tests that prove the
spec, and docs in **English plus the product locale**.

This is **not** marketing fluff. Missing files fail QA.

## Languages

- **UI / landing copy:** `architecture.content_language` only (LANGUAGE_SYSTEM).
- **Docs are bilingual:** always English (`README.md`, `docs/en.md`). If
  `content_language` is not `en`, also `README.<code>.md` and `docs/<code>.md`
  (example: `ru` → `README.ru.md`, `docs/ru.md`). Cross-link at the top:
  `> 🌐 [English](README.md) · [Русский](README.ru.md)`.
- File paths, JSON keys, CI job names, and badge `alt` stay English.

## README (root)

`README.md` is the GitHub landing page. Required shape:

1. **Title + one-line tagline** (product name from spec).
2. **Language switcher** when a second README exists.
3. **Badge row** between `<!-- aicom-readme-badges -->` and
   `<!-- /aicom-readme-badges -->`. Commit SVG shields under `docs/badges/`
   (`ci.svg`, `coverage.svg`, `license.svg`, plus `tests.svg` when you know
   a count). Do **not** use img.shields.io workflow-status URLs (they 5xx).
   After a real GitHub remote exists, CI may add a GitHub-native
   `…/actions/workflows/ci.yml/badge.svg` next to the local SVG.
4. **Hero** — one visual above the fold:
   - Browser UI / landing: original SVG still at `docs/gallery/hero.svg`
     (same mood as `ui_experience`; not a grey rectangle).
   - CLI / API-only: mermaid architecture (or sequence) in the README.
5. **Gallery** (when there is a UI): 2–4 stills in `docs/gallery/`
   (`01.svg`… ) with a markdown table of caption + file. Skip only for
   pure CLI with no screens.
6. **What it is / who it is for / what it is not** (honest boundaries).
7. **Quick start** — copy-pasteable install + run from repo root.
8. **Tests** — the exact commands from `test_commands`.
9. **Docs index** — links to `docs/en.md` and the locale twin.
10. **License** — default MIT unless the spec names another OSI license.
    Ship `LICENSE`.

Localized `README.<code>.md` mirrors the same sections; do not leave it as
a stub that says “see English”.

## Documentation

- `docs/en.md` — operator/developer guide: architecture, env vars, run,
  test, troubleshoot. Not a paste of the README.
- `docs/<code>.md` — the same guide in the product locale when locale ≠ `en`.
- **Product packaging (binding for full_software with a UI):**
  - `docs/admin.md` — deploy, secrets/env, funding, republish, failure table.
  - `docs/user-guide.md` — short end-user / operator UI walkthrough.
  - `docs/use-cases.md` — who it is for, who it is not, 2–3 concrete journeys.
  - README **Docs** section must link all three (plus `docs/en.md`).
  - Badge files under `docs/badges/*.svg` must **exist on disk** (not only be
    linked from README). Dead badge links fail QA.
  - Gallery table must embed images (`![…](docs/gallery/…)`) — bare paths
    without markdown image syntax fail QA.
- `CHANGELOG.md` — Keep a Changelog, starts with `## [0.1.0] — YYYY-MM-DD`.
- `SECURITY.md` — how to report vulns (no live secrets).
- `CONTRIBUTING.md` — how to run tests, open PRs, and what not to commit
  (secrets, `node_modules/`, `.venv/`). **Required** for catalog publish.

## Tests (coverage)

**full_software** — test pyramid is binding (unit → integration → UI/e2e):

- Unit tests for core logic (no HTTP server required).
- One realistic API/behavior test (happy path + one error/edge).
- UI e2e last when there is a browser surface (Playwright or equivalent).
- CI must collect coverage. Target **≥70%** line coverage on first-party
  application code; **fail the job below 60%**. Do not game coverage with
  empty tests.
- Landings: at least a smoke test (html `lang`, in-page CTA/anchors exist).

Put tests in conventional paths (`tests/`, `*_test.py`, `*.test.ts`).

## CI and release

Ship:

- `.github/workflows/ci.yml` — checkout, install, run `test_commands`,
  coverage with **`--cov-fail-under=60`** (or the stack equivalent).
  Optional lint. Write `docs/badges/coverage.svg` when a generator exists;
  otherwise keep an honest placeholder SVG (label `#555`, passing `#4c1`).
- `.github/workflows/release.yml` — `on.push.tags: ['v*']`, then
  **`softprops/action-gh-release@v2`** with `generate_release_notes: true`
  (GitHub Release). Soft for marketing_landing; required for **full_software**.
- Version **0.1.0** in the package manifest (`pyproject.toml` /
  `package.json` / `VERSION`). First CHANGELOG heading `## [0.1.0]`.

DevOps must describe the same lifecycle in `lifecycle_release`
(semver, tag → Release, rollback = previous tag).

## Copy shapes (fill in — do not invent a thinner README)

`README.md` (English). Localized twin uses the same sections:

```markdown
# {Product}
> one-line tagline

> 🌐 [English](README.md) · [{Locale label}](README.{code}.md)

<!-- aicom-readme-badges -->
<p align="center">
  <img src="docs/badges/ci.svg" alt="CI" />
  <img src="docs/badges/coverage.svg" alt="coverage" />
  <img src="docs/badges/license.svg" alt="License: MIT" />
</p>
<!-- /aicom-readme-badges -->

<p align="center"><img src="docs/gallery/hero.svg" alt="{Product} hero" width="820"></p>

## Gallery
| Still | Caption |
| ----- | ------- |
| docs/gallery/01.svg | … |
| docs/gallery/02.svg | … |

## What it is
## What it is not
## Quick start
## Tests
## Docs
- [English](docs/en.md) · [{Locale}](docs/{code}.md)
## License
```

CLI/API-only products replace the hero `<img>` with a mermaid diagram.

## Architect `repository_layout`

The ASCII tree MUST include at least:
`README.md`, `LICENSE`, `CHANGELOG.md`, `docs/en.md`, `docs/gallery/`
(when UI), `docs/badges/`, `.github/workflows/ci.yml`, and the test
directories named in `testing_contract`. Add `README.<code>.md` +
`docs/<code>.md` when `content_language` ≠ `en`. Add `release.yml` for
**full_software**.

## Forbidden

- README that is only “run index.html” with no hero, badges, or tests.
- English-only docs when the product UI is not English.
- Fake “100% coverage” or shields.io passing badges with no workflow.
- Binary screenshot dumps in the LLM `files` payload — use SVG stills.
