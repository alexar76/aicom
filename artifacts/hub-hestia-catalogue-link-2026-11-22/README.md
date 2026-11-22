# modelmarket.dev home: the HESTIA strip links the agent catalogue — rollout 2026-11-22 (LIVE 07:39Z)

Part of «Что ещё не сделано: - делай» (owner 22.11). Code: aicom main 5f2c92588: under the four cards of the
"Verification agents on HESTIA — through this hub" strip, a link "The catalogue: what each one checks, its code
and that code's SHA-256 ↗" to `https://hestia.modelmarket.dev/agents/`, next to the existing HESTIA link; five
languages (`hearth_catalogue`).

The same commit repairs `tests/test_branding.py`: the strip's translation test (3921e7413) had been inserted inside
`TestTheHomePageAndTheWidget`, which made the widget allowlist test after it a nested function pytest never
collected. It is a module-level test after the class again. branding + landing 50 passed, 1 skipped (the widget
package is not bundled in this checkout); terminal page node tests 19/19.

## Base

Another session rolled the capability-search fix at 07:01–07:04Z (`modelmarket-hub:3.22.0-capsfix-20261122`,
main 06809e022). Checked on the live container before building: `/app/terminal-home.html` = main 06809e022
(a4168f86…, with that fix), `hub-ui-i18n.json` = 06809e022 (6fc25823…). The new files are main 5f2c92588, which
differs from 06809e022 only by this link and its five translations; the build asserts the link, the strip's place
and the key in every language, and the fix's `drainCaps` line is still served afterwards. Both copies are
installed (`/app` and `aimarket_hub/static/ui`; the latter had still held the strip version without the fix).

## Switch

| container | switched (UTC) | new image | previous (rollback) |
|---|---|---|---|
| modelmarket-hub | 07:39:19–07:39:32 | `modelmarket-hub:3.22.0-cataloguelink-20261122` = ef2ece24026b | `modelmarket-hub-security-prev-1795333161183267248` (`3.22.0-capsfix-20261122`) |

THEMIS shares the hub's network namespace and was recreated with it (healthy). DB backup
`/root/hub-backups/modelmarket-hub-pre-cataloguelink-20261122T073919Z.db`. Kit on the host
`/root/hub-catalogue-link-20261122/kit`. Rollback:

    cd /root/hub-catalogue-link-20261122/kit && ./roll.sh modelmarket-hub modelmarket-hub:3.22.0-capsfix-20261122 \
      http://127.0.0.1:9083/ai-market/v2/health,http://127.0.0.1:9460/health

## After

Healthy, 0 restarts, no traceback. https://modelmarket.dev/ links `https://hestia.modelmarket.dev/agents/`, the
strip still before the external block, the capability-search fix still in the page; `/hub-ui-i18n.json` carries
`hearth_catalogue` in en, ru, es, fr, zh. hub.modelmarket.dev (not the apex) serves no strip.
