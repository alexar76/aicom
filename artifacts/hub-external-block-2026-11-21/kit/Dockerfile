# The home page's block of other providers' x402 services moves below everything that runs through the hub,
# with a title and note that say ModelMarket does not relay or bill those calls (five languages) — 2026-11-21.
# Built FROM modelmarket-hub:3.22.0-20261121 (CoinMarketCap listed, as in main): two UI files change, at both
# places the package reads them (/app is the authored copy ui_assets prefers; static/ui is the wheel's copy).
ARG BASE
FROM ${BASE}
ARG RUN_USER=hub
USER root
COPY files/ /tmp/extblock/
RUN set -e; cd /tmp/extblock; sha256sum -c SHA256SUMS; \
    for f in terminal-home.html hub-ui-i18n.json; do \
      install -m 0644 "$f" "/app/$f"; install -m 0644 "$f" "/app/aimarket_hub/static/ui/$f"; \
      chown "$RUN_USER" "/app/$f" "/app/aimarket_hub/static/ui/$f"; done; \
    cd /app; python -c "import json, aimarket_hub.ui_assets as u, aimarket_hub.external_services as e; p=u.ui_asset_path('terminal-home.html'); assert p == '/app/terminal-home.html', p; assert 'Other x402 services' in open(p).read(); json.load(open(u.ui_asset_path('hub-ui-i18n.json'))); assert [s['id'] for s, _ in e._SERVICES] == ['coinmarketcap', 'tavily', 'laso']"; \
    cd /; rm -rf /tmp/extblock
USER ${RUN_USER}
LABEL ai.market.overlay="hub-external-block-20261121"
