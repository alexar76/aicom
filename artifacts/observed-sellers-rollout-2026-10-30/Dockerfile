ARG BASE
FROM ${BASE}
# observed-seller overlay 2026-10-30 (branch claude/backend-audit-ecosystem-a7acca d617b1e0a, ported to the pre-split api.py)
COPY observed_sellers.py /app/aimarket_hub/observed_sellers.py
COPY api.py /app/aimarket_hub/api.py
COPY migrations.py /app/aimarket_hub/migrations.py
COPY database.py /app/aimarket_hub/database.py
COPY mcp_gateway.py /app/aimarket_hub/mcp_gateway.py
COPY outbound_http.py /app/aimarket_hub/outbound_http.py
COPY hub_routes/federation.py /app/aimarket_hub/hub_routes/federation.py
COPY hub_routes/catalog.py /app/aimarket_hub/hub_routes/catalog.py
COPY hub_routes/wellknown.py /app/aimarket_hub/hub_routes/wellknown.py
