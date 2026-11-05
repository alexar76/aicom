ARG BASE
FROM ${BASE}
# Manifest gateway address overlay 2026-11-05 (supplier review finding, owner «исправляй»): the public manifest
# shows this hub's invoke endpoint for an operator gateway provider instead of its private address
# (http://aicom-diagnostics:8124/diagnose). Routing keeps the stored address. Only catalog.py changes.
COPY catalog.py /app/aimarket_hub/hub_routes/catalog.py
