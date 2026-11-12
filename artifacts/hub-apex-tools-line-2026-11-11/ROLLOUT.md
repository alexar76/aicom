# modelmarket.dev: a line for people who came for the checks — 2026-11-11

Owner, 2026-11-11: «Предлагаемое позиционирование: ДА» and «Yes, apply it» (the positioning applied to the docs and
the modelmarket.dev page). Positioning: `PromoMaterials/strategy/positioning-2026-11-11.md`.

## What changed

The home page hero gets one line above the eyebrow: *Checks and a witnessed public record for the tools AI agents
use: HISTOR · WARDEN · Free checks*. It links to histor.modelmarket.dev, warden.modelmarket.dev and
modelmarket.dev/tools/, and is translated into RU, ES, FR and ZH (`apex_tools_line`, `apex_tools_free` in
`hub-ui-i18n.json`). The hub's own tagline and terminal stay as they were.

Code, on the aicom branch with this record:
- `aimarket-hub/terminal-home.html`: CSS and markup, between `<!-- apex-only -->` markers;
- `aimarket-hub/hub-ui-i18n.json`: two keys in five languages;
- `aimarket_hub/hub_routes/pages.py`: every hub not named `modelmarket.dev` drops the marked block, so a stranger's
  hub never shows our line above its name;
- `tests/test_branding.py`: the line is on the reference hub and absent from a third-party one.

## Production

The apex hub on factory-vps ran `modelmarket-hub:xb3-20261108` (b43b763b5ae3). Its `/app/hub-ui-i18n.json` equalled
main's byte for byte. Its `/app/terminal-home.html` (89356c61…) is a production variant: it lacks main's later
link-contrast CSS (212fa377b). So `patch.py` put the same two blocks into the production file at the same anchors,
and nothing else changed (`prod-before-terminal-home.html` is the file before the patch).

- Overlay `modelmarket-hub:apex-tools-20261111` (8ecd6cd3547d) = the running image plus the two files (`Dockerfile`,
  `build.sh`). `/app` copies are the ones served: `ui_asset_path` prefers them over `static/ui/`.
- `smoke.py` passed inside the image with no network: file hashes, the line once, five languages, the app imports.
- Open alerts before the roll: disks of oracle (admin-vps, 2 d 20 h) and attested. Nothing on factory-vps or the
  hub. No OS rollout was running.
- Rolled 2026-11-11 04:54:57Z (host clock):

  ```
  roll.sh modelmarket-hub modelmarket-hub:xb3-20261108 modelmarket-hub:apex-tools-20261111 \
    http://127.0.0.1:9083/ai-market/v2/health,http://127.0.0.1:9460/health
  ```

  SQLite backup `/app/data/hub-backup-pre-3160-20261111T045457Z.db`. Healthy; THEMIS recreated and healthy
  (`roll-apex.log`).

## Verified live

- `https://modelmarket.dev/` serves `<p class="apex-tools">` once; `/ai-market/v2/health` is 200.
- `/hub-ui-i18n.json` has the keys in all five languages.
- All three link targets answer 200.
- In a browser, RU gives "Проверки и публичная история с подписями свидетелей для инструментов ИИ-агентов:"; the
  links compute to rgb(56, 224, 255).
- The page was checked at 800 px and at 375 px (mobile): the line wraps under itself and the links stay on one line
  each.

## Rollback

- Previous containers: `modelmarket-hub-security-prev-1794372898256268572` (and
  `themis-security-prev-1794372898256268572`), via rollout_container.py.
- Or roll again onto `modelmarket-hub:xb3-20261108`:

  ```
  roll.sh modelmarket-hub modelmarket-hub:apex-tools-20261111 modelmarket-hub:xb3-20261108 <same health URLs>
  ```

- The other five hubs are not touched. They don't need the line. When they next roll from main, `pages.py` drops
  it for them.
