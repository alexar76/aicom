# modelmarket.dev home: other providers' x402 services in their own block, at the bottom — 2026-11-21

Owner 21.11 asked whether CMC belonged on the home page. Agents can use the three listed services
(CoinMarketCap, Tavily, Laso), but only directly: the agent pays the provider from its own wallet. The hub
does not relay or bill these calls (`hub_invoke: false`), and the x402 bridge pays none of them. The owner's
answer: keep them, on the home page in their own block («не на главной а на главной в блоке своем»). Then,
on the proposal, «ДА»:

- **Placement.** The block moves from right under the search bar (above everything the hub runs) to just
  above the footer.
- **Wording.** A title and note in five languages say it plainly (`hub-ui-i18n.json`):
  - en: "Other x402 services — paid to the provider directly" / "ModelMarket does not relay or bill these
    calls: your agent pays the provider from its own wallet, on the terms the provider publishes."
  - ru: «Другие сервисы x402 — оплата напрямую поставщику» / «ModelMarket не передаёт и не оплачивает эти
    вызовы: ваш агент платит поставщику со своего кошелька по опубликованным им условиям.»
- **CMC is listed again.** Main never dropped it (6965ef6d1 reverted the removal). Prod had run without it
  from 19:40Z (`3.22.0-nocmc-20261121`).
- **Search** is unchanged: it already shows these as their own group below the hub's results, with the same
  title and note.

**Tests.** `terminal_search_evidence.test.cjs` now expects the new title; node 19/19 pass. pytest passes 29/29:
terminal search evidence, live, SSR, UI assets, social card, catalogue hygiene.

**Rollout.** Two-file overlay `modelmarket-hub:3.22.0-extblock-20261121` (sha256:9e974d6b…), built FROM the
release image `modelmarket-hub:3.22.0-20261121` (45737a5b…). `build.sh` refuses unless that image's
`terminal-home.html` (a915a3af…) and `hub-ui-i18n.json` (1f4ca846…) equal main's before this change. The new
files go to `/app` (the copy `ui_assets` prefers) and to `aimarket_hub/static/ui`. `roll.sh` ran at 19:45:41Z
(server UTC):

- database backup `/root/hub-backups/modelmarket-hub-pre-extblock-20261121T194541Z.db`;
- health 9083 (hub) and 9460 (THEMIS) answered: healthy;
- the previous container (the no-CMC overlay) is kept as `modelmarket-hub-security-prev-1795290342840709036`.

**After.**
- `/ai-market/v2/external-services` lists coinmarketcap, tavily and laso.
- The served home page has `#external-directory` after the dashboard and before `<footer>`, with the new
  title.
- In a browser (`?lang=ru`) the block is shown with the Russian title and note, cards CoinMarketCap, Tavily
  and Laso, and the footer next.
- The container is healthy, `RestartCount` 0, no traceback.
- `crypto.price.onchain@v1` (HESTIA) is still found by search.

**Rollback:** `./roll.sh modelmarket-hub modelmarket-hub:3.22.0-20261121 <the same health URLs>` in
`/root/hub-external-block-20261121/kit`.
