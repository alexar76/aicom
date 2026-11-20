# HISTOR prod host, 2026-11-20: histor-histor:signed-fingerprints-20261119 (sha256:d81ba087c9b3…) plus the
# subregistry (histor/subregistry.py; migration 026, table registry_entries), aicom main 56b85fd35.
# config.py, service.py, migrations.py as in main (each image file equalled main before the change);
# app.py = the image's own file with only this change applied (the import and the mount). Nothing else moves:
# WARDEN, the observer, the sandbox, the crawler and the landing are the base image's.
# On start HISTOR applies migration 026 (a new table); the base image then refuses the database until
# `switch.sh rollback` drops it again. The routes exist only with HISTOR_SUBREGISTRY=1 (set in the override).
FROM histor-histor:signed-fingerprints-20261119
USER 0:0
COPY --chown=0:0 --chmod=644 ctx/app.py ctx/config.py ctx/service.py ctx/migrations.py ctx/subregistry.py /app/histor/
LABEL aicom.histor.overlay="subregistry-20261120" aicom.histor.overlay.commits="56b85fd35"
USER 65532:65532
RUN python -c "import histor.app, histor.subregistry, histor.service; from histor.migrations import MIGRATIONS; assert MIGRATIONS[-1][0] == 26"
