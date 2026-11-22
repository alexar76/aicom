# HESTIA agent catalogue in the landing's look — rollout 2026-11-22 (LIVE 11:49Z, narrow-screen fix 11:51Z)

Owner 22.11, pointing at https://hestia.modelmarket.dev/agents/: «сделай ты там красивый каталог с стилями,
полутенями и достойный наших лендингов». Code: aicom 59e7be0c0 (design), 7697bf983 (narrow screens). Only the
generated pages and `live.js` changed (`hestia-agents/scripts/build_catalog.py` → `hestia/docs/agents`); no HESTIA
code, no agent, no handler.

## What the pages look like now

- The hearth landing's palette, Syne / IBM Plex served by the hearth itself (`/fonts/fonts.css`, no third party),
  nebula, grain and vignette; sticky navigation (Hearth, Agents, Check, Limits, Others) and EN/RU/ES/FR/ZH pills.
- Hero: kicker, «Every agent, its code and its SHA-256», the catalogue intro, and a `handler_sha256` card for one
  agent (x402-preflight): the digest published here against the one the hearth runs, with `=` or `≠` and a status
  chip filled by `live.js`. Then the live summary as a status line, buttons (catalog.json, SHA256SUMS, roster, full
  text) and figures: 29 agents, 18 free, 16 without network, N/29 running the published code (live), Ed25519.
- Agents: a tile per agent (live chip, capability id, first sentence, price, network, language) above the full cards,
  which have layered shadows, an ember edge, facts as a two-column grid and the input schema behind a pill.
- Check: the curl/jq/sha256sum commands with a copy button; How to call with the URLs as code; limits as tiles;
  Others as a table; footer.
- `live.js` marks every `[data-live]` element with `data-state` and writes roster values with `textContent` only,
  as before; the copy button uses the clipboard API and does nothing where there is none.
- Dark only, like the landing. ≤420 px: the header wraps instead of pushing the language pills off screen.

## Checks before

- hestia-agents `test_catalog.py` 13 passed (it now allows the hearth's own `/` and `/fonts/` links);
  hestia `test_agent_catalogue.py` 7 passed; ruff clean.
- Rendered with Playwright (system Chrome) against a local copy and a roster saved from the live hearth, at 1440, 390 and
  320 px: no horizontal scroll (only code inside scrolling blocks is wider), all three fonts loaded, 29/29, no
  console errors. Russian, English and Chinese pages looked at.
- The running hearth was my 07:29Z image (0de5b8893bc2), healthy, 0 restarts; no HESTIA alert open. The overlay has
  the same 90 files as the running `/app/docs/agents` (the build checks every hash and the count).
- Candidate check offline (`kit/check_candidate.py`, `--network none`, `PYTHONPATH=/app`): /agents 308, all five
  pages 200, 29 sources `text/plain` with matching digests, `live.js` the new one, the design markers, `/fonts/fonts.css`
  200, encoded `../` 404, `/health` ok.

## Switch (overlay FROM the running image, ledger dump first)

| step | switched (UTC) | new image | previous (rollback) | ledger dump |
|---|---|---|---|---|
| design | 11:49:14–11:49:18 | `aicom-security:hestia-hearth-catalogue-design-20261122` = 811abdd7bf9e | `hestia-hestia-1-security-prev-1795348154754371725` (0de5b8893bc2, the 07:29Z catalogue) | `/root/hestia-backups/hestia-pg-pre-catalogue-design-20261122T114914Z.sql.gz` |
| narrow screens | 11:51:43–11:51:47 | `aicom-security:hestia-hearth-catalogue-narrow-20261122` = 0e1df4ad9965 | `hestia-hestia-1-security-prev-1795348304144097173` (811abdd7bf9e) | `/root/hestia-backups/hestia-pg-pre-catalogue-narrow-20261122T115143Z.sql.gz` |

Kit on the host: `/root/hestia-catalogue-design-20261122` (`overlay/` and `narrow/overlay/` are `git archive` of
59e7be0c0 and 7697bf983). Rollback to the previous image, or straight to this morning's catalogue:

    cd /root/hestia-catalogue-design-20261122 && python3 rollout_container.py hestia-hestia-1 --rollback
    cd /root/hestia-catalogue-design-20261122 && python3 rollout_container.py hestia-hestia-1 \
      --image aicom-security:hestia-hearth-catalogue-20261122 --health http://127.0.0.1:9480/health

## After

- Healthy, 0 restarts, no traceback. From outside: all pages `text/html`, `live.js` `text/javascript`,
  `SHA256SUMS` and sources `text/plain`; `index.html`, `index.ru.html`, `live.js` and `SHA256SUMS` byte-equal to the
  repository; `src/x402-preflight.py` hashes to the roster's 699cac9d…; 33 roster rows, all with a digest; a priced
  agent still answers 402 with its terms.
- Browser on the live site: "All 29 agents run exactly the published code", 29/29, `=` in the hero card, 88 live
  marks "same" (29 tiles, 29 card chips, 29 "now" lines, the hero chip), 4 other agents listed.
- Host tree `/root/claudecode/aicom/hestia/docs/agents` updated from 7697bf983 without deleting anything (a dry run
  with `--delete` listed 0), file modes back to the tree's 644/755, then `aicom-hestia-guard snapshot` and `check`
  ("hestia tree whole").
