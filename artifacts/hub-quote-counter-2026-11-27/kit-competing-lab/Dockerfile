# FROM hub.modelmarket.dev's running image (Tutu build of 2026-11-24): the quote counter applied to that build's
# own files (migration 075, external_quotes; REST quote route only, this build has no invoke path for Tutu).
ARG BASE
FROM ${BASE}
COPY files/tutu_esim.py /app/aimarket_hub/tutu_esim.py
COPY files/hub_routes/catalog.py /app/aimarket_hub/hub_routes/catalog.py
COPY files/database.py /app/aimarket_hub/database.py
COPY files/migrations.py /app/aimarket_hub/migrations.py
