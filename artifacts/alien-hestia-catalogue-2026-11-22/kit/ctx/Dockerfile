# Alien Monitor, HESTIA card: catalogue link + per-agent code match (aicom main 5a47f524f). Thin image FROM the
# running one (BASE = its image): the UI built with the same toolchain as the live dist (vite 6.4.4; every chunk but
# the entry is byte-identical to it) and the one changed backend file.
ARG BASE
FROM ${BASE}
COPY --chown=0:0 dist/ /app/frontend/dist/
COPY --chown=0:0 hestia_status.py /app/backend/hestia_status.py
