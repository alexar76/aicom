# Review of the week's changes — 2026-11-14 to 2026-11-22

Owner 21.11: «проверь наши изменения последней недели на качество, покрой тестами если не покрыто и проверь на
вулнетикс». Range: main from 49d571e57 (parent of the week's first commit 3c3f15b4d) to 084cf5666, 380 commits; the
largest code changes in warden, histor, scripts, community-landing, hestia-agents, aimarket-hub, argus.

## Vulnetix-class and static checks over the whole range

| check | result |
|---|---|
| `scripts/code_scan_gate.sh main 49d571e57` — our Vulnetix-class rules (open without a key, check-then-connect SSRF, forwarding-header trust, ssh without host keys) | 0 new findings |
| the same gate's Semgrep 1.185.0 layer (p/python, p/javascript, p/typescript, p/owasp-top-ten, baseline mode) | nothing new |
| `scripts/python_bug_gate.sh main` (syntax, undefined names) | clean |

## Test suites on main, each with the dependencies the component really runs with

| component | result | notes |
|---|---|---|
| histor | 1661 passed, 337 skipped | |
| hestia | 829 passed | |
| momus | 550 passed | |
| warden | 2137 / 2137 | vitest |
| argus | 607 passed, 10 skipped | vitest |
| okx-a2mcp | 87 / 87 | |
| mcp-token-cost | 40 / 40 | after `npm ci` (main's checkout has no node_modules); 7 of them new, below |
| aimarket-hub | 4375 passed | with `--all-extras` (escrow needs eth-account). Two more fail without the in-repo provenance plugin and pass with it (`--with-editable ./plugins/aimarket-provenance`); `test_topup_chain` short authorization is the known failure recorded on 2026-11-18 and skips with the plugin |
| skopos | 1004 passed | with the fixes below; `test_all_analytics_dashboards_render_and_cached_revisit_is_fast` needs the untracked local `servers.yaml`/`agent.yaml`/`skopos.sqlite3` of the main checkout (it passes there, fails in a clean tree): a pre-existing test-hygiene gap, not this week's |
| hestia-agents | all pass | except the sandbox-lint tests without HESTIA's dependencies (147/147 with them) and the bundle-version test (0.35.0 bundle vs 0.36.0 in main) |

## Changed code no test exercised

Every changed source file of the week was matched against the tests of its component (by module name, then by the
behaviour: routes, fields). Money, auth and security changes (web backend payment/admin, kova and charon billing,
esim rails paywall/quote, hub external services, HESTIA roster fields, HISTOR payer audit, the UNI lottery guard,
core/untrusted_text) all have tests. One gap: **mcp-token-cost** (on npm since 21.11) printed money and population
figures that no test checked → `mcp-token-cost/test/money.test.js` (7 tests: uncached, warm-cache and rewritten-cache
cost per 1,000 requests, a custom price, no guessed cache-read price for Haiku, the 101-point curve and percentile).
Its `data/prices.json` agrees with the current model table.

## Fixed

- **skopos/pyproject.toml** declared none of `tldextract`, `user-agents`, `requests`, `python-dateutil`, `maxminddb`,
  which the package imports (only `requirements.txt`, the image, had them): an install from pyproject and its tests
  failed with ModuleNotFoundError. Declared, and `pytest-asyncio` added to `dev`.
- **skopos/uv.lock** had drifted to pandas 3.0.6 and plotly 7.1.0 while the image runs pandas 2.2.2 and plotly 5.23.0;
  three dashboard tests fail on the newer majors (pandas 3 StringDtype nulls render as NaN; plotly 6+ serialises arrays
  as {"dtype","bdata"}, which a cached snapshot does not turn back into numbers). pyproject now caps pandas<3 and
  plotly<6, so the lock matches what is tested and deployed; moving up is its own change.
- **skopos/ui.py** `prepare_display_df` also treats StringDtype text columns, so a missing value shows "—" under
  pandas 3 too.

## Left as findings

- SKOPOS's dashboard render test depends on local untracked config and may reach the servers named there.
- Component suites need setup that their manifests do not say (hub: provenance plugin; skopos: sibling momus).
