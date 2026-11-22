# modelmarket.dev home page without CoinMarketCap strings — 2026-11-22 (owner: «убери строки CMC с главной»).
# Built FROM the container's own image (modelmarket-hub:3.22.0-nocmc2-20261122). Two files change, each in both places the
# image keeps them (/app and /app/aimarket_hub/static/ui): terminal-home.html (documentation-host allowlist) and
# hub-ui-i18n.json (external_desc_coinmarketcap in five languages). build.sh checks the running copies are aicom main's
# before this change. No code, dependency or database change.
ARG BASE
FROM ${BASE}
ARG RUN_USER=hub
USER root
COPY files/ /tmp/nocmcpage/
RUN set -e; cd /tmp/nocmcpage; sha256sum -c SHA256SUMS; \
    for d in /app /app/aimarket_hub/static/ui; do \
      install -m 0644 -o "$RUN_USER" terminal-home.html "$d/terminal-home.html"; \
      install -m 0644 -o "$RUN_USER" hub-ui-i18n.json "$d/hub-ui-i18n.json"; \
    done; \
    if grep -qi coinmarketcap /app/terminal-home.html /app/hub-ui-i18n.json /app/aimarket_hub/static/ui/terminal-home.html /app/aimarket_hub/static/ui/hub-ui-i18n.json; then echo "CMC string left" >&2; exit 1; fi; \
    python -c "import json; json.load(open('/app/hub-ui-i18n.json')); json.load(open('/app/aimarket_hub/static/ui/hub-ui-i18n.json'))"; \
    cd /; rm -rf /tmp/nocmcpage
USER ${RUN_USER}
LABEL ai.market.overlay="hub-cmc-strings-20261122"
