# WARDEN article quality pass — 2026-11-08

Canonical article and illustrations live in the user-authorized sibling directory
`../PromoMaterials/devto/warden-own-market-2026-11-07/`.
This folder contains implementation-derived fixture data, generation code and test evidence.

## Bounded checks

From `aimarket-hub/`, using its existing Python environment:

```sh
./.venv/bin/python -m pytest \
  tests/test_mcp_stranger_path.py::test_a_price_or_trial_change_leaves_the_tool_definitions_alone \
  tests/test_mcp_stranger_path.py::test_direct_tool_text_follows_free_and_trial_settings -q
```

Result: 2 passed, one existing Starlette deprecation warning. See `gateway-regression.log`.

From `argus/`:

```sh
./node_modules/.bin/vitest run test/mcp-health.test.ts
```

Result: 9 passed. See `argus-mcp-health-rerun.log`. The first sandboxed attempt could not
listen on loopback (`EPERM`) and is retained as `argus-mcp-health.log`; the permitted
loopback rerun made no external service requests.

No full test suite, production probe, dependency installation or source implementation
change was needed for this pass.

## Figure data and reproducibility

From `aicom/`:

```sh
./aimarket-hub/.venv/bin/python artifacts/article-quality-2026-11-08/warden/generate_fixtures.py
python3 artifacts/article-quality-2026-11-08/warden/generate_figures.py --out /tmp/warden-quality-2026-11-08
python3 artifacts/article-quality-2026-11-08/warden/render_figures.py /tmp/warden-quality-2026-11-08
```

The fixture calls the actual `_direct_tool_definition`, controls `sandbox_enabled` and
`max_per_visitor`, and compares complete dictionaries. Five selected cases for `weather_now`
produce equality results `[true, true, true, false, false]`. The positive-price and numeric-quota
invariant is also checked for all five current direct-tool definitions. `fixture-results.json`
contains descriptions, inputs and source hashes. These are regression fixture inputs, not
observed traffic, rates, production safety results or a benchmark.

`mcp-admission-states` illustrates the paths implemented in `argus/src/mcp/host.ts` and the
recorded November 6 counters. The allowed branch requires a positive WARDEN verdict, not just
pin equality. It makes no claim of recovery after the recorded incident. All three ARGUS still
awaited a human TTY reapproval and restart at the end of that rollout.

The SVG sources are deterministic. Chromium PNG rendering permits local files and aborts
HTTP(S) requests. Both final PNGs were inspected visually. `quality-result.json` records the
canonical asset paths, byte sizes, hashes, dimensions and preserved-frontmatter check.

Body: 739 → 940 whitespace-delimited words (including code, alt text and captions).
Before-image: `article.before-quality-2026-11-08.md` in the article pack. This pass changed no
cover, publication date, DEV.to article, blog deployment or GitHub state.
