# CoinMarketCap removed from the apex external-services references — 2026-11-21.
# Built FROM the container's own image (hub 3.22.0): one file of the package changes,
# aimarket_hub/external_services.py. The running copy equals aicom main before this change (sha256 checked in
# build.sh). No dependency or database change.
ARG BASE
FROM ${BASE}
ARG RUN_USER=hub
USER root
COPY files/ /tmp/nocmc/
RUN set -e; cd /tmp/nocmc; sha256sum -c SHA256SUMS; \
    install -m 0644 external_services.py /app/aimarket_hub/external_services.py; \
    chown "$RUN_USER" /app/aimarket_hub/external_services.py; \
    cd /app; python -c "import aimarket_hub, aimarket_hub.external_services as e; assert aimarket_hub.__file__.startswith('/app/'); ids=[s['id'] for s,_ in e._SERVICES]; assert ids == ['tavily', 'laso'], ids"; \
    cd /; rm -rf /tmp/nocmc
USER ${RUN_USER}
LABEL ai.market.overlay="hub-cmc-removal-20261121"
