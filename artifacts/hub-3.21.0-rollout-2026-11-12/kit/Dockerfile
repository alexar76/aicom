# aimarket-hub 3.21.0 onto a running hub image (rollout 2026-11-12). Built FROM the container's own image,
# so plugins, generated files, the image's Python and every installed dependency stay; only the hub package
# changes. 3.21.0 declares the same dependencies as 3.20.0 and has no database migration.
ARG BASE
FROM ${BASE}
ARG RUN_USER=hub
ARG KEEP_UI=0
USER root
COPY wheels/ /tmp/hub321/
COPY activate.py /tmp/hub321/activate.py
RUN set -e; cd /tmp/hub321; sha256sum -c SHA256SUMS; \
    python -m pip install --no-index --no-deps --force-reinstall aimarket_hub-3.21.0-py3-none-any.whl; \
    KEEP_UI=$KEEP_UI python activate.py; \
    python -m pip check || echo "pip check: see above"; \
    chown -R "$RUN_USER" /app/aimarket_hub; \
    if [ "$KEEP_UI" != 1 ]; then for f in terminal-home.html operator.html plugins-demo.html hub-ui-i18n.json cap-descriptions-i18n.json studio-ui-i18n.json; do chown "$RUN_USER" "/app/$f"; done; fi; \
    cd /; rm -rf /tmp/hub321
USER ${RUN_USER}
LABEL org.opencontainers.image.version="3.21.0" \
      ai.market.release.wheel.sha256="e3dd66ef1dcbf46e52738d06fd3611e2906814d35dba371d23339ac0226fdd09"
