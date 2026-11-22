# modelmarket.dev home: a strip of HESTIA's verification agents — 2026-11-22 (LIVE since 06:06Z)

Owner 22.11, asked where the agent docs belong: «Лучше рядом, отдельной полосой, например «Проверочные агенты на
Гестии»: да / место сам выбери».

## What and where

A separate strip, `#hearth-directory`, directly above the block of other providers' x402 services
(`#external-directory`) and below the search and its results. It is not inside that block on purpose: the external
block says the agent pays the provider directly and the hub neither relays nor bills; HESTIA's agents are called
through the hub, are free and sign every answer.

- Title (en/ru): "Verification agents on HESTIA — through this hub" / «Проверочные агенты на HESTIA — через этот хаб».
- One sentence on what they are: checks to run before trusting a payment, a package, a server or a signature;
  WebAssembly sandbox, declared or caller-named hosts only, every answer signed; free.
- Four cards, each a button that fills the hub's own search and opens its results:
  `x402.preflight@v1` ("x402 preflight"), `package.provenance.verify@v1` ("package provenance"),
  `agent.card.verify@v1` ("agent card verify"), `registry.entry.verify@v1` ("registry entry verify").
  The other three (evm.signature.verify, timestamp.verify, site.agent_policy) are found by the same search.
- A link to https://hestia.modelmarket.dev/ ("HESTIA, the hearth they run on").
- Five languages through `hub-ui-i18n.json` (`hearth_*` keys in en, ru, es, fr, zh).
- 4 columns on desktop, 2 at ≤900 px, 1 at ≤640 px; capability ids break only after a dot (`<wbr>`).
- Apex only: wrapped in the exact `<!-- apex-only -->` markers that `hub_routes/pages.py` strips when the hub is not
  modelmarket.dev. The external block's opening marker had text after it, so the strip pattern missed it and other
  hubs got that block hidden rather than removed; it now uses the exact marker too.

## Bug caught while checking

The page closes the search results on any click outside the search box (document click listener). A card's click
bubbled to it, so the results opened and closed at once. The card handler stops propagation; the browser check below
shows the results staying open.

## Tests

- `aimarket-hub/tests/test_branding.py`: on a third-party hub neither `#hearth-directory`, the HESTIA link nor
  `#external-directory` is served; on the apex the strip comes after the search, before the external block and before
  the footer, with the four searches and the HESTIA link; `test_the_hestia_strip_is_translated_in_every_language`
  checks every `data-i18n` key of the strip exists in all five languages.
- branding + landing: 29 passed; hub node tests 10/10.

## Rollout (factory-vps, container `modelmarket-hub`)

- Kit `kit/`: Dockerfile FROM the live image `modelmarket-hub:3.22.0-extblock-20261121`, replacing
  `terminal-home.html` and `hub-ui-i18n.json` (SHA256SUMS in `kit/files/`); the build asserts the strip comes before the
  external block and the keys exist. `build.sh` refuses to build unless the two files in the base image hash as
  expected (42e621f171b1c1cd…, fcbe69e859b53da4…), so nothing newer is overwritten.
- `roll.sh` backed up the DB to `/root/hub-backups/modelmarket-hub-pre-hestiastrip-20261122T060613Z.db`, then
  `rollout_container.py` swapped the container with health checks on `:9083/ai-market/v2/health` and `:9460/health`.
- Server time 2026-11-22T06:08:50Z: `modelmarket-hub` on `modelmarket-hub:3.22.0-hestiastrip-20261122`
  (sha256:6df04e95913d…), started 06:06:17Z, healthy, 0 restarts, 0 tracebacks since 06:06Z, health HTTP 200.
  Previous container kept stopped as `modelmarket-hub-security-prev-1795327574912702806` (image
  `3.22.0-extblock-20261121`).

## Live checks

- https://modelmarket.dev/ serves `#hearth-directory` before `#external-directory` and before the footer;
  `/hub-ui-i18n.json` has the `hearth_*` keys in all five languages; the external services endpoint still lists
  coinmarketcap, tavily and laso.
- Browser, https://modelmarket.dev/?lang=ru: the Russian title and text; the external block with its three cards
  still visible below; clicking the second card put "package provenance" into the search and the results opened with
  `package.provenance.verify@v1`. At phone width (375 px) the strip is one column of 335 px and ends inside the
  viewport. The page as a whole is 23 px wider than 375 px there because of the header's `Live · time` indicator
  (`.conn` in `.nav-inner`), which this change does not touch: a pre-existing header finding.
- Other hubs were not rolled; their images do not contain the strip, and the apex-only stripping covers any hub built
  from main later.

## Rollback

On factory-vps, in `/root/hub-hestia-strip-20261122/kit`:

    ./roll.sh modelmarket-hub modelmarket-hub:3.22.0-extblock-20261121 \
      http://127.0.0.1:9083/ai-market/v2/health,http://127.0.0.1:9460/health

The DB is unchanged by this rollout (static page files only); the backup above is a precaution.

## Follow-up (done 2026-11-22, owner «Yes, publish it», «делай»)

The catalogue is LIVE at https://hestia.modelmarket.dev/agents/ with `handler_sha256` on the roster; the strip
links it (07:39Z) and so does the Alien Monitor's HESTIA card. Records: `hestia-catalogue-rollout-2026-11-22`,
`hub-hestia-catalogue-link-2026-11-22`, `alien-hestia-catalogue-2026-11-22`.
