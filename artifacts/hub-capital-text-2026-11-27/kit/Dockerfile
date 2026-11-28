# FROM the hub's running image; patch_text.py applies hub 3.22.5's public-text change to that image's own code
# (each replacement must match exactly once, else the build fails). Nothing else changes.
ARG BASE
FROM ${BASE}
ARG RUNUSER=root
USER root
COPY patch_text.py /tmp/patch_text.py
RUN python3 /tmp/patch_text.py /app/aimarket_hub \
 && python3 -m compileall -q /app/aimarket_hub/hub_routes/capital.py /app/aimarket_hub/api_models.py /app/aimarket_hub/capital_pricing.py \
 && rm /tmp/patch_text.py
USER ${RUNUSER}
