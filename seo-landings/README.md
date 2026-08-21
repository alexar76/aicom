# SEO landings — source & build

> 🌐 **English** · [Русский](docs/README.ru.md) · [Español](docs/README.es.md) · [Français](docs/README.fr.md) · [中文](docs/README.zh.md) · [Glossary](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)

Programmatic SEO pages for passive search traffic. **Sources live here; output is written to `ecosystem-landing/`** and deployed with the main ecosystem landing.

## What gets built

| Path on site | Content |
|--------------|---------|
| `/learn/` | Course hub + 10 course landing pages |
| `/oracles/` | Oracle hub + 17 verifiable-math oracle pages |
| `/guides/` | 6 developer answer pages (from `docs/specs/`, ARGUS use case) |
| `/encyclopedia/` | Cosmic Encyclopedia (EN/RU/ES + PDFs) with injected meta |
| `/sitemap.xml` | Unified sitemap (~42 URLs) |
| `/robots.txt` | Crawler rules + sitemap pointer |
| `/shared/seo.css` | Shared professional stylesheet |

Each page includes: `title`, `description`, `canonical`, Open Graph, Twitter cards, JSON-LD (`Course`, `TechArticle`, `SoftwareApplication`).

## Build locally

```bash
# Production canonical (modeldev)
./scripts/build_ecosystem_landing.sh

# GitHub Pages mirror
SEO_BASE_URL=https://alexar76.github.io/aicom ./scripts/build_ecosystem_landing.sh

# Smoke verify
./scripts/verify_seo_landings.sh
```

**Factory Pages note:** `courses/` and `oracles/` are satellites, so the trimmed
`alexar76/aicom` tree has neither. `/learn/` still builds from
`seo-landings/data/courses.yaml` (keep in sync with course titles). `/oracles/`
needs `oracles.ts` — the Pages workflow fetches it from `alexar76/oracles`.
`school/build.py` is skipped when `school/` is absent.

Low-level:

```bash
python3 scripts/build_seo_landings.py --base-url https://modeldev.modelmarket.dev
```

## Deploy (for ops / deploy agent)

### modeldev.modelmarket.dev (nginx)

```bash
# On factory host — builds + rsync to /var/www/modeldev.modelmarket.dev
sudo ./scripts/deploy_ecosystem_landing.sh
```

Also runs as step **7/7** of `./scripts/deploy_ecosystem.sh`.

Nginx: `deploy/nginx/modeldev.modelmarket.dev.conf` — static `try_files` serves all subpaths.

### GitHub Pages (aicom repo)

Workflow: `.github/workflows/pages-ecosystem.yml` — runs `build_ecosystem_landing.sh` with `SEO_BASE_URL=https://alexar76.github.io/aicom`, then uploads `ecosystem-landing/`.

**Do not push manually** unless publishing; workflow triggers on changes to `seo-landings/`, `docs/encyclopedia/`, specs, courses, oracles metadata.

## Edit content

| What | Where |
|------|-------|
| Site URLs, external links | `seo-landings/seo.config.yaml` |
| Guide list + SEO copy | `seo-landings/data/guides.yaml` |
| Guide body | Linked markdown in monorepo (`docs/specs/…`, `argus/docs/…`) |
| Oracle facts | `oracles/frontend/src/oracles.ts` (parsed at build) |
| Course metadata | `courses/*/course.config.json` + `courses/catalog.yaml` |
| Encyclopedia narrative | `docs/encyclopedia/content/{en,ru,es}.json` |
| Shared styles | `seo-landings/shared/seo.css` |
| Main landing nav | `ecosystem-landing/index.html` (hand-edited) |

## Dependencies

- Python 3.9+
- PyYAML (`pip install pyyaml`) — available in CI workflow
