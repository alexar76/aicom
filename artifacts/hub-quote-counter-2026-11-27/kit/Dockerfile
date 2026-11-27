# FROM the apex hub's running image; counts the Tutu quotes the hub hands out (migration 075, external_quotes).
ARG BASE
FROM ${BASE}
COPY files/tutu_esim.py /app/aimarket_hub/tutu_esim.py
COPY files/hub_routes/catalog.py /app/aimarket_hub/hub_routes/catalog.py
COPY files/hub_routes/invoke_parts/local_delivery.py /app/aimarket_hub/hub_routes/invoke_parts/local_delivery.py
COPY files/database.py /app/aimarket_hub/database.py
COPY files/migrations.py /app/aimarket_hub/migrations.py
