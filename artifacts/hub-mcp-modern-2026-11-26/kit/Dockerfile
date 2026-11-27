# FROM the hub's running image; MCP 2026-07-28 beside the handshake (main 9886575bc). mcp_gateway.py
# is this hub's own running variant with the same change applied (GATEWAY = 3220 | tutu | halowerk1 | main).
ARG BASE
FROM ${BASE}
ARG GATEWAY
COPY files/mcp_modern.py /app/aimarket_hub/mcp_modern.py
COPY files/hub_routes/ai_catalog.py /app/aimarket_hub/hub_routes/ai_catalog.py
COPY files/static/well-known/mcp/server-card.json /app/aimarket_hub/static/well-known/mcp/server-card.json
COPY gateway/mcp_gateway-${GATEWAY}.py /app/aimarket_hub/mcp_gateway.py
