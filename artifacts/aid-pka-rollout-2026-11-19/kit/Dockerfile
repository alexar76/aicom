# AID endpoint proof (aimarket_hub/aid_pka.py) onto the running hub 3.21.0 image (rollout 2026-11-19).
# Built FROM the container's own image: only three files of the package change. hub_routes/ard.py and
# signing.py in that image are the 3.21.0 release files (checked by sha256 before building); the copies
# here are those files plus the AID lines (aicom main, see ROLLOUT.md). No dependency or database change.
ARG BASE
FROM ${BASE}
ARG RUN_USER=hub
USER root
COPY files/ /tmp/aidpka/
RUN set -e; cd /tmp/aidpka; sha256sum -c SHA256SUMS; \
    install -m 0644 aid_pka.py /app/aimarket_hub/aid_pka.py; \
    install -m 0644 ard.py /app/aimarket_hub/hub_routes/ard.py; \
    install -m 0644 signing.py /app/aimarket_hub/signing.py; \
    chown "$RUN_USER" /app/aimarket_hub/aid_pka.py /app/aimarket_hub/hub_routes/ard.py /app/aimarket_hub/signing.py; \
    cd /app; python -c "import aimarket_hub, aimarket_hub.aid_pka, aimarket_hub.hub_routes.ard, aimarket_hub.signing; assert aimarket_hub.__file__.startswith('/app/'), aimarket_hub.__file__"; \
    cd /; rm -rf /tmp/aidpka
USER ${RUN_USER}
LABEL ai.market.overlay="aid-pka-20261119"
