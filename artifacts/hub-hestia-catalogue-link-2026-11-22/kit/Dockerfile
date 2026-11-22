# modelmarket.dev home: the HESTIA strip links the agent catalogue (hestia.modelmarket.dev/agents/) — 2026-11-22.
# Built FROM modelmarket-hub:3.22.0-capsfix-20261122 (the live image, with the capability-search fix of 07:01Z):
# the two UI files are aicom main 5f2c92588, which carries that fix too; both places the package reads them.
ARG BASE
FROM ${BASE}
ARG RUN_USER=hub
USER root
COPY files/ /tmp/cataloguelink/
RUN set -e; cd /tmp/cataloguelink; sha256sum -c SHA256SUMS; \
    for f in terminal-home.html hub-ui-i18n.json; do \
      install -m 0644 "$f" "/app/$f"; install -m 0644 "$f" "/app/aimarket_hub/static/ui/$f"; \
      chown "$RUN_USER" "/app/$f" "/app/aimarket_hub/static/ui/$f"; done; \
    cd /app; python -c "import json, aimarket_hub.ui_assets as u; p=u.ui_asset_path('terminal-home.html'); assert p == '/app/terminal-home.html', p; h=open(p).read(); assert 'href=\"https://hestia.modelmarket.dev/agents/\"' in h and h.index('id=\"hearth-directory\"') < h.index('id=\"external-directory\"'); ui=json.load(open(u.ui_asset_path('hub-ui-i18n.json')))['ui']; assert all('hearth_catalogue' in ui[l] for l in ('en','ru','es','fr','zh'))"; \
    cd /; rm -rf /tmp/cataloguelink
USER ${RUN_USER}
LABEL ai.market.overlay="hub-hestia-catalogue-link-20261122"
