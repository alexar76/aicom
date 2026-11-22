# modelmarket.dev home: a strip of HESTIA's verification agents (called through this hub) above the block of
# other providers' x402 services, in five languages; both blocks are now removed by the server on any hub that is
# not modelmarket.dev (exact apex-only markers) — 2026-11-22.
# Built FROM modelmarket-hub:3.22.0-extblock-20261121 (the live image): two UI files change, at both places the
# package reads them (/app is the authored copy ui_assets prefers; static/ui is the wheel's copy).
ARG BASE
FROM ${BASE}
ARG RUN_USER=hub
USER root
COPY files/ /tmp/hestiastrip/
RUN set -e; cd /tmp/hestiastrip; sha256sum -c SHA256SUMS; \
    for f in terminal-home.html hub-ui-i18n.json; do \
      install -m 0644 "$f" "/app/$f"; install -m 0644 "$f" "/app/aimarket_hub/static/ui/$f"; \
      chown "$RUN_USER" "/app/$f" "/app/aimarket_hub/static/ui/$f"; done; \
    cd /app; python -c "import json, aimarket_hub.ui_assets as u; p=u.ui_asset_path('terminal-home.html'); assert p == '/app/terminal-home.html', p; h=open(p).read(); assert 'id=\"hearth-directory\"' in h and h.index('id=\"hearth-directory\"') < h.index('id=\"external-directory\"'); ui=json.load(open(u.ui_asset_path('hub-ui-i18n.json')))['ui']; assert all('hearth_title' in ui[l] for l in ('en','ru','es','fr','zh'))"; \
    cd /; rm -rf /tmp/hestiastrip
USER ${RUN_USER}
LABEL ai.market.overlay="hub-hestia-strip-20261122"
