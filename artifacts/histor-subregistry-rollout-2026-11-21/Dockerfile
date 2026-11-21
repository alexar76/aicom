# HISTOR prod host, 2026-11-21: histor-histor:warden-0.35.0-prod (sha256:ef3e5cb4b312…, live since 10:11:43Z) plus the
# subregistry (histor/subregistry.py; migration 026, table registry_entries), aicom 933d203b9/56b85fd35.
# app.py, config.py, service.py, migrations.py = the image's own files with only the subregistry hunks of 933d203b9
# applied (6, 17, 22 and 23 changed lines, as in that commit); subregistry.py as in main. Nothing else moves: WARDEN
# 0.35.0, the cosigned checkpoint, the observer, the sandbox, the crawler and the landing are the base image's.
# On start HISTOR applies migration 026 (a new table); the base image then refuses the database until
# `switch.sh rollback` drops it again. The routes exist only with HISTOR_SUBREGISTRY=1 (set in the override).
FROM histor-histor:warden-0.35.0-prod
USER 0:0
COPY --chown=0:0 --chmod=644 ctx/app.py ctx/config.py ctx/service.py ctx/migrations.py ctx/subregistry.py /app/histor/
LABEL aicom.histor.overlay="subregistry-20261121" aicom.histor.overlay.commits="933d203b9 56b85fd35"
USER 65532:65532
RUN python -c "import histor.app, histor.subregistry, histor.service; from histor.migrations import MIGRATIONS; assert MIGRATIONS[-1][0] == 26"
