ARG BASE
FROM ${BASE}
# Catalogue floor overlay 2026-11-04 (aicom 28004ff8a, discovery draft -04 §5): the live crawler, database and
# migrations with the check ported by patch_live.py (or the committed files where the live ones equal its base),
# and the committed cli.py (`aimarket peers --reset-catalogue-time`).
COPY crawler.py /app/aimarket_hub/crawler.py
COPY database.py /app/aimarket_hub/database.py
COPY migrations.py /app/aimarket_hub/migrations.py
COPY cli.py /app/aimarket_hub/cli.py
