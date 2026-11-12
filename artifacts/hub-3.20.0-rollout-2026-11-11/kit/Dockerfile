# aimarket-hub 3.20.0 onto a running hub image (rollout 2026-11-11). Built FROM the container's own image,
# so plugins, generated files and the image's Python stay; only the hub package (and the provenance plugin
# where installed) change. WEB_PINS optionally raises fastapi/starlette to what 3.20.0 declares.
ARG BASE
FROM ${BASE}
ARG RUN_USER=hub
ARG KEEP_UI=0
ARG WEB_PINS=""
USER root
COPY wheels/ /tmp/hub320/
COPY schemas/ /tmp/hub320/schemas/
COPY activate.py /tmp/hub320/activate.py
RUN set -e; cd /tmp/hub320; sha256sum -c SHA256SUMS; \
    python -m pip install --no-index --no-deps --force-reinstall aimarket_hub-3.20.0-py3-none-any.whl; \
    if python -c 'import aimarket_provenance' 2>/dev/null; then \
      python -m pip install --no-index --no-deps --force-reinstall aimarket_provenance-2.3.2-py3-none-any.whl; fi; \
    if [ -n "$WEB_PINS" ]; then python -m pip install --no-cache-dir $WEB_PINS; fi; \
    KEEP_UI=$KEEP_UI python activate.py; \
    python -m pip check || echo "pip check: see above"; \
    chown -R "$RUN_USER" /app/aimarket_hub; \
    if [ "$KEEP_UI" != 1 ]; then for f in terminal-home.html operator.html plugins-demo.html hub-ui-i18n.json cap-descriptions-i18n.json studio-ui-i18n.json; do chown "$RUN_USER" "/app/$f"; done; fi; \
    cd /; rm -rf /tmp/hub320
USER ${RUN_USER}
LABEL org.opencontainers.image.version="3.20.0" \
      ai.market.release.wheel.sha256="e5001655f7ab9b25656e914e5820713c73a2e7cae25a8ec920122f435e309375"
