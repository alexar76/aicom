# FROM the hub's running image; the changed files of the HTTP validity change, and catalog.py patched
# for this hub's own variant of it (CATALOG = 3220 | hub | main).
ARG BASE
FROM ${BASE}
ARG CATALOG
COPY files/crawler.py files/database.py files/migrations.py files/models.py files/http_validity.py /app/aimarket_hub/
COPY files/hub_routes/wellknown.py /app/aimarket_hub/hub_routes/wellknown.py
COPY catalog/catalog-${CATALOG}.py /app/aimarket_hub/hub_routes/catalog.py
