# FROM the hub's running image; only the four files of the change are replaced.
ARG BASE
FROM ${BASE}
COPY aimarket_hub/config.py aimarket_hub/crawler.py aimarket_hub/database.py aimarket_hub/realm.py /app/aimarket_hub/
