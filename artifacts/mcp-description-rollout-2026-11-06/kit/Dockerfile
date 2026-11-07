ARG BASE
FROM ${BASE}
# 2026-11-06 (aicom 624e03e43): direct-tool descriptions without price or trial size, MCP server version 1.3.0.
# Only mcp_gateway.py changes: the committed file where the live one equals main's base (modelmarket.dev),
# the same change patched onto the live 3.16.0 file elsewhere (it keeps that file's receipt_binding block).
COPY mcp_gateway.py /app/aimarket_hub/mcp_gateway.py
