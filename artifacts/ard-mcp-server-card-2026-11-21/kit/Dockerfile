# The ARD MCP entry names the SEP-2127 Server Card (/mcp/server-card) — rollout 2026-11-21.
# Built FROM the container's own image: two files of the package change (aimarket_hub/ard.py and
# aimarket_hub/hub_routes/ard.py). The running copies equal aicom main ad4065b30 (checked by sha256 in
# build.sh before building); the copies here are those files plus this change. No dependency or database change.
ARG BASE
FROM ${BASE}
ARG RUN_USER=hub
USER root
COPY files/ /tmp/ardcard/
RUN set -e; cd /tmp/ardcard; sha256sum -c SHA256SUMS; \
    install -m 0644 ard.py /app/aimarket_hub/ard.py; \
    install -m 0644 routes_ard.py /app/aimarket_hub/hub_routes/ard.py; \
    chown "$RUN_USER" /app/aimarket_hub/ard.py /app/aimarket_hub/hub_routes/ard.py; \
    cd /app; python -c "import aimarket_hub, aimarket_hub.ard as a, aimarket_hub.hub_routes.ard, aimarket_hub.ai_catalog as c; assert aimarket_hub.__file__.startswith('/app/'), aimarket_hub.__file__; assert c.SERVER_CARD_PATH == a.MCP_SERVER_CARD_PATH"; \
    cd /; rm -rf /tmp/ardcard
USER ${RUN_USER}
LABEL ai.market.overlay="ard-mcp-server-card-20261121"
