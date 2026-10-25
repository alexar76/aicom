# Frontend dependency compatibility

The 2026-10-23 dependency update removes `braces` from the locked and installed frontend tree.
It does not suppress an advisory. See the [verification report](../../docs/quality-audit-2026-10-23.md#braces-resolution).

Tailwind CSS and `@tailwindcss/postcss` are pinned together at **4.3.3**; `tailwind-merge` is
**3.7.0**. The PostCSS plugin handles imports and prefixing, replacing `autoprefixer`.
The explicit CSS sources retain the app/components scan scope, and `@config` loads the existing
custom theme. Utility renames preserve the previous shadow, radius, blur and outline scales.
Custom resets live in the base layer so utilities retain precedence. Form defaults are preserved;
unprefixed backdrop-filter declarations follow vendor-prefixed declarations so production CSS
keeps blur in Chromium. Tests compare selected computed styles with values captured from the
previous production build and exercise form defaults.

The upstream [Tailwind upgrade guide](https://tailwindcss.com/docs/upgrade-guide) sets browser
requirements at **Safari 16.4+, Chrome 111+, Firefox 128+**. Local browser verification uses Chromium;
it does not certify all supported browser versions. Touch hover follows Tailwind 4's hover-capability
media query. Space/divide utilities also use the v4 sibling selectors; this check does not establish
pixel equivalence for every screen or hidden-child combination.

Next's ESLint plugin remains pinned at **16.4.2** with `eslint-config-next`. Its dependency on
`fast-glob` is replaced **only inside `@next/eslint-plugin-next`** by npm alias
`npm:tinyglobby@0.2.17`. The pinned plugin uses `globSync(..., { onlyDirectories: true })`
in `getRootDirs`; the consuming `no-html-link-for-pages` rule joins those roots to page directories.
Tinyglobby's relative paths/trailing slashes differ in representation but resolve to the same
locations in this consumer. This is not a claim that the two packages have identical APIs.

[Compatibility tests](lib/next-lint-glob.test.ts) load the actual installed plugin and check directory
filtering, brace/array patterns, path separator normalization and default roots. They run the actual
navigation rule against four root configurations and require a diagnostic, guarding against a
silently disabled rule. Recheck this consumer and the override whenever upgrading Next; remove the
override once upstream uses a safe dependency graph. Avoid extending the alias to other consumers
without separate compatibility tests.

Reproduce from this directory:

```bash
npm ci --ignore-scripts
npm audit --package-lock-only --ignore-scripts --include=dev
npm run lint -- --max-warnings=0
npm run test:unit
npm run build -- --webpack
# In another terminal: npm run start -- -p 3010 -H localhost
npm test -- --workers=2
```

The webpack option is supported by Next 16. The local Turbopack check could not bind its required
IPC port, so it is recorded as an environment limitation rather than a passing build.
