# Catalog and workflow preservation audit — 2026-10-11

## Scope and findings

Compared the factory before the landing reorganization (`a5c45044a^`), the homepage before visitor simplification (`8e3221115^`), and the current working tree. The simplification removed working entry points from the homepage even though their backend implementations remained. Treat this as a functional regression, not only a presentation issue.

| Capability | Finding and correction | Verification |
| --- | --- | --- |
| Complete public catalog | QA-only default hid most entries. All listed products are now the default. | Live API and browser: 19 entries, 15 landings and 4 full products. |
| Separate shelves | Restored Landing pages and Full products sections, counts and direct anchors. | Desktop and mobile browser. |
| Catalog discovery | Restored category filters, text/stack search, template labels, tags, prices, implementation details, build replays and category browsing. | QA filter: 2; FinTech: 4; Relay search: 1; reset: 19. |
| Homepage factory order | Restored the original public pipeline form, 20 style presets, validation and idea handoff to Admin. | Validation in browser; original POST payload/redirect retained. No extra pipeline job queued during this audit. |
| Full pipeline landings | Existing admin delivery profile, fast-path switch and optional web assistant are retained. | Review screen reached with marketing_landing, fast pipeline off, assistant on; see full-pipeline-review.txt. |
| Quick generator | Kept separate from pipeline ordering, with its optional web assistant. | Real English generation succeeded in 46.8 seconds; preview and ZIP control appeared; assistant answered an export question. See assistant-generation.txt. |
| Idea handoff through login | Two independent unauthorized-session redirects lost the target tab. Preserve a validated local return path in both, and delay tab mounting until authentication finishes. | Unit tests plus live signed-out handoff. |
| Category index performance | The old index independently requested every category, multiplying backend scans and causing timeouts. Share one catalog request per render and filter using the original shelf rules. | Unit tests; final live routes and browser checks. |
| Technical sections | Restored quality metrics. Features, pipeline, architecture and ecosystem blocks remain expandable. Hash navigation opens the enclosing section. | Live #features navigation. |
| Marketplace widget | Remains available on demand. | Opened and closed live capability search. |
| Product detail and checkout entry | Preserved specifications, architecture, API/data details, sandbox, security report, feedback and purchase entry. | Live product pages and checkout route; no payment submitted. |

## Source preservation

No deleted files were found in the frontend or landing-generator diff for this reorganization. Product-detail, explore-page, build-replay and checkout source directories, admin tab components, `web/backend/main.py` and `aicom-landing/server.js` match the pre-reorganization baseline. The admin shell/login and API client now have the targeted return-path fix; category data loading now avoids duplicated scans. Catalog records and pipeline settings were not deleted or rewritten by this repair.

This is a scoped audit of the reorganization and public entry flows, not proof that every historical feature or backend integration is defect-free. Full paid checkout and a new full pipeline build were not executed here; the public demo and existing focus configuration were preserved.

## Regression rule

Before changing storefront information architecture, inventory every existing form, action, route, catalog filter and section. Every retained capability must have an explicit reachable destination. Hiding a section is acceptable only when its navigation and deep links continue to work. Keep quick generation, factory pipeline landings and full product builds distinguishable.

## Validation and deployment

- 28 focused unit tests passed: return-path validation, API unauthorized handoff, category shelf semantics, QA state and locale resolution.
- TypeScript check passed.
- Production frontend builds passed; existing containers are retained for rollback.
- `routes-before.json` records the initial timeouts. Its `/api/categories` probe was incorrect; the final check uses `/api/products/categories`.
- All 12 final route checks returned HTTP 200 with complete response bodies. Cold category requests took 14.9–15.3 seconds; the public catalog API took 10.4 seconds. Backend scan latency remains a known limitation.
- The signed-out idea handoff returned to `/admin?tab=new-product` with the exact 86-character brief intact; see `admin-handoff-final.txt`.
- English desktop/mobile screenshots and live interaction transcripts are in this directory.
- Production changes are confined to the factory frontend. The marketing landing and ecosystem landing retain their distinct domains.
- Final frontend: `aicom-frontend-catalog-shelves-20261011`, loopback port 9094. Nginx backup: `/root/catalog-shelves-20261011/magic-ai-factory.com.before`; previous frontend remains on 9093.
- Publish source through `scripts/push_gitea_monorepo.sh` only. No GitHub publication is part of this repair.
