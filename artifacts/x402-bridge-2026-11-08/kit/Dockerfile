ARG BASE
FROM ${BASE}
# x402 bridge, honest map, onboarding funnel, knock verdicts and index-only admission, 2026-11-08: four new
# modules and thirteen live modules with this change ported onto them (never main's copies: the live hub runs
# 3.17.0 with overlays). Root-owned, read-only for the hub user.
USER root
COPY overlay/aimarket_hub/ /app/aimarket_hub/
RUN chown -R 0:0 /app/aimarket_hub/x402_bridge.py /app/aimarket_hub/peer_liveness.py /app/aimarket_hub/federation_funnel.py \
      /app/aimarket_hub/hub_routes/bridge.py /app/aimarket_hub/api.py /app/aimarket_hub/peer_routing.py \
      /app/aimarket_hub/hub_routes/invoke.py /app/aimarket_hub/hub_routes/invoke_parts /app/aimarket_hub/credits.py \
      /app/aimarket_hub/migrations.py /app/aimarket_hub/database.py /app/aimarket_hub/hub_routes/federation.py \
      /app/aimarket_hub/hub_routes/pages.py /app/aimarket_hub/hubs_page.py /app/aimarket_hub/federation_assay.py \
      /app/aimarket_hub/cli.py \
 && python -c "import aimarket_hub.api, aimarket_hub.x402_bridge, aimarket_hub.hub_routes.bridge"
USER hub
LABEL aicom.hub.overlay="x402-bridge-20261108"
