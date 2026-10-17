# Landing separation validation — 2026-10-11

Factory implementation: `web/frontend/`. Ecosystem source: `scripts/github-io/`.
Ecosystem delivery: https://github.com/alexar76/alexar76.github.io/pull/1 (draft).
Neither production homepage was deployed by this change.

Verified:

- Next.js 16.4 production build passed (36 generated routes); TypeScript passed.
- ESLint passed for the changed page, layout, locale copy, widget loader and locale regression test.
- `vitest run lib/siteLocale.test.ts`: 10 tests passed.
- `python3 scripts/github-io/validate.py`: five translations, generated HTML consistency, anchors, local assets, font files and metadata passed.
- Both scene modules and ecosystem interactions passed JavaScript syntax checking; shared scene copies match.
- Mirror secret scan and `git diff --check` passed.
- `http-checks.json`: 10 real HTTP page requests, SSR locales and factory canonical/social metadata.
- `guide-checks.json`: five real HTTP 200 downloads of the bundled subcontracting guide.
- `external-links.json`: nine public project/generator destinations returned HTTP 200. It also records the missing GitHub procurement guide; the homepage now serves a bundled download instead.
- Browser: actual WebGL rendering, factory stage selection, pause, EN/RU/ES/FR/ZH language switching, navigation to `/lead` and back. The production navigation check returned no browser errors or warnings.
- Atlas browser: RU/FR switching and trust-category filtering returned METIS, AttestedMemory, WARDEN, THEMIS (four results).
- Desktop and 390px mobile layouts inspected. All five factory locales reported a 379px document width in a 390px viewport, with a 334px stage control. No horizontal document overflow. The market widget remains hidden on return to the factory homepage.

The screenshots show locally running builds, not a deployment. JPEG files come directly from browser capture. Factory hero captures precede the final documentation-link change; `factory-subcontracting.jpg` shows that final change.

Limits: this frontend-only preview had no Python backend, so theme/analytics API requests could not connect. Lead submission, email delivery and the product pipeline were not exercised during the landing redesign. The pre-existing locale Playwright suite was updated but not executed; equivalent focused browser and HTTP checks above were performed. Reduced-motion and WebGL failure behavior were reviewed in source; no browser failure injection or Lighthouse score is claimed. The separate real LLM/subcontracting evidence is in `../factory-subcontracting-live-2026-10-11.json`.

Initial production build hit a sandbox socket error cached by Turbopack. A clean generated cache and approved build succeeded; no dependency or application workaround was required.
