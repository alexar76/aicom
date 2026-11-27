# FROM the running quote-counter image of the apex (main 0f20a691b files with the counter): a fresh quote id per Tutu quote, carried to Tutu's
# checkout as mmq and stored in external_quotes (migration 076).
ARG BASE
FROM ${BASE}
COPY files/tutu_esim.py /app/aimarket_hub/tutu_esim.py
COPY files/database.py /app/aimarket_hub/database.py
COPY files/migrations.py /app/aimarket_hub/migrations.py
