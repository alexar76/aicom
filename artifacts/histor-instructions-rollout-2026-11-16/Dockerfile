# HISTOR prod host, 2026-11-15: the running image histor-histor:landing-scanner-20261115 (sha256:f2660c5f…) plus
# the server-level instructions record (main f8ed320e8, migration 024): instructions.py (new), crawler.py,
# mcpclient.py, migrations.py, packages.py, store.py as in main (each image file equalled main before the change),
# and app.py = the image's own app.py with only that change applied (main's newer journey/Watch UI is not shipped).
# WARDEN and the landing are untouched. On start HISTOR applies migration 024 (ALTER TABLE observations ADD COLUMN
# instructions TEXT); older images then refuse the database until switch.sh rollback drops it again.
FROM histor-histor:landing-scanner-20261115
USER 0:0
COPY --chown=0:0 --chmod=644 ctx/app.py ctx/crawler.py ctx/instructions.py ctx/mcpclient.py ctx/migrations.py ctx/packages.py ctx/store.py /app/histor/
LABEL aicom.histor.overlay="instructions-20261115" aicom.histor.overlay.commits="f8ed320e8"
USER 65532:65532
RUN python -c "import histor.app, histor.crawler, histor.instructions; from histor.migrations import MIGRATIONS; assert MIGRATIONS[-1][0] == 24"
